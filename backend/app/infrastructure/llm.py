from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from typing import Any

from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncOpenAI,
    InternalServerError,
    RateLimitError,
)

from ..core.ports import LlmService
from .logging import preview, work_tag

logger = logging.getLogger(__name__)


class StreamInterrupted(Exception):
    """The response body stopped arriving part-way through.

    Worth its own type because of what it rules out. By the time bytes are
    flowing the provider has accepted the request and answered its headers, so
    whatever goes wrong from here is the connection, never the request: a
    rejected key or a malformed body would have come back as a status code
    before the first chunk. That makes every one of these safe to retry —
    without this, each new transport failure had to be recognised by name, and
    the list was always one outage behind reality (httpx2.ReadTimeout, then a
    bare ssl.SSLError, each taking down a report on its debut).
    """


class OpenAICompatibleLlmService(LlmService):
    """LLM adapter for OpenAI-compatible providers such as DashScope."""

    #: Failures the SDK itself classifies: the request never reached a decision,
    #: or the provider said it could not answer *right now*.
    _RETRYABLE = (
        StreamInterrupted,
        APIConnectionError,
        APITimeoutError,
        InternalServerError,
        RateLimitError,
        TimeoutError,
    )

    #: Transport failures worth another attempt, matched by class *name*.
    #:
    #: The SDK's HTTP library is not ours to choose: openai 3.x vendors
    #: `httpx2`, whose ReadTimeout shares no ancestry with the `httpx` this
    #: package used to import, so an isinstance list stops matching the day
    #: that dependency moves. It already did — a guard naming
    #: httpx.TimeoutException sat right here while httpx2.ReadTimeout walked
    #: past it and killed a report. Names survive the swap.
    _RETRYABLE_TRANSPORT_NAMES = frozenset({
        "ConnectError",
        "ConnectTimeout",
        "PoolTimeout",
        "ProtocolError",
        "ReadError",
        "ReadTimeout",
        "RemoteProtocolError",
        "TimeoutException",
        "WriteError",
        "WriteTimeout",
    })

    @staticmethod
    async def _interruptible(stream: Any) -> Any:
        """Yield the stream's chunks, relabelling a broken connection.

        Only advancing the iterator is wrapped. Whatever the caller does with a
        chunk it already has is its own business, so a parsing bug in this
        module still surfaces as itself instead of being retried five times.
        """
        iterator = stream.__aiter__()
        while True:
            try:
                chunk = await iterator.__anext__()
            except StopAsyncIteration:
                return
            except Exception as exc:
                raise StreamInterrupted(f"{type(exc).__name__}: {exc}") from exc
            yield chunk

    def _backoff(self, attempt: int) -> float:
        """Exponential wait with jitter, capped so a late attempt is not idle
        for minutes."""
        delay = self.backoff_seconds * (2 ** (attempt - 1))
        return min(delay, self.max_backoff_seconds) * random.uniform(0.8, 1.2)

    @classmethod
    def _is_retryable(cls, exc: BaseException) -> bool:
        """Whether another attempt could plausibly do better.

        Auth, permission and malformed-request errors are excluded: none of
        their class names appear above, and retrying them only wastes the
        user's time.
        """
        if isinstance(exc, cls._RETRYABLE):
            return True
        # Walk the ancestry so a vendored subclass matches through its base.
        return any(
            base.__name__ in cls._RETRYABLE_TRANSPORT_NAMES for base in type(exc).__mro__
        )

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 60.0,
        max_attempts: int = 5,
        backoff_seconds: float = 5.0,
        max_backoff_seconds: float = 30.0,
    ) -> None:
        if not base_url:
            raise ValueError("LLM_BASE_URL is required")
        if not api_key:
            raise ValueError("LLM_API_KEY is required")
        if not model:
            raise ValueError("LLM_MODEL_NAME is required")
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        self.model = model
        self.max_attempts = max_attempts
        self.backoff_seconds = backoff_seconds
        # The window matters more than the count: this provider drops out for
        # up to a minute at a time, and three attempts eighteen seconds apart
        # all landed inside one outage and failed the report anyway. Five
        # attempts backing off to a 30s ceiling span roughly 75 seconds.
        self.max_backoff_seconds = max_backoff_seconds
        # `timeout` is an idle timeout, not a budget for the whole answer: it
        # bounds the wait for the next chunk, and a healthy stream on this
        # provider goes quiet for under three seconds at a time, so a minute of
        # silence means the connection is dead rather than the model slow.
        #
        # max_retries=0 leaves this class as the only place that retries.
        # The SDK's own two attempts would otherwise multiply with ours, and a
        # bad request would be sent nine times before anyone heard about it.
        self.client = AsyncOpenAI(
            base_url=base_url.rstrip("/"), api_key=api_key, timeout=timeout, max_retries=0
        )

    async def _stream_once(self, request: dict[str, Any]) -> dict[str, Any]:
        """Run one request in streaming mode and fold the deltas back together.

        Streaming is not for show: gateways in front of these providers drop a
        connection that sits silent for a few minutes, and a full chapter takes
        longer than that to write. Chunks keep the connection alive; the caller
        still gets one whole message.
        """
        stream = await self.client.chat.completions.create(
            **request, stream=True, stream_options={"include_usage": True}
        )
        content_parts: list[str] = []
        # Tool calls arrive in fragments keyed by their position in the call list.
        partial_calls: dict[int, dict[str, Any]] = {}
        total_tokens: int | None = None
        async for chunk in self._interruptible(stream):
            if chunk.usage is not None:
                total_tokens = getattr(chunk.usage, "total_tokens", None)
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta is None:
                continue
            if delta.content:
                content_parts.append(delta.content)
            for call in delta.tool_calls or []:
                entry = partial_calls.setdefault(
                    call.index, {"id": None, "name": None, "arguments": ""}
                )
                if call.id:
                    entry["id"] = call.id
                if call.function is None:
                    continue
                if call.function.name:
                    entry["name"] = call.function.name
                if call.function.arguments:
                    entry["arguments"] += call.function.arguments
        tool_calls: list[dict[str, Any]] = []
        for _, entry in sorted(partial_calls.items()):
            arguments = entry["arguments"] or "{}"
            try:
                parsed_arguments = json.loads(arguments)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Model returned invalid tool arguments for {entry['name']}: {arguments}"
                ) from exc
            tool_calls.append(
                {"id": entry["id"], "name": entry["name"], "arguments": parsed_arguments}
            )
        return {
            "content": "".join(content_parts),
            "tool_calls": tool_calls,
            "total_tokens": total_tokens,
        }

    async def _complete_with_retry(self, request: dict[str, Any]) -> dict[str, Any]:
        """Retry transient provider failures.

        A gateway hiccup used to fail the whole report: one 5xx in the middle of
        a multi-chapter run left nothing to resume from. Auth and request errors
        are not retried — they will not fix themselves. A stream that dies
        part-way is retried from the start; the partial text is discarded.
        """
        for attempt in range(1, self.max_attempts + 1):
            try:
                return await self._stream_once(request)
            except Exception as exc:
                if not self._is_retryable(exc) or attempt == self.max_attempts:
                    raise
                delay = self._backoff(attempt)
                logger.warning(
                    "llm_retry%s model=%s attempt=%d/%d after=%.1fs error=%s: %s",
                    work_tag(), self.model, attempt, self.max_attempts, delay,
                    type(exc).__name__, preview(str(exc), limit=160),
                )
                await asyncio.sleep(delay)
        raise RuntimeError("unreachable")

    async def complete_streaming(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Same result as ``complete``, delivered as a stream.

        A long generation returns nothing until it finishes, and the gateway in
        front of the provider gives up waiting and answers 504. Streaming keeps
        bytes flowing, so the connection stays alive for as long as the model
        needs. Tool calls are not assembled here: only the tool-free
        composition call uses this path.
        """
        if tools:
            raise ValueError("Streaming does not assemble tool calls")
        request: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
            "stream": True,
        }

        logger.info(
            "llm_stream_request%s model=%s messages=%d prompt=%s",
            work_tag(), self.model, len(messages), preview(messages[-1].get("content") if messages else ""),
        )
        started = time.monotonic()
        chunks: list[str] = []
        for attempt in range(1, self.max_attempts + 1):
            try:
                stream = await self.client.chat.completions.create(**request)
                async for event in self._interruptible(stream):
                    choices = getattr(event, "choices", None)
                    if not choices:
                        continue
                    delta = getattr(choices[0], "delta", None)
                    piece = getattr(delta, "content", None) if delta else None
                    if piece:
                        chunks.append(piece)
                break
            except Exception as exc:
                # Partial output cannot be resumed; stitching two half answers
                # together would be worse than failing.
                if not self._is_retryable(exc) or attempt == self.max_attempts or chunks:
                    raise
                delay = self._backoff(attempt)
                logger.warning(
                    "llm_stream_retry%s model=%s attempt=%d/%d after=%.1fs error=%s",
                    work_tag(), self.model, attempt, self.max_attempts, delay, type(exc).__name__,
                )
                await asyncio.sleep(delay)

        content = "".join(chunks)
        logger.info(
            "llm_stream_response%s model=%s elapsed_ms=%d chars=%d content=%s",
            work_tag(), self.model, int((time.monotonic() - started) * 1000), len(content), preview(content),
        )
        return {"content": content, "tool_calls": []}

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        request: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
        }
        if tools:
            request["tools"] = [self._to_openai_tool(tool) for tool in tools]
            request["tool_choice"] = "auto"
        logger.info(
            "llm_request%s model=%s messages=%d tools=%d prompt=%s",
            work_tag(),
            self.model,
            len(messages),
            len(tools),
            preview(messages[-1].get("content") if messages else ""),
        )
        started = time.monotonic()
        result = await self._complete_with_retry(request)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        tool_calls = result["tool_calls"]
        logger.info(
            "llm_response%s model=%s elapsed_ms=%d tokens=%s tool_calls=%s content=%s",
            work_tag(),
            self.model,
            elapsed_ms,
            result["total_tokens"],
            [call["name"] for call in tool_calls] or "-",
            preview(result["content"]),
        )
        return {"content": result["content"], "tool_calls": tool_calls}

    @staticmethod
    def _to_openai_tool(schema: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": schema["name"],
                "description": schema.get("description", ""),
                "parameters": schema.get("parameters", {"type": "object", "properties": {}}),
            },
        }
