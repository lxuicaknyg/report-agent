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
    def __init__(self) -> None:
        self.calls: list[tuple[list[dict], list[dict]]] = []
        self.responses = [
            {
                "content": "",
                "tool_calls": [
                    {
                        "name": "read_dataset",
                        "arguments": {"dataset_id": "sales", "sheet_name": "wrong", "limit": 10},
                    }
                ],
            },
            {
                "content": "",
                "tool_calls": [
                    {
                        "name": "read_dataset",
                        "arguments": {"dataset_id": "sales", "sheet_name": "交易明细", "limit": 10},
                    }
                ],
            },
            {"content": '{"status":"ready_for_writing"}', "tool_calls": []},
            {
                "content": json.dumps(
                    {
                        "status": "completed",
                        "content": "客户A的交易记录如下。",
                        "tables": [{"title": "交易明细", "columns": ["客户", "金额"], "rows": [["客户A", 12]]}],
                        "assumptions": [],
                        "questions": [],
                    },
                    ensure_ascii=False,
                ),
                "tool_calls": [],
            },
        ]

    async def complete(self, messages, tools):
        self.calls.append((messages, tools))
        return self.responses[len(self.calls) - 1]


class FakeReadDatasetTool(Tool):
    name = "read_dataset"
    description = "Read rows from an Excel dataset"

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


def test_chapter_writer_agent_retries_read_error_and_composes_from_template_and_data():
    async def run():
        llm = ScriptedLlm()
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
        assert result.draft is not None
        assert result.draft.content == "客户A的交易记录如下。"
        assert result.draft.evidence[0].evidence_id == "evidence-1"
        assert [item["sheet_name"] for item in tool.arguments] == ["wrong", "交易明细"]
        assert any("sheet_not_found" in (message.get("content") or "") for message in llm.calls[1][0])
        composition_messages, composition_tools = llm.calls[-1]
        assert composition_tools == []
        composition_payload = json.loads(composition_messages[-1]["content"])
        assert composition_payload["chapter"]["template_text"] == "客户分析\n\n本章节展示客户交易明细。"
        assert composition_payload["collected_data"][0]["rows"] == [{"客户": "客户A", "金额": 12}]

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
