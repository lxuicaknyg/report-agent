import asyncio

from app.core.models import RequestContext, User
from app.core.tooling import Tool, ToolContext, ToolRegistry, ToolResult


class DemoTool(Tool):
    name = "demo"
    description = "demo"
    access_groups = ["analyst"]

    async def execute(self, context: ToolContext, arguments: dict) -> ToolResult:
        return ToolResult(success=True, result_for_llm="ok", data=arguments)


def test_tool_registry_permissions():
    async def run():
        registry = ToolRegistry()
        registry.register(DemoTool())
        denied = await registry.execute("demo", ToolContext(request=RequestContext(user=User(id="u"))), {})
        assert not denied.success
        allowed = await registry.execute("demo", ToolContext(request=RequestContext(user=User(id="u", group_memberships=["analyst"]))), {"x": 1})
        assert allowed.success

    asyncio.run(run())
