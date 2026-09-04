from __future__ import annotations

from uuid import uuid4

from ..core.models import utc_now
from ..core.ports import ArtifactStore
from ..core.reports import (
    AnswerReportQuestionRequest,
    ChapterWriterInput,
    CreateReportGenerationRequest,
    DataSourceMetadata,
    ReportArtifact,
    ReportGenerationSession,
    ReportGenerationStatus,
    ReportTemplate,
)
from ..data.catalog import DataCatalog
from .assembler import ReportAssembler
from .chapter_writer import ChapterWriter
from .planner import ReportPlanner
from .renderer import MarkdownReportRenderer
from .session import ReportSessionRepository, ReportTemplateRepository, StoredReportTemplate
from .template_parser import ReportTemplateParser


class ReportGenerationService:
    """Application service that owns the report-generation business flow."""

    def __init__(
        self,
        sessions: ReportSessionRepository,
        templates: ReportTemplateRepository,
        template_parser: ReportTemplateParser,
        planner: ReportPlanner,
        writer: ChapterWriter,
        assembler: ReportAssembler,
        renderer: MarkdownReportRenderer,
        artifact_store: ArtifactStore,
        catalog: DataCatalog,
    ) -> None:
        self.sessions = sessions
        self.templates = templates
        self.template_parser = template_parser
        self.planner = planner
        self.writer = writer
        self.assembler = assembler
        self.renderer = renderer
        self.artifact_store = artifact_store
        self.catalog = catalog

    async def upload_template(
        self,
        filename: str,
        content: bytes,
        content_type: str | None = None,
    ) -> ReportTemplate:
        if not content:
            raise ValueError("Template file is empty")
        template_id = f"template_{uuid4().hex}"
        template = self.template_parser.parse(template_id, filename, content, content_type)
        await self.templates.save(StoredReportTemplate(template=template, content=content))
        return template

    async def get_template(self, template_id: str) -> ReportTemplate:
        return (await self.templates.get(template_id)).template

    async def create_session(
        self,
        request: CreateReportGenerationRequest,
        user_id: str,
    ) -> ReportGenerationSession:
        await self.templates.get(request.template_id)
        available = {dataset.dataset_id for dataset in await self.catalog.list_datasets()}
        missing = [dataset_id for dataset_id in request.dataset_ids if dataset_id not in available]
        if missing:
            raise KeyError(f"Dataset not found: {', '.join(missing)}")
        session = ReportGenerationSession(
            session_id=f"report_{uuid4().hex}",
            user_id=user_id,
            template_id=request.template_id,
            dataset_ids=request.dataset_ids,
            instruction=request.instruction,
            title=request.title,
        )
        await self.sessions.save(session)
        if request.auto_start:
            return await self.start(session.session_id)
        return session

    async def get_session(self, session_id: str) -> ReportGenerationSession:
        return await self.sessions.get(session_id)

    async def start(self, session_id: str) -> ReportGenerationSession:
        session = await self.sessions.get(session_id)
        if session.status == ReportGenerationStatus.COMPLETED:
            return session
        if session.status == ReportGenerationStatus.WAITING_USER and session.pending_questions:
            return session
        if session.status in {ReportGenerationStatus.CANCELLED, ReportGenerationStatus.FAILED}:
            raise ValueError(f"Session cannot be started from status: {session.status.value}")

        try:
            return await self._continue(session)
        except Exception as exc:
            session.status = ReportGenerationStatus.FAILED
            session.error = str(exc)
            session.updated_at = utc_now()
            await self.sessions.save(session)
            raise

    async def answer_question(
        self,
        session_id: str,
        request: AnswerReportQuestionRequest,
    ) -> ReportGenerationSession:
        session = await self.sessions.get(session_id)
        question = next((item for item in session.pending_questions if item.question_id == request.question_id), None)
        if question is None:
            raise KeyError(f"Pending report question not found: {request.question_id}")

        question.answer = request.answer
        question.answered_at = utc_now()
        session.answers[question.question_id] = request.answer
        session.pending_questions = [item for item in session.pending_questions if item.question_id != question.question_id]
        session.updated_at = utc_now()
        if session.pending_questions:
            await self.sessions.save(session)
            return session

        session.status = ReportGenerationStatus.RUNNING
        await self.sessions.save(session)
        if request.auto_resume:
            return await self.start(session_id)
        return session

    async def get_artifact(self, session_id: str, artifact_id: str) -> tuple[ReportArtifact, bytes]:
        session = await self.sessions.get(session_id)
        artifact = next((item for item in session.artifacts if item.artifact_id == artifact_id), None)
        if artifact is None:
            raise KeyError(f"Report artifact not found: {artifact_id}")
        return artifact, await self.artifact_store.get(artifact.uri)

    async def _continue(self, session: ReportGenerationSession) -> ReportGenerationSession:
        if session.template_snapshot is None:
            session.current_step = "parse_template"
            stored = await self.templates.get(session.template_id)
            session.template_snapshot = self.template_parser.parse(
                stored.template.template_id,
                stored.template.filename,
                stored.content,
                stored.template.content_type,
            )
            await self._save(session)

        if session.plan is None:
            session.current_step = "create_plan"
            session.plan = await self.planner.create_plan(
                session.template_snapshot,
                session.dataset_ids,
                session.instruction,
                session.title,
            )
            await self._save(session)

        session.status = ReportGenerationStatus.RUNNING
        session.current_step = "write_chapters"
        await self._save(session)
        data_sources = await self._build_data_source_metadata(session.dataset_ids)
        template_sections = {section.section_id: section for section in session.template_snapshot.sections}
        for section in session.plan.sections:
            if section.section_id in session.chapter_drafts:
                continue
            session.current_chapter_id = section.section_id
            template_section = template_sections.get(section.section_id)
            if template_section is None:
                raise ValueError(f"Template section not found: {section.section_id}")
            writer_input = ChapterWriterInput(
                section=template_section.model_copy(update={"title": section.title}),
                chapter_plan=section,
                global_context=session.plan.global_context,
                metrics=section.metrics,
                report_outline=[item.title for item in session.plan.sections],
                data_sources=data_sources,
                user_instruction=session.instruction,
                previous_answers=session.answers,
            )
            result = await self.writer.write(writer_input, session)
            if result.status == "waiting_user":
                session.pending_questions = result.questions
                session.status = ReportGenerationStatus.WAITING_USER
                session.current_step = "wait_for_user"
                await self._save(session)
                return session
            if result.status == "failed" or result.draft is None:
                raise ValueError(result.error or f"Chapter writer failed: {section.section_id}")
            session.chapter_drafts[section.section_id] = result.draft
            await self._save(session)

        session.status = ReportGenerationStatus.RUNNING
        session.current_step = "assemble_report"
        session.current_chapter_id = None
        session.assembled_report = await self.assembler.assemble(
            session.template_snapshot,
            session.plan,
            session.chapter_drafts,
        )
        await self._save(session)

        content = await self.renderer.render(session.assembled_report)
        artifact_id = f"artifact_{uuid4().hex}"
        filename = f"{session.session_id}{self.renderer.extension}"
        uri = await self.artifact_store.put(filename, content, self.renderer.content_type)
        session.artifacts.append(
            ReportArtifact(
                artifact_id=artifact_id,
                name=filename,
                content_type=self.renderer.content_type,
                uri=uri,
                format=self.renderer.format,
            )
        )
        session.status = ReportGenerationStatus.COMPLETED
        session.current_step = "completed"
        session.error = None
        await self._save(session)
        return session

    async def _build_data_source_metadata(self, dataset_ids: list[str]) -> list[DataSourceMetadata]:
        datasets = {dataset.dataset_id: dataset for dataset in await self.catalog.list_datasets()}
        result: list[DataSourceMetadata] = []
        for dataset_id in dataset_ids:
            dataset = datasets[dataset_id]
            try:
                sheets = [sheet.model_dump() for sheet in await self.catalog.sheets(dataset_id)]
            except NotImplementedError:
                sheets = []
            result.append(
                DataSourceMetadata(
                    dataset_id=dataset.dataset_id,
                    name=dataset.name,
                    source_type=dataset.source_type,
                    description=dataset.description,
                    sheets=sheets,
                    columns=[column.model_dump() for column in dataset.columns],
                    metadata=dataset.metadata,
                )
            )
        return result

    async def _save(self, session: ReportGenerationSession) -> None:
        session.updated_at = utc_now()
        await self.sessions.save(session)
