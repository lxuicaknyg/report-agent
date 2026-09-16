"""A gateway hiccup must not fail a whole multi-chapter report."""

import asyncio

import httpx
import pytest
from openai import APIConnectionError, AuthenticationError, InternalServerError

from app.infrastructure.llm import OpenAICompatibleLlmService


def build(**kwargs) -> OpenAICompatibleLlmService:
    return OpenAICompatibleLlmService(
        base_url="https://example.invalid/v1",
        api_key="test-key",
        model="test-model",
        backoff_seconds=0,  # keep the test fast; the delay itself is not the behaviour
        **kwargs,
    )


class Chunk:
    """Minimal stand-in for one streamed chat completion chunk."""

    def __init__(self, content=None, tool_call=None, usage_tokens=None):
        delta = type("Delta", (), {"content": content, "tool_calls": tool_call or []})()
        self.choices = [type("Choice", (), {"delta": delta})()]
        self.usage = type("Usage", (), {"total_tokens": usage_tokens})() if usage_tokens else None


class ToolCallDelta:
    """One fragment of a tool call, as providers send them."""

    def __init__(self, index=0, call_id=None, name=None, arguments=None):
        self.index = index
        self.id = call_id
        self.function = type("Fn", (), {"name": name, "arguments": arguments})()


class Stream:
    """Async-iterable over prepared chunks."""

    def __init__(self, chunks):
        self.chunks = chunks

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk


def ok_stream():
    return Stream([Chunk(content="o"), Chunk(content="k"), Chunk(usage_tokens=7)])


def server_error() -> InternalServerError:
    request = httpx.Request("POST", "https://example.invalid/v1/chat/completions")
    response = httpx.Response(500, text="<html>gateway</html>", request=request)
    return InternalServerError("boom", response=response, body=None)


def install(service, errors: list[Exception], chunks=None):
    """Raise each queued error in turn, then answer normally."""
    calls = {"n": 0}

    async def create(**_):
        calls["n"] += 1
        if errors:
            raise errors.pop(0)
        return chunks() if callable(chunks) else ok_stream()

    service.client.chat.completions.create = create
    return calls


def test_a_transient_gateway_error_is_retried_and_then_succeeds():
    service = build(max_attempts=3)
    calls = install(service, [server_error(), server_error()])

    result = asyncio.run(service.complete([{"role": "user", "content": "hi"}], []))

    assert result["content"] == "ok"
    assert calls["n"] == 3


def test_retries_are_bounded():
    service = build(max_attempts=2)
    calls = install(service, [server_error(), server_error(), server_error()])

    with pytest.raises(InternalServerError):
        asyncio.run(service.complete([{"role": "user", "content": "hi"}], []))
    assert calls["n"] == 2


def test_a_connection_error_is_retried():
    service = build(max_attempts=2)
    request = httpx.Request("POST", "https://example.invalid/v1/chat/completions")
    calls = install(service, [APIConnectionError(request=request)])

    result = asyncio.run(service.complete([{"role": "user", "content": "hi"}], []))
    assert result["content"] == "ok"
    assert calls["n"] == 2


def test_an_auth_error_is_not_retried():
    """A bad key will not fix itself; retrying only wastes time."""
    service = build(max_attempts=3)
    request = httpx.Request("POST", "https://example.invalid/v1/chat/completions")
    response = httpx.Response(401, text="unauthorized", request=request)
    calls = install(service, [AuthenticationError("nope", response=response, body=None)])

    with pytest.raises(AuthenticationError):
        asyncio.run(service.complete([{"role": "user", "content": "hi"}], []))
    assert calls["n"] == 1


def test_streamed_text_fragments_are_folded_into_one_message():
    """The caller sees a whole message, not the chunks the gateway needs."""
    service = build()
    install(service, [])

    result = asyncio.run(service.complete([{"role": "user", "content": "hi"}], []))

    assert result["content"] == "ok"
    assert result["tool_calls"] == []


def test_a_tool_call_split_across_chunks_is_reassembled():
    service = build()
    install(
        service,
        [],
        chunks=lambda: Stream(
            [
                Chunk(tool_call=[ToolCallDelta(call_id="call_1", name="read_dataset", arguments='{"sh')]),
                Chunk(tool_call=[ToolCallDelta(arguments='eet": "月度汇总"}')]),
                Chunk(usage_tokens=11),
            ]
        ),
    )

    result = asyncio.run(service.complete([{"role": "user", "content": "hi"}], [
        {"name": "read_dataset", "description": "", "parameters": {}}
    ]))

    assert result["tool_calls"] == [
        {"id": "call_1", "name": "read_dataset", "arguments": {"sheet": "月度汇总"}}
    ]


def test_a_bare_transport_timeout_is_retried():
    """A hung connection surfaces as a plain TimeoutError, not APITimeoutError."""
    service = build(max_attempts=3)
    calls = install(service, [TimeoutError("deadline exceeded"), httpx.ReadTimeout("slow")])

    result = asyncio.run(service.complete([{"role": "user", "content": "hi"}], []))

    assert result["content"] == "ok"
    assert calls["n"] == 3


