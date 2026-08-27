from __future__ import annotations

import json
from typing import Any

from openai import AsyncOpenAI

from ..core.ports import LlmService


class OpenAICompatibleLlmService(LlmService):
    """LLM adapter for OpenAI-compatible providers such as DashScope."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 120.0,
    ) -> None:
        if not base_url:
            raise ValueError("LLM_BASE_URL is required")
        if not api_key:
            raise ValueError("LLM_API_KEY is required")
        if not model:
            raise ValueError("LLM_MODEL_NAME is required")
        self.model = model
        self.client = AsyncOpenAI(base_url=base_url.rstrip("/"), api_key=api_key, timeout=timeout)

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
        response = await self.client.chat.completions.create(**request)
        message = response.choices[0].message
        tool_calls: list[dict[str, Any]] = []
        for call in message.tool_calls or []:
            arguments = call.function.arguments or "{}"
            try:
                parsed_arguments = json.loads(arguments)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Model returned invalid tool arguments for {call.function.name}: {arguments}") from exc
            tool_calls.append(
                {
                    "id": call.id,
                    "name": call.function.name,
                    "arguments": parsed_arguments,
                }
            )
        return {"content": message.content or "", "tool_calls": tool_calls}

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
