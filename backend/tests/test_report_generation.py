import asyncio
import json

from app.reporting.assembler import ReportAssembler
from app.reporting.chapter_writer import StubChapterWriter
from app.reporting.chapter_writer import ChapterWriter
from app.reporting.planner import ReportPlanner
from app.reporting.report_generation import ReportGenerationService
from app.reporting.renderer import MarkdownReportRenderer
from app.reporting.template_parser import ReportTemplateParser
from app.core.reports import (
    AnswerReportQuestionRequest,
    ChapterDraft,
    ChapterWriterResult,
    ConfirmReportPlanRequest,
    CreateReportGenerationRequest,
    ReportGenerationStatus,
    UserQuestion,
)
from app.core.ports import LlmService
from app.core.reports import (
    ChapterPlan,
    DataSourceMetadata,
    ReportTemplate,
    ReportTemplateSection,
)
from app.data.catalog import DataCatalog
from app.infrastructure.artifact_store import InMemoryArtifactStore
from app.infrastructure.report_repositories import (
    InMemoryReportSessionRepository,
    InMemoryReportTemplateRepository,
)


def build_service() -> ReportGenerationService:
    return ReportGenerationService(
        sessions=InMemoryReportSessionRepository(),
        templates=InMemoryReportTemplateRepository(),
        template_parser=ReportTemplateParser(),
        planner=ReportPlanner(),
        writer=StubChapterWriter(),
        assembler=ReportAssembler(),
        renderer=MarkdownReportRenderer(),
        artifact_store=InMemoryArtifactStore(),
        catalog=DataCatalog(),
    )


def test_planner_keeps_business_plan_separate_from_data_access_metadata():
    async def run():
        template = ReportTemplate(
            template_id="template_plan",
            filename="plan.md",
            title="经营分析",
            sections=[
                ReportTemplateSection(
                    section_id="section_1",
                    title="贷款业务情况",
                    order=0,
                    required_data=["授信贷款余额", "对公贷款余额"],
                )
            ],
        )
        metadata = [
            DataSourceMetadata(
                dataset_id="excel_1",
                name="经营数据",
                source_type="excel",
                sheets=[{"sheet_name": "Sheet1", "columns": [{"name": "贷款余额"}]}],
                columns=[{"name": "贷款余额"}],
            )
        ]
        plan = await ReportPlanner().create_plan(
            template,
            metadata,
            "报告期间：2025年第四季度，机构：北京分行",
        )
        assert plan.global_context.report_period == "2025年第四季度"
        assert plan.global_context.dimensions == {"机构": "北京分行"}
        assert plan.chapters == [ChapterPlan(section_id="section_1", title="贷款业务情况", metrics=["授信贷款余额", "对公贷款余额"])]
        assert "excel_1" not in plan.model_dump_json()
        assert "Sheet1" not in plan.model_dump_json()

    asyncio.run(run())


