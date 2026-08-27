from __future__ import annotations

from ..core.models import AnalysisRequest, AnalysisResult, Evidence, RequestContext
from ..core.tooling import ToolContext, ToolRegistry


class AnalysisAgent:
    """领域 Agent：编排数据工具，未来可替换 Planner/LLM，不绑定数据源。"""

    def __init__(self, tools: ToolRegistry) -> None:
        self.tools = tools

    async def profile(self, context: RequestContext, dataset_id: str):
        result = await self.tools.execute("profile_dataset", ToolContext(request=context), {"dataset_id": dataset_id})
        if not result.success:
            raise ValueError(result.error or result.result_for_llm)
        return result.data

    async def query(self, context: RequestContext, request: AnalysisRequest) -> AnalysisResult:
        if not request.dataset_id or not request.sql:
            raise ValueError("dataset_id and sql are required for deterministic query execution")
        tool_context = ToolContext(request=context)
        result = await self.tools.execute("query_dataset", tool_context, request.model_dump(include={"dataset_id", "sql", "limit"}))
        if not result.success:
            raise ValueError(result.error or result.result_for_llm)
        query_result = result.data
        answer = f"查询完成，共返回 {query_result.row_count} 行，耗时 {query_result.execution_time_ms:.1f} ms。"
        return AnalysisResult(question=request.question, answer=answer, query_result=query_result, evidence=result.evidence)
