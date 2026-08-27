from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .models import RequestContext


class ToolContext(BaseModel):
    request: RequestContext
    metadata: dict[str, Any] = Field(default_factory=dict)
    model_config = ConfigDict(arbitrary_types_allowed=True)


class ToolResult(BaseModel):
    success: bool
    result_for_llm: str
    data: Any = None
    evidence: list[Any] = Field(default_factory=list)
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Tool(ABC):
    name: str
    description: str
    access_groups: list[str] = []
    parameters_schema: dict[str, Any] = {"type": "object", "properties": {}}

    @abstractmethod
    async def execute(self, context: ToolContext, arguments: dict[str, Any]) -> ToolResult:
        pass

    def schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters_schema,
            "access_groups": self.access_groups,
        }


class ToolRegistry:
    """工具注册、权限检查和调用入口。"""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def list(self) -> list[str]:
        return list(self._tools)

    def schemas(self, context: ToolContext | None = None) -> list[dict[str, Any]]:
        return [tool.schema() for tool in self._tools.values() if context is None or self._allowed(tool, context)]

    @staticmethod
    def _allowed(tool: Tool, context: ToolContext) -> bool:
        if not tool.access_groups:
            return True
        return bool(set(tool.access_groups) & set(context.request.user.group_memberships))

    async def execute(self, name: str, context: ToolContext, arguments: dict[str, Any]) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(success=False, result_for_llm=f"Unknown tool: {name}", error="tool_not_found")
        if not self._allowed(tool, context):
            return ToolResult(success=False, result_for_llm=f"Access denied for tool: {name}", error="access_denied")
        return await tool.execute(context, arguments)
