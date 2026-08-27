from __future__ import annotations

from typing import Any

from ..core.ports import LlmService


class MockLlmService(LlmService):
    """本地开发和测试用模型实现；生产环境替换为 OpenAI/Claude 等适配器。"""

    async def complete(self, messages: list[dict[str, str]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        last_message = messages[-1]["content"] if messages else ""
        if last_message.startswith("tool_call:") or (messages and messages[-1]["role"] == "tool"):
            return {"content": "工具执行完成，请基于工具结果生成最终回答。", "tool_calls": []}
        return {"content": "当前使用本地 Mock LLM。请通过 /analysis/query 使用确定性数据分析，或接入真实 LlmService。", "tool_calls": []}