def test_planner_uses_model_to_infer_metrics_from_template_and_metadata():
    class PlannerLlm(LlmService):
        def __init__(self):
            self.messages = []

        async def complete(self, messages, tools):
            self.messages.append(messages)
            return {
                "content": json.dumps(
                    {
                        "title": "北京分行经营分析报告",
                        "global_context": {
                            "report_period": "2025年第四季度",
                            "dimensions": {"机构": "北京分行"},
                        },
                        "chapters": [
                            {
                                "section_id": "section_1",
                                "title": "贷款业务情况",
                                "metrics": ["授信贷款余额", "对公贷款余额"],
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                "tool_calls": [],
            }

    async def run():
        llm = PlannerLlm()
        template = ReportTemplate(
            template_id="template_model",
            filename="历史报告.md",
            title="历史报告",
            sections=[
                ReportTemplateSection(
                    section_id="section_1",
                    title="贷款业务情况",
                    order=0,
                    template_text="本季度贷款余额较上季度有所变化。",
                )
            ],
        )
        plan = await ReportPlanner(llm=llm).create_plan(
            template,
            [
                DataSourceMetadata(
                    dataset_id="excel_1",
                    name="经营数据",
                    source_type="excel",
                    columns=[{"name": "期末余额"}],
                    sample_rows=[{"期末余额": 100}],
                )
            ],
            "请生成北京分行2025年第四季度报告",
        )
        prompt = llm.messages[0][1]["content"]
        assert "历史报告.md" in prompt
        assert "期末余额" in prompt
        assert plan.chapters[0].metrics == ["授信贷款余额", "对公贷款余额"]
        assert plan.global_context.report_period == "2025年第四季度"

    asyncio.run(run())


def test_report_generation_outer_flow_and_artifact():
    async def run():
        service = build_service()
        template = await service.upload_template(
            "经营分析模板.md",
            "# 经营分析报告\n\n## 一、经营概况\n模板正文\n\n## 二、风险情况\n风险模板".encode(),
            "text/markdown",
        )
        # The outer report flow now validates selected data sources. Register
        # a minimal source-independent dataset for this boundary test.
        from app.data.sources.excel import ExcelDataSource
        from openpyxl import Workbook
        import tempfile
        from pathlib import Path

        fixture_path = Path(tempfile.mkdtemp()) / "data.xlsx"
        workbook = Workbook()
        workbook.active.append(["value"])
        workbook.active.append([1])
        workbook.save(fixture_path)
        service.catalog.register(ExcelDataSource(fixture_path, "excel_001", "data.xlsx"))

        session = await service.create_session(
            CreateReportGenerationRequest(
                template_id=template.template_id,
                dataset_ids=["excel_001"],
                instruction="参考模板生成类似报告",
                auto_start=True,
            ),
            user_id="local-user",
        )

        assert session.status == ReportGenerationStatus.COMPLETED
        assert session.plan is not None
        assert len(session.plan.sections) == 2
        assert len(session.chapter_drafts) == 2
        assert len(session.artifacts) == 1

        artifact, content = await service.get_artifact(session.session_id, session.artifacts[0].artifact_id)
        assert artifact.format == "markdown"
        assert "经营分析报告" in content.decode("utf-8")

    asyncio.run(run())


def test_template_parser_extracts_docx_headings():
    async def run():
        # A minimal DOCX package is enough to verify the semantic parser.
        import tempfile
        from pathlib import Path
        from zipfile import ZipFile

        root = Path(tempfile.mkdtemp())
        docx = root / "template.docx"
        content_types = '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'
        document = '''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:pPr><w:pStyle w:val="Title"/></w:pPr><w:r><w:t>分析报告</w:t></w:r></w:p><w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>经营概况</w:t></w:r></w:p><w:p><w:r><w:t>正文</w:t></w:r></w:p></w:body></w:document>'''
        with ZipFile(docx, "w") as archive:
            archive.writestr("[Content_Types].xml", content_types)
            archive.writestr("word/document.xml", document)

        template = ReportTemplateParser().parse("template_1", docx.name, docx.read_bytes())
        assert template.title == "分析报告"
        assert [section.title for section in template.sections] == ["经营概况"]

    asyncio.run(run())


def test_chapter_writer_can_pause_for_user_and_resume():
    class AskingWriter(ChapterWriter):
        def __init__(self):
            self.inputs = []

        async def write(self, input, session):
            self.inputs.append(input)
            if not session.answers:
                return ChapterWriterResult(
                    status="waiting_user",
                    questions=[UserQuestion(question_id="q-1", chapter_id=input.section.section_id, content="请确认是否继续")],
                )
            return ChapterWriterResult(
                status="completed",
                draft=ChapterDraft(
                    chapter_id=input.section.section_id,
                    section_id=input.section.section_id,
                    title=input.section.title,
                    content=f"已根据回答生成：{session.answers['q-1']}",
                ),
            )

    async def run():
        service = build_service()
        writer = AskingWriter()
        service.writer = writer
        template = await service.upload_template("t.md", b"# T\n\n## S\nBody", "text/markdown")

        from app.data.sources.excel import ExcelDataSource
        from openpyxl import Workbook
        import tempfile
        from pathlib import Path

        fixture_path = Path(tempfile.mkdtemp()) / "data.xlsx"
        workbook = Workbook()
        workbook.active.append(["value"])
        workbook.active.append([1])
        workbook.save(fixture_path)
        service.catalog.register(ExcelDataSource(fixture_path, "excel_002", "data.xlsx"))

        session = await service.create_session(
            CreateReportGenerationRequest(template_id=template.template_id, dataset_ids=["excel_002"], instruction="generate"),
            user_id="local-user",
        )
        assert session.status == ReportGenerationStatus.AWAITING_CONFIRMATION
        assert session.plan is not None
        assert session.data_source_metadata[0].sheets[0]["columns"][0]["name"] == "value"

        session = await service.confirm_plan(
            session.session_id,
            ConfirmReportPlanRequest(chapters=session.plan.chapters),
        )
        assert session.status == ReportGenerationStatus.WAITING_USER
        assert session.pending_questions[0].question_id == "q-1"

        resumed = await service.answer_question(
            session.session_id,
            AnswerReportQuestionRequest(question_id="q-1", answer="继续"),
        )
        assert resumed.status == ReportGenerationStatus.COMPLETED
        assert writer.inputs[0].data_sources[0].dataset_id == "excel_002"
        assert writer.inputs[1].previous_answers["q-1"] == "继续"

    asyncio.run(run())
