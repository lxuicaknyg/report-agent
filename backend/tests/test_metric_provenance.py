"""Every number in a chapter must trace back to the read that produced it.

Provenance used to stop at the chapter: a flat pool of evidence with no way to
say which of its entries settled which metric, and the settled values themselves
were discarded when the run ended.
"""

import asyncio

from app.core.models import Evidence, DataReadResult
from app.core.reports import (
    ChapterWriterInput,
    ChapterSupplement,
    DataSourceMetadata,
    ReportGenerationSession,
    ReportGenerationStatus,
    ReportTemplateSection,
)
from app.core.ports import LlmService
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


class CountingTool(Tool):
    """Returns one row and one evidence per call, with a fresh id each time."""

    name = "aggregate_dataset"
    description = "Aggregate"

    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, context: ToolContext, arguments: dict) -> ToolResult:
        self.calls += 1
        data = DataReadResult(
            dataset_id="sales", sheet_name="月度汇总", columns=["金额"],
            rows=[{"金额": 100}], row_count=1, offset=0, limit=10,
        )
        return ToolResult(
            success=True,
            result_for_llm="ok",
            data=data,
            evidence=[
                Evidence(
                    evidence_id=f"evidence-{self.calls}",
                    kind="calculation",
                    title="Dataset aggregate",
                    source="sales",
                    value={"rows": [{"金额": 100}]},
                    method='{"group_by":["区域"]}',
                )
            ],
        )


def aggregate_call(sheet: str = "月度汇总") -> dict:
    return {
        "content": "",
        "tool_calls": [{
            "name": "aggregate_dataset",
            "arguments": {"dataset_id": "sales", "sheet_name": sheet,
                          "metrics": [{"column": "金额", "function": "sum"}]},
        }],
    }


def chapter_input(metrics, supplements=()) -> ChapterWriterInput:
    return ChapterWriterInput(
        section=ReportTemplateSection(
            section_id="section_1", title="经营概况", order=0,
            template_blocks=[{"type": "paragraph", "text": "概况。"}],
        ),
        metrics=list(metrics),
        supplements=list(supplements),
        data_sources=[DataSourceMetadata(
            dataset_id="sales", name="销售 Excel", source_type="excel",
            sheets=[{"sheet_name": "月度汇总"}],
        )],
        user_instruction="生成",
    )


def session() -> ReportGenerationSession:
    return ReportGenerationSession(
        session_id="session-1", user_id="user-1", template_id="template-1",
        dataset_ids=["sales"], instruction="生成",
        status=ReportGenerationStatus.RUNNING,
    )


async def run_agent(llm, tool, input):
    registry = ToolRegistry()
    registry.register(tool)
    return await ChapterWriterAgent(llm=llm, tools=registry).write(input, session())


def test_each_finding_names_the_evidence_it_was_read_from():
    async def run():
        llm = ScriptedLlm([
            aggregate_call(),
            {"content": '{"status":"resolved","value":"100 元","basis":"月度汇总求和"}', "tool_calls": []},
            {"content": '{"status":"completed","content":"本期 100 元。"}', "tool_calls": []},
        ])
        result = await run_agent(llm, CountingTool(), chapter_input(["交易金额"]))

        finding = result.draft.findings[0]
        assert finding.metric == "交易金额"
        assert finding.value == "100 元"
        assert finding.basis == "月度汇总求和"
        # The link that was missing: the value points at the read behind it.
        assert finding.evidence_ids == ["evidence-1"]
        # And that id resolves against the chapter's own evidence.
        by_id = {item.evidence_id: item for item in result.draft.evidence}
        assert set(finding.evidence_ids) <= set(by_id)
        assert by_id["evidence-1"].method == '{"group_by":["区域"]}'

    asyncio.run(run())


def test_evidence_records_which_metric_asked_for_it():
    async def run():
        llm = ScriptedLlm([
            aggregate_call(),
            {"content": '{"status":"resolved","value":"100 元","basis":"求和"}', "tool_calls": []},
            {"content": '{"status":"completed","content":"本期 100 元。"}', "tool_calls": []},
        ])
        result = await run_agent(llm, CountingTool(), chapter_input(["交易金额"]))

        evidence = result.draft.evidence[0]
        assert evidence.metadata["metric"] == "交易金额"
        assert evidence.metadata["tool"] == "aggregate_dataset"

    asyncio.run(run())


def test_a_metric_reusing_another_read_still_names_its_source():
    """The cross-metric read cache saves a round trip. It used to cost the
    second metric its provenance, because a cache hit produced no evidence."""

    async def run():
        llm = ScriptedLlm([
            aggregate_call(),
            {"content": '{"status":"resolved","value":"100 元","basis":"求和"}', "tool_calls": []},
            aggregate_call(),  # identical arguments — served from cache
            {"content": '{"status":"resolved","value":"1 个区域","basis":"同一张表"}', "tool_calls": []},
            {"content": '{"status":"completed","content":"本期 100 元，覆盖 1 个区域。"}', "tool_calls": []},
        ])
        tool = CountingTool()
        result = await run_agent(llm, tool, chapter_input(["交易金额", "区域数"]))

        assert tool.calls == 1, "the second metric should have hit the cache"
        first, second = result.draft.findings
        assert first.evidence_ids == ["evidence-1"]
        # The reusing metric claims the same read rather than having none.
        assert second.evidence_ids == ["evidence-1"]
        # The evidence is still held once.
        assert len(result.draft.evidence) == 1

    asyncio.run(run())


def test_a_user_supplied_number_is_recorded_as_a_source_too():
    async def run():
        llm = ScriptedLlm([
            {"content": '{"status":"completed","content":"本期净利润 42 万元。"}', "tool_calls": []},
        ])
        result = await run_agent(
            llm,
            CountingTool(),
            chapter_input([], supplements=[
                ChapterSupplement(metric="净利润", value="42 万元", note="财务口径"),
            ]),
        )

        finding = next(item for item in result.draft.findings if item.metric == "净利润")
        assert finding.value == "42 万元"
        # A reader checking the chapter must see this was supplied, not measured.
        assert "用户补充" in finding.basis
        assert "财务口径" in finding.basis
        assert finding.evidence_ids == []

    asyncio.run(run())


def test_facts_carry_the_same_links_for_downstream_consumers():
    async def run():
        llm = ScriptedLlm([
            aggregate_call(),
            {"content": '{"status":"resolved","value":"100 元","basis":"求和"}', "tool_calls": []},
            {"content": '{"status":"completed","content":"本期 100 元。"}', "tool_calls": []},
        ])
        result = await run_agent(llm, CountingTool(), chapter_input(["交易金额"]))

        fact = result.draft.facts[0]
        assert fact.label == "交易金额"
        assert fact.value == "100 元"
        assert fact.evidence_ids == ["evidence-1"]

    asyncio.run(run())
