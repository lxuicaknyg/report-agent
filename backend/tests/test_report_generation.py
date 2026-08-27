import asyncio

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
    CreateReportGenerationRequest,
    ReportGenerationStatus,
    UserQuestion,
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
