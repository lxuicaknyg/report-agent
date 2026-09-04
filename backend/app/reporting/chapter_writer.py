from __future__ import annotations

from abc import ABC, abstractmethod

from ..core.reports import (
    ChapterDraft,
    ChapterWriterInput,
    ChapterWriterResult,
    ReportGenerationSession,
)


class ChapterWriter(ABC):
    """章节写作智能体的边界接口。

    Writer 接收章节原文和数据源元数据，内部可以自行执行 ReAct、调用数据工具
    并在信息不足时返回 waiting_user，而不把这些实现细节暴露给外围流程。
    """

    @abstractmethod
    async def write(
        self,
        input: ChapterWriterInput,
        session: ReportGenerationSession,
    ) -> ChapterWriterResult:
        pass


class StubChapterWriter(ChapterWriter):
    """Placeholder writer used to validate the outer report workflow."""

    async def write(
        self,
        input: ChapterWriterInput,
        session: ReportGenerationSession,
    ) -> ChapterWriterResult:
        source_names = "、".join(source.name for source in input.data_sources) or "未提供数据源"
        original = input.section.example_content or "模板未提供章节示例正文。"
        metrics = "、".join(input.metrics) or "未指定"
        context = input.global_context.model_dump(exclude_none=True)
        content = (
            f"本章节已根据模板原文生成外围流程结果。\n\n"
            f"原文参考：{original}\n\n"
            f"本章节指标：{metrics}\n\n"
            f"报告全局信息：{context or '未指定'}\n\n"
            f"可用数据源：{source_names}\n\n"
            f"后续 ChapterWriterAgent 将基于章节原文和数据源元数据执行 ReAct 取数，"
            f"再生成最终章节内容。"
        )
        draft = ChapterDraft(
            chapter_id=input.section.section_id,
            section_id=input.section.section_id,
            title=input.section.title,
            content=content,
            assumptions=["当前使用 StubChapterWriter，仅验证报告外围流程。"],
        )
        return ChapterWriterResult(status="completed", draft=draft)