def test_streaming_returns_the_joined_content():
    """The composition call streams so a slow generation cannot trip a gateway."""
    service = build()
    pieces = ["{\"status\":", "\"completed\",", "\"content\":\"正文\"}"]

    class Delta:
        def __init__(self, text): self.content = text

    class Event:
        def __init__(self, text):
            self.choices = [type("C", (), {"delta": Delta(text)})()]

    class Stream:
        def __aiter__(self):
            async def gen():
                for piece in pieces:
                    yield Event(piece)
            return gen()

    async def create(**kwargs):
        assert kwargs["stream"] is True
        return Stream()

    service.client.chat.completions.create = create
    result = asyncio.run(service.complete_streaming([{"role": "user", "content": "hi"}], []))

    assert result["content"] == '{"status":"completed","content":"正文"}'
    assert result["tool_calls"] == []


def test_streaming_refuses_tools_rather_than_dropping_them():
    """Tool calls are not assembled on this path; silently losing them would
    look like the model answering nothing."""
    service = build()
    with pytest.raises(ValueError):
        asyncio.run(service.complete_streaming([{"role": "user", "content": "hi"}], [{"name": "t"}]))


class TimeoutException(Exception):
    """Stands in for httpx2's timeout base.

    The SDK's HTTP library is a transitive dependency: openai 3.x raises from
    `httpx2`, which shares no ancestry with the `httpx` this package used to
    import. These doubles inherit from nothing the module knows about and are
    recognised by class name alone — which is the mechanism under test.
    """


class ReadTimeout(TimeoutException):
    pass


def test_a_transport_timeout_from_an_unknown_http_library_is_retried():
    """The regression: a 180s stall raised httpx2.ReadTimeout, an isinstance
    guard naming httpx.TimeoutException did not match, and a whole report died
    on a hiccup that one more attempt would have survived."""
    service = build(max_attempts=3)
    calls = install(service, [ReadTimeout("read timeout"), TimeoutException("boom")])

    result = asyncio.run(service.complete([{"role": "user", "content": "hi"}], []))

    assert result["content"] == "ok"
    assert calls["n"] == 3


def test_an_unrelated_error_is_not_retried():
    """Name matching must not turn every exception into a retry."""

    class ValidationError(Exception):
        pass

    service = build(max_attempts=3)
    calls = install(service, [ValidationError("bad request")])

    with pytest.raises(ValidationError):
        asyncio.run(service.complete([{"role": "user", "content": "hi"}], []))
    assert calls["n"] == 1


def test_the_sdk_does_not_retry_underneath_us():
    """Two retry layers multiply: the SDK's own attempts times ours sent a
    doomed request nine times before anyone was told."""
    service = build()
    assert service.client.max_retries == 0


def test_the_retry_window_outlasts_a_short_outage():
    """Attempts alone do not help if they all land inside the same outage: the
    first fix retried three times within eighteen seconds and still lost the
    report to a provider that was back a minute later."""
    service = OpenAICompatibleLlmService(
        base_url="https://example.invalid/v1", api_key="k", model="m"
    )
    window = sum(service._backoff(n) for n in range(1, service.max_attempts))

    assert service.max_attempts >= 5
    # Jitter is ±20%, so check the floor rather than an exact figure.
    assert window >= 55
    # Capped, so raising max_attempts cannot idle for minutes at a stretch.
    assert service._backoff(99) <= service.max_backoff_seconds * 1.2


def test_a_connection_that_breaks_mid_stream_is_retried_whatever_raised_it():
    """Transport failures kept arriving as types this module had never heard
    of — httpx2.ReadTimeout, then a bare ssl.SSLError. What they have in
    common is where they happen, not what they are."""

    class SSLError(Exception):
        """Not an httpx type, not an SDK type: exactly the awkward case."""

    class BreaksMidStream:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise SSLError("[SSL] record layer failure")

    service = build(max_attempts=2)
    calls = {"n": 0}

    async def create(**_):
        calls["n"] += 1
        return ok_stream() if calls["n"] > 1 else BreaksMidStream()

    service.client.chat.completions.create = create

    result = asyncio.run(service.complete([{"role": "user", "content": "hi"}], []))

    assert result["content"] == "ok"
    assert calls["n"] == 2


def test_a_bug_handling_a_chunk_is_not_mistaken_for_a_broken_connection():
    """Only advancing the iterator counts as transport. A defect in this
    module must not be retried five times and reported as a network fault."""

    class Boom:
        @property
        def usage(self):
            raise RuntimeError("bug in chunk handling")

    class OneBadChunk:
        def __aiter__(self):
            return self

        async def __anext__(self):
            return Boom()

    service = build(max_attempts=3)
    calls = {"n": 0}

    async def create(**_):
        calls["n"] += 1
        return OneBadChunk()

    service.client.chat.completions.create = create

    with pytest.raises(RuntimeError, match="bug in chunk handling"):
        asyncio.run(service.complete([{"role": "user", "content": "hi"}], []))
    assert calls["n"] == 1
