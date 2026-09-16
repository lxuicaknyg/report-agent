import asyncio
import json

from app.core.models import DataReadResult, Evidence
from app.core.ports import LlmService
from app.core.reports import (
    ChapterWriterInput,
    DataSourceMetadata,
    ReportGenerationSession,
    ReportTemplateSection,
    ReportGenerationStatus,
)
from app.core.tooling import Tool, ToolContext, ToolRegistry, ToolResult
from app.reporting.chapter_writer_agent import ChapterWriterAgent
from app.reporting.template_parser import ReportTemplateParser


class ScriptedLlm(LlmService):
    """Replays a fixed sequence of model turns, recording what it was asked."""

    def __init__(self, responses: list[dict] | None = None) -> None:
        self.calls: list[tuple[list[dict], list[dict]]] = []
        self.responses = list(responses) if responses is not None else []

    async def complete(self, messages, tools):
        # Snapshot: the agent appends to the same list across a metric's turns,
        # so recording the object itself would show every call as the last one.
        self.calls.append((list(messages), tools))
        return self.responses.pop(0)


def read_call(sheet_name: str, limit: int = 10) -> dict:
    """One research turn: a filled-in aggregation, never a written query."""
    return {
        "content": "",
        "tool_calls": [
            {
                "name": "aggregate_dataset",
                "arguments": {
                    "dataset_id": "sales",
                    "sheet_name": sheet_name,
                    "group_by": ["客户"],
                    "metrics": [{"column": "金额", "function": "sum"}],
                    "limit": limit,
                },
            }
        ],
    }


class FakeReadDatasetTool(Tool):
    name = "aggregate_dataset"
    description = "Aggregate one sheet of a dataset"

    def __init__(self) -> None:
        self.arguments: list[dict] = []

    async def execute(self, context: ToolContext, arguments: dict) -> ToolResult:
        self.arguments.append(arguments)
        if arguments["sheet_name"] == "wrong":
            return ToolResult(
                success=False,
                result_for_llm="Sheet 'wrong' not found. Available sheets: ['交易明细']",
                error="sheet_not_found",
                metadata={"available_sheets": ["交易明细"]},
            )
        data = DataReadResult(
            dataset_id="sales",
            sheet_name="交易明细",
            columns=["客户", "金额"],
            rows=[{"客户": "客户A", "金额": 12}],
            row_count=1,
            offset=0,
            limit=10,
        )
        return ToolResult(
            success=True,
            result_for_llm="Read 1 rows",
            data=data,
            evidence=[
                Evidence(
                    evidence_id="evidence-1",
                    kind="dataset",
                    title="Dataset rows",
                    source="sales",
                    value=data.model_dump(),
                    method="read_rows",
                )
            ],
        )


