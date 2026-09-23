"""A report from a template alone: no data file, every figure asked for.

The user has last period's report and wants this period's, but the numbers are
not in a spreadsheet yet. Planning still comes from the template; research has
nothing to read, so each metric becomes a question instead.
"""

import asyncio

from app.core.ports import LlmService
from app.core.reports import (
    ChapterSupplement,
    ChapterWriterInput,
    DataSourceMetadata,
    ReportGenerationSession,
    ReportGenerationStatus,
    ReportTemplateSection,
)
from app.core.tooling import Tool, ToolContext, ToolRegistry, ToolResult
from app.reporting.chapter_writer_agent import ChapterWriterAgent


class ScriptedLlm(LlmService):
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def complete(self, messages, tools):
        self.calls.append((list(messages), tools))
        return self.responses.pop(0)

    async def complete_streaming(self, messages, tools):
        return await self.complete(messages, tools)


class ExplodingTool(Tool):
    """Any call is a bug: with no data source there is nothing to read."""

    name = "aggregate_dataset"
    description = "Aggregate"

    async def execute(self, context: ToolContext, arguments: dict) -> ToolResult:
        raise AssertionError("research must not run without a data source")


def chapter(metrics, supplements=()) -> ChapterWriterInput:
    return ChapterWriterInput(
        section=ReportTemplateSection(
            section_id="section_1", title="一、经营概况", order=0,
            template_blocks=[{"type": "paragraph", "text": "报告期内整体交易规模…"}],
        ),
        metrics=list(metrics),
        supplements=list(supplements),
        data_sources=[],
        user_instruction="按这份模板生成本期报告",
    )


def session() -> ReportGenerationSession:
    return ReportGenerationSession(
        session_id="session-1", user_id="user-1", template_id="template-1",
        dataset_ids=[], instruction="按这份模板生成本期报告",
        status=ReportGenerationStatus.RUNNING,
    )


async def run(llm, input):
    registry = ToolRegistry()
    registry.register(ExplodingTool())
    return await ChapterWriterAgent(llm=llm, tools=registry).write(input, session())


def test_without_a_data_file_every_metric_is_asked_for():
    """Research used to be entered anyway. Every tool call came back
    "dataset not allowed", which is non-retryable, so the chapter failed and
    took the whole run down instead of asking."""

    async def go():
        llm = ScriptedLlm([])  # the model must not be consulted at all
        result = await run(llm, chapter(["累计交易金额", "交易笔数"]))

        assert result.status == "waiting_user"
        assert [q.metric for q in result.questions] == ["累计交易金额", "交易笔数"]
        assert "没有上传数据文件" in result.questions[0].content
        assert llm.calls == []

    asyncio.run(go())


def test_a_chapter_carrying_no_metrics_still_writes():
    """Narrative chapters — a preface, a methodology note — were never going to
    read anything, and must not be turned into a question."""

    async def go():
        llm = ScriptedLlm([
            {"content": '{"status":"completed","content":"本报告依据模板结构编制。"}', "tool_calls": []},
        ])
        result = await run(llm, chapter([]))

        assert result.status == "completed"
        assert result.draft.content == "本报告依据模板结构编制。"

    asyncio.run(go())


def test_supplied_numbers_carry_the_chapter_once_they_arrive():
    """The second pass: the user answered, so the chapter writes from what they
    gave and asks for nothing further."""

    async def go():
        llm = ScriptedLlm([
            {"content": '{"status":"completed","content":"本期累计交易金额 2.1 亿元。"}', "tool_calls": []},
        ])
        result = await run(
            llm,
            chapter(
                ["累计交易金额"],
                supplements=[ChapterSupplement(metric="累计交易金额", value="2.1 亿元", note="财务口径")],
            ),
        )

        assert result.status == "completed"
        finding = next(item for item in result.draft.findings if item.metric == "累计交易金额")
        assert finding.value == "2.1 亿元"
        # Nothing measured it, so the chapter says so rather than implying a query.
        assert "用户补充" in finding.basis
        assert finding.evidence_ids == []

    asyncio.run(go())


def test_a_data_file_still_takes_the_research_path():
    """The short circuit must key on there being no source, not on the mode."""

    async def go():
        llm = ScriptedLlm([
            {"content": '{"status":"unresolved","reason":"表里没有这个口径"}', "tool_calls": []},
        ])
        input = chapter(["累计交易金额"])
        input.data_sources = [
            DataSourceMetadata(dataset_id="sales", name="x.xlsx", source_type="excel",
                               sheets=[{"sheet_name": "月度汇总"}])
        ]
        result = await run(llm, input)

        assert result.status == "waiting_user"
        # The model was asked, and its own reason reached the user.
        assert llm.calls
        assert result.questions[0].content == "表里没有这个口径"

    asyncio.run(go())
