from __future__ import annotations

import json
from typing import Any

from .models import RequestContext
from .ports import LlmService
from .tooling import ToolContext, ToolRegistry


class ToolCallingAgent:
    """通用工具调用循环，保持与具体业务分析和数据源解耦。"""

    def __init__(self, llm: LlmService, tools: ToolRegistry, max_iterations: int = 8) -> None:
        self.llm = llm
        self.tools = tools
        self.max_iterations = max_iterations

    async def run(self, context: RequestContext, message: str) -> dict[str, Any]:
        messages: list[dict[str, Any]] = [{"role": "user", "content": message}]
        tool_context = ToolContext(request=context)
        executed_tools: list[dict[str, Any]] = []

        for _ in range(self.max_iterations):
            response = await self.llm.complete(messages, self.tools.schemas(tool_context))
            tool_calls = response.get("tool_calls") or []
            if not tool_calls:
                return {"answer": response.get("content", ""), "tool_calls": executed_tools}

            assistant_tool_calls = []
            for call in tool_calls:
                name = call["name"]
                arguments = call.get("arguments", {})
                call_id = call.get("id") or f"call_{len(executed_tools) + 1}"
                result = await self.tools.execute(name, tool_context, arguments)
                executed_tools.append({"name": name, "success": result.success, "metadata": result.metadata})
                assistant_tool_calls.append(
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)},
                    }
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": result.result_for_llm,
                    }
                )
            messages.insert(
                len(messages) - len(tool_calls),
                {
                    "role": "assistant",
                    "content": response.get("content") or None,
                    "tool_calls": assistant_tool_calls,
                },
            )

        raise RuntimeError(f"Agent exceeded max_iterations={self.max_iterations}")