def test_a_metric_is_researched_with_its_own_budget_and_retries_read_errors():
    async def run():
        llm = ScriptedLlm(
            [
                read_call("wrong"),                                   # 指标第 1 次尝试：错的 sheet
                read_call("交易明细"),                                 # 修正参数后重试
                {"content": '{"status":"resolved","value":"12 万元","basis":"交易明细表求和"}', "tool_calls": []},
                {"content": '{"status":"completed","content":"客户A的交易记录如下。"}', "tool_calls": []},
            ]
        )
        tool = FakeReadDatasetTool()
        registry = ToolRegistry()
        registry.register(tool)
        agent = ChapterWriterAgent(llm=llm, tools=registry)
        section = ReportTemplateSection(
            section_id="section_1",
            title="客户分析",
            order=0,
            template_text="客户分析\n\n本章节展示客户交易明细。",
            template_blocks=[
                {"type": "heading", "text": "客户分析"},
                {"type": "paragraph", "text": "本章节展示客户交易明细。"},
            ],
        )
        result = await agent.write(
            ChapterWriterInput(
                section=section,
                metrics=["交易金额"],
                report_outline=["客户分析"],
                data_sources=[
                    DataSourceMetadata(
                        dataset_id="sales",
                        name="销售 Excel",
                        source_type="excel",
                        sheets=[{"sheet_name": "交易明细"}],
                    )
                ],
                user_instruction="关注客户交易",
            ),
            ReportGenerationSession(
                session_id="session-1",
                user_id="user-1",
                template_id="template-1",
                dataset_ids=["sales"],
                instruction="关注客户交易",
                status=ReportGenerationStatus.RUNNING,
            ),
        )

        assert result.status == "completed"
        assert result.draft.content == "客户A的交易记录如下。"
        assert result.draft.evidence[0].evidence_id == "evidence-1"
        assert [item["sheet_name"] for item in tool.arguments] == ["wrong", "交易明细"]
        assert any("sheet_not_found" in (m.get("content") or "") for m in llm.calls[1][0])

        # The research turn is scoped to one metric, and composition groups the
        # reads under it so every figure has a named owner.
        research_payload = json.loads(llm.calls[0][0][-1]["content"])
        assert research_payload["metric"] == "交易金额"
        composition_messages, composition_tools = llm.calls[-1]
        assert composition_tools == []
        composition_payload = json.loads(composition_messages[-1]["content"])
        # Parser bookkeeping and the duplicate Markdown rendering of the
        # template are left out; writing gets the shape and nothing else.
        assert composition_payload["chapter"]["title"] == "客户分析"
        assert composition_payload["chapter"]["blocks"] == [
            {"type": "paragraph", "text": "本章节展示客户交易明细。"}
        ]
        assert "template_text" not in composition_payload["chapter"]
        # Writing receives a settled value, not raw rows to re-derive.
        assert composition_payload["findings"] == [
            {"metric": "交易金额", "value": "12 万元", "basis": "交易明细表求和"}
        ]

    asyncio.run(run())


def test_each_unresolved_metric_becomes_its_own_question():
    """A single question naming every metric at once cannot be acted on."""

    async def run():
        llm = ScriptedLlm(
            [
                {"content": '{"status":"unresolved","reason":"数据源里没有同期口径"}', "tool_calls": []},
                {"content": '{"status":"unresolved","reason":"没有分行字段"}', "tool_calls": []},
            ]
        )
        agent = ChapterWriterAgent(llm=llm, tools=ToolRegistry())
        result = await agent.write(
            ChapterWriterInput(
                section=ReportTemplateSection(section_id="section_1", title="经营概况", order=0),
                metrics=["同比增速", "分行明细"],
            ),
            ReportGenerationSession(
                session_id="session-1",
                user_id="user-1",
                template_id="template-1",
                dataset_ids=["sales"],
                instruction="生成",
                status=ReportGenerationStatus.RUNNING,
            ),
        )

        assert result.status == "waiting_user"
        assert [q.metric for q in result.questions] == ["同比增速", "分行明细"]
        assert result.questions[0].content == "数据源里没有同期口径"

    asyncio.run(run())


def test_a_metric_declared_missing_after_a_successful_read_is_challenged_once():
    """The model has been observed calling data missing while holding it."""

    async def run():
        llm = ScriptedLlm(
            [
                read_call("交易明细"),
                {"content": '{"status":"unresolved","reason":"缺少同期数据"}', "tool_calls": []},
                {"content": '{"status":"resolved","value":"12 万元","basis":"交易明细表求和"}', "tool_calls": []},
                {"content": '{"status":"completed","content":"正文"}', "tool_calls": []},
            ]
        )
        registry = ToolRegistry()
        registry.register(FakeReadDatasetTool())
        agent = ChapterWriterAgent(llm=llm, tools=registry)
        result = await agent.write(
            ChapterWriterInput(
                section=ReportTemplateSection(section_id="section_1", title="经营概况", order=0),
                metrics=["交易金额"],
                data_sources=[
                    DataSourceMetadata(
                        dataset_id="sales", name="销售 Excel", source_type="excel",
                        sheets=[{"sheet_name": "交易明细"}],
                    )
                ],
            ),
            ReportGenerationSession(
                session_id="session-1",
                user_id="user-1",
                template_id="template-1",
                dataset_ids=["sales"],
                instruction="生成",
                status=ReportGenerationStatus.RUNNING,
            ),
        )

        assert result.status == "completed"
        challenge = llm.calls[2][0][-1]["content"]
        assert "真的无法得到" in challenge


    asyncio.run(run())


