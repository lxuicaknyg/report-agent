from __future__ import annotations

import logging
from uuid import uuid4

from ..core.models import utc_now
from ..core.ports import ArtifactStore
from ..core.reports import (
    AnswerReportQuestionRequest,
    ChapterWriterInput,
    ConfirmReportPlanRequest,
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

logger = logging.getLogger(__name__)


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
        logger.info("template_uploaded template_id=%s filename=%s sections=%d", template.template_id, filename, len(template.sections))
        return template

    async def get_template(self, template_id: str) -> ReportTemplate:
        return (await self.templates.get(template_id)).template

    async def list_templates(self, offset: int = 0, limit: int = 50) -> tuple[int, list[ReportTemplate]]:
        items = [stored.template for stored in await self.templates.list()]
        items.sort(key=lambda item: item.created_at, reverse=True)
        return len(items), items[offset:offset + limit]

    async def list_sessions(self, offset: int = 0, limit: int = 20) -> tuple[int, list[ReportGenerationSession]]:
        items = await self.sessions.list()
        items.sort(key=lambda item: item.updated_at, reverse=True)
        return len(items), items[offset:offset + limit]

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
        logger.info("report_session_created session_id=%s template_id=%s datasets=%s", session.session_id, request.template_id, request.dataset_ids)
        session = await self._prepare_plan(session)
        if request.auto_start:
            assert session.plan is not None
            session.plan.status = "approved"
            await self._save(session)
            return await self.start(session.session_id)
        return session

    async def get_session(self, session_id: str) -> ReportGenerationSession:
        return await self.sessions.get(session_id)

    async def start(self, session_id: str) -> ReportGenerationSession:
        session = await self.sessions.get(session_id)
        logger.info("report_generation_started session_id=%s status=%s", session_id, session.status)
        if session.status == ReportGenerationStatus.COMPLETED:
            return session
        if session.plan is not None and session.plan.status == "awaiting_confirmation":
            session.status = ReportGenerationStatus.AWAITING_CONFIRMATION
            await self._save(session)
            return session
        if session.status == ReportGenerationStatus.WAITING_USER and session.pending_questions:
            return session
        if session.status in {ReportGenerationStatus.CANCELLED, ReportGenerationStatus.FAILED}:
            raise ValueError(f"Session cannot be started from status: {session.status.value}")

        try:
            return await self._continue(session)
        except Exception as exc:
            logger.exception("report_generation_failed session_id=%s step=%s", session_id, session.current_step)
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

    async def confirm_plan(
        self,
        session_id: str,
        request: ConfirmReportPlanRequest,
    ) -> ReportGenerationSession:
        session = await self.sessions.get(session_id)
        if session.plan is None:
            raise ValueError("Report plan has not been generated")
        if session.plan.status != "awaiting_confirmation":
            raise ValueError(f"Report plan cannot be confirmed from status: {session.plan.status}")

        plan = session.plan
        if request.title is not None:
            title = request.title.strip()
            if not title:
                raise ValueError("Report title cannot be empty")
            plan.title = title
            session.title = title

        if request.global_context is not None:
            plan.global_context = request.global_context
        if request.report_period is not None:
            plan.global_context.report_period = request.report_period.strip() or None
        if request.dimensions is not None:
            plan.global_context.dimensions = {
                str(key).strip(): str(value).strip()
                for key, value in request.dimensions.items()
                if str(key).strip() and str(value).strip()
            }

        if request.chapters is not None:
            expected = [chapter.section_id for chapter in plan.sections]
            actual = [chapter.section_id for chapter in request.chapters]
            if len(actual) != len(set(actual)):
                raise ValueError("Chapter section_id values must be unique")
            if actual != expected:
                raise ValueError("Confirmed chapters must preserve the template chapter order")
            plan.chapters = list(request.chapters)
            plan.assembly_order = actual

        plan.version += 1
        plan.status = "approved"
        session.status = ReportGenerationStatus.RUNNING
        session.current_step = "plan_approved"
        await self._save(session)
        return await self.start(session_id)

    async def get_artifact(self, session_id: str, artifact_id: str) -> tuple[ReportArtifact, bytes]:
        session = await self.sessions.get(session_id)
        artifact = next((item for item in session.artifacts if item.artifact_id == artifact_id), None)
        if artifact is None:
            raise KeyError(f"Report artifact not found: {artifact_id}")
        return artifact, await self.artifact_store.get(artifact.uri)

    async def _continue(self, session: ReportGenerationSession) -> ReportGenerationSession:
        if session.template_snapshot is None:
            logger.info("template_parsing_started session_id=%s", session.session_id)
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
            session = await self._prepare_plan(session)

        if session.plan.status == "awaiting_confirmation":
            session.status = ReportGenerationStatus.AWAITING_CONFIRMATION
            session.current_step = "await_plan_confirmation"
            await self._save(session)
            return session

        session.status = ReportGenerationStatus.RUNNING
        session.plan.status = "executing"
        session.current_step = "write_chapters"
        await self._save(session)
        data_sources = session.data_source_metadata
        template_sections = {section.section_id: section for section in session.template_snapshot.sections}
        for section in session.plan.sections:
            if section.section_id in session.chapter_drafts:
                logger.info("chapter_skipped session_id=%s section_id=%s", session.session_id, section.section_id)
                continue
            session.current_chapter_id = section.section_id
            template_section = template_sections.get(section.section_id)
            if template_section is None:
                raise ValueError(f"Template section not found: {section.section_id}")
            logger.info("chapter_generation_started session_id=%s section_id=%s title=%s", session.session_id, section.section_id, section.title)
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
                logger.info("chapter_waiting_user session_id=%s section_id=%s questions=%d", session.session_id, section.section_id, len(result.questions))
                session.pending_questions = result.questions
                session.status = ReportGenerationStatus.WAITING_USER
                session.current_step = "wait_for_user"
                await self._save(session)
                return session
            if result.status == "failed" or result.draft is None:
                raise ValueError(result.error or f"Chapter writer failed: {section.section_id}")
            session.chapter_drafts[section.section_id] = result.draft
            await self._save(session)
            logger.info("chapter_generation_completed session_id=%s section_id=%s", session.session_id, section.section_id)

        session.status = ReportGenerationStatus.RUNNING
        session.current_step = "assemble_report"
        session.current_chapter_id = None
        session.assembled_report = await self.assembler.assemble(
            session.template_snapshot,
            session.plan,
            session.chapter_drafts,
        )
        await self._save(session)
        logger.info("report_assembled session_id=%s chapters=%d", session.session_id, len(session.assembled_report.chapters))

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
        session.plan.status = "completed"
        session.current_step = "completed"
        session.error = None
        await self._save(session)
        logger.info("report_generation_completed session_id=%s artifact_id=%s filename=%s", session.session_id, artifact_id, filename)
        return session

    async def _prepare_plan(self, session: ReportGenerationSession) -> ReportGenerationSession:
        if session.template_snapshot is None:
            session.current_step = "parse_template"
            stored = await self.templates.get(session.template_id)
            session.template_snapshot = self.template_parser.parse(
                stored.template.template_id,
                stored.template.filename,
                stored.content,
                stored.template.content_type,
            )

        if not session.data_source_metadata:
            session.current_step = "build_data_source_metadata"
            session.data_source_metadata = await self._build_data_source_metadata(session.dataset_ids)

        session.current_step = "create_plan"
        session.plan = await self.planner.create_plan(
            template=session.template_snapshot,
            instruction=session.instruction,
            data_sources=session.data_source_metadata,
            title=session.title,
        )
        session.status = ReportGenerationStatus.AWAITING_CONFIRMATION
        await self._save(session)
        logger.info("report_plan_created session_id=%s sections=%d", session.session_id, len(session.plan.sections))
        return session

    async def _build_data_source_metadata(self, dataset_ids: list[str]) -> list[DataSourceMetadata]:
        datasets = {dataset.dataset_id: dataset for dataset in await self.catalog.list_datasets()}
        result: list[DataSourceMetadata] = []
        for dataset_id in dataset_ids:
            dataset = datasets[dataset_id]
            try:
                sheet_models = await self.catalog.sheets(dataset_id)
                sheets = [sheet.model_dump(mode="json") for sheet in sheet_models]
            except NotImplementedError:
                sheets = []
            columns = [column.model_dump(mode="json") for column in dataset.columns]
            if not columns:
                columns = [column.model_dump(mode="json") for column in await self.catalog.schema(dataset_id)]
            sample_rows: list[dict] = []
            try:
                profile = await self.catalog.profile(dataset_id)
                sample_rows = profile.sample_rows[:5]
            except Exception as exc:
                logger.warning("data_source_sample_unavailable dataset_id=%s error=%s", dataset_id, exc)
            result.append(
                DataSourceMetadata(
                    dataset_id=dataset.dataset_id,
                    name=dataset.name,
                    source_type=dataset.source_type,
                    description=dataset.description,
                    sheets=sheets,
                    columns=columns,
                    sample_rows=sample_rows,
                    metadata=dict(dataset.metadata),
                )
            )
        return result

    async def _save(self, session: ReportGenerationSession) -> None:
        session.updated_at = utc_now()
        await self.sessions.save(session)
