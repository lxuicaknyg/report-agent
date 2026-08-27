import asyncio

from app.core.agent import ToolCallingAgent
from app.core.models import RequestContext
from app.core.ports import LlmService
from app.core.tooling import ToolRegistry


class StaticLlmService(LlmService):
    async def complete(self, messages, tools):
        return {"content": "static response", "tool_calls": []}


def test_tool_calling_agent_has_replaceable_llm_port():
    async def run():
        agent = ToolCallingAgent(StaticLlmService(), ToolRegistry())
        result = await agent.run(RequestContext(), "hello")
        assert result["answer"]

    asyncio.run(run())