def test_template_parser_preserves_section_template_text():
    template = ReportTemplateParser().parse(
        "template-1",
        "report.md",
        "# 报告\n\n## 客户分析\n\n本章节展示客户交易明细。".encode(),
        "text/markdown",
    )

    assert template.sections[0].template_text == "客户分析\n本章节展示客户交易明细。"
    assert template.sections[0].template_blocks[0]["type"] == "heading"


def test_questions_block_the_chapter_even_when_the_model_says_completed():
    """A model that hedges in prose while reporting success must still ask."""

    class HedgingLlm(LlmService):
        def __init__(self) -> None:
            self.responses = [
                read_call("交易明细"),
                {"content": '{"status":"resolved","value":"12 万元","basis":"交易明细表求和"}', "tool_calls": []},
                {
                    "content": json.dumps(
                        {
                            "status": "completed",
                            "content": "同比变化待补充数据后再计算。",
                            "questions": [
                                {
                                    "question_id": "q_yoy",
                                    "metric": "2025年同期交易金额",
                                    "expected": "value",
                                    "content": "缺少历史同期数据，无法计算同比",
                                }
                            ],
                        },
                        ensure_ascii=False,
                    ),
                    "tool_calls": [],
                },
            ]

        async def complete(self, messages, tools):
            return self.responses.pop(0)

    async def run():
        registry = ToolRegistry()
        registry.register(FakeReadDatasetTool())
        agent = ChapterWriterAgent(llm=HedgingLlm(), tools=registry)
        result = await agent.write(
            ChapterWriterInput(
                section=ReportTemplateSection(section_id="section_1", title="经营概况", order=0),
                metrics=["交易金额同比增长率"],
                data_sources=[
                    DataSourceMetadata(
                        dataset_id="sales", name="销售 Excel", source_type="excel",
                        sheets=[{"sheet_name": "交易明细"}],
                    )
                ],
                user_instruction="和 2025 年同期做同比",
            ),
            ReportGenerationSession(
                session_id="session-1",
                user_id="user-1",
                template_id="template-1",
                dataset_ids=["sales"],
                instruction="和 2025 年同期做同比",
                status=ReportGenerationStatus.RUNNING,
            ),
        )

        assert result.status == "waiting_user"
        assert result.draft is None
        assert result.questions[0].metric == "2025年同期交易金额"
        assert result.questions[0].expected == "value"

    asyncio.run(run())


def test_parking_without_questions_still_names_what_is_missing():
    """A silent pause is unactionable, so fall back to the planned metrics."""

    class VagueLlm(LlmService):
        def __init__(self) -> None:
            self.responses = [
                read_call("交易明细"),
                {"content": '{"status":"resolved","value":"12 万元","basis":"交易明细表求和"}', "tool_calls": []},
                {
                    "content": json.dumps(
                        {"status": "waiting_user", "content": "当前未提供任何实际交易数据，无法计算。"},
                        ensure_ascii=False,
                    ),
                    "tool_calls": [],
                },
            ]

        async def complete(self, messages, tools):
            return self.responses.pop(0)

    async def run():
        registry = ToolRegistry()
        registry.register(FakeReadDatasetTool())
        agent = ChapterWriterAgent(llm=VagueLlm(), tools=registry)
        result = await agent.write(
            ChapterWriterInput(
                section=ReportTemplateSection(section_id="section_1", title="经营概况", order=0),
                metrics=["交易金额"],
                data_sources=[
                    DataSourceMetadata(
                        dataset_id="sales", name="销售 Excel", source_type="excel",
                        sheets=[{"sheet_name": "交易明细"}],
                    )
                ],
            ),
            ReportGenerationSession(
                session_id="session-1",
                user_id="user-1",
                template_id="template-1",
                dataset_ids=["sales"],
                instruction="生成",
                status=ReportGenerationStatus.RUNNING,
            ),
        )

        assert result.status == "waiting_user"
        assert len(result.questions) == 1
        assert result.questions[0].metric == "交易金额"
        assert result.questions[0].chapter_id == "section_1"
        assert "未提供任何实际交易数据" in result.questions[0].content

    asyncio.run(run())


def test_a_question_without_an_id_does_not_fail_the_report():
    """The model is not asked to invent ids; a missing one must not crash the run."""
    questions = ChapterWriterAgent._questions(
        [
            {"metric": "累计交易客户数", "content": "需要按客户去重的口径"},
            {"metric": "没有正文的问题"},
            "不是对象",
        ]
    )
    assert len(questions) == 1
    assert questions[0].metric == "累计交易客户数"
    assert questions[0].question_id.startswith("question_")


def test_research_insists_on_a_value_before_declaring_a_metric_resolved():
    """Raw rows are not a result: the value is decided once, during research."""

    async def run():
        llm = ScriptedLlm(
            [
                read_call("交易明细"),
                # resolved 但没给 value —— 应当被追问一次
                {"content": '{"status":"resolved"}', "tool_calls": []},
                {"content": '{"status":"resolved","value":"209,336,720 元","basis":"月度汇总 24 行求和"}',
                 "tool_calls": []},
                {"content": '{"status":"completed","content":"正文"}', "tool_calls": []},
            ]
        )
        registry = ToolRegistry()
        registry.register(FakeReadDatasetTool())
        agent = ChapterWriterAgent(llm=llm, tools=registry)
        result = await agent.write(
            ChapterWriterInput(
                section=ReportTemplateSection(section_id="section_1", title="经营概况", order=0),
                metrics=["累计交易金额"],
                data_sources=[
                    DataSourceMetadata(
                        dataset_id="sales", name="销售 Excel", source_type="excel",
                        sheets=[{"sheet_name": "交易明细"}],
                    )
                ],
            ),
            ReportGenerationSession(
                session_id="session-1", user_id="user-1", template_id="template-1",
                dataset_ids=["sales"], instruction="生成",
                status=ReportGenerationStatus.RUNNING,
            ),
        )

        assert result.status == "completed"
        # The value is asked for again rather than the metric being abandoned:
        # the model routinely works the number out in prose and never emits JSON.
        prompt_for_value = llm.calls[2][0][-1]["content"]
        assert "只允许输出一个 JSON 对象" in prompt_for_value
        findings = json.loads(llm.calls[-1][0][-1]["content"])["findings"]
        assert findings == [
            {"metric": "累计交易金额", "value": "209,336,720 元", "basis": "月度汇总 24 行求和"}
        ]

    asyncio.run(run())


def test_a_metric_worked_out_in_prose_is_asked_for_again_until_the_budget_runs_out():
    """The answer is in the prose; discarding it after one nudge wastes the work."""

    async def run():
        llm = ScriptedLlm(
            [
                read_call("月度汇总"),
                {"content": "已取得月度汇总表，现计算各区域合计：", "tool_calls": []},
                {"content": "华东：7,985,000 + 7,683,000 = 15,668,000 …", "tool_calls": []},
                {"content": '{"status":"resolved","value":"209,336,720 元","basis":"月度汇总求和"}',
                 "tool_calls": []},
                {"content": '{"status":"completed","content":"正文"}', "tool_calls": []},
            ]
        )
        registry = ToolRegistry()
        registry.register(FakeReadDatasetTool())
        agent = ChapterWriterAgent(llm=llm, tools=registry)
        result = await agent.write(
            ChapterWriterInput(
                section=ReportTemplateSection(section_id="section_1", title="正文", order=0),
                metrics=["累计交易金额"],
                data_sources=[
                    DataSourceMetadata(
                        dataset_id="sales", name="销售 Excel", source_type="excel",
                        sheets=[{"sheet_name": "月度汇总"}],
                    )
                ],
            ),
            ReportGenerationSession(
                session_id="session-1", user_id="user-1", template_id="template-1",
                dataset_ids=["sales"], instruction="生成",
                status=ReportGenerationStatus.RUNNING,
            ),
        )

        assert result.status == "completed"
        findings = json.loads(llm.calls[-1][0][-1]["content"])["findings"]
        assert findings[0]["value"] == "209,336,720 元"

    asyncio.run(run())
