from __future__ import annotations

import functools
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from tempfile import gettempdir
from uuid import uuid4

from ..config import settings
from ..connections.service import ConnectionService
from ..core.models import utc_now
from ..core.ports import ArtifactStore
from ..core.reports import (
    ChapterPlan,
    ChapterSupplement,
    ChapterWriterInput,
    CreateReportGenerationRequest,
    DataSourceMetadata,
    GenerationCancelled,
    QuestionResolutionInput,
    ReportArtifact,
    ReportGenerationSession,
    ReportGenerationStatus,
    ReportTemplate,
    ResolveQuestionsRequest,
    UserInputRejected,
    UserQuestion,
    synthesize_template,
)
from ..core.tabular import TableParseError, parse_table
from ..data.catalog import DataCatalog
from ..data.sources.excel import ExcelDataSource
from ..infrastructure.logging import preview
from .assembler import ReportAssembler
from .chapter_writer import ChapterWriter
from .planner import ReportPlanner
from .renderer import MarkdownReportRenderer
from .session import ReportSessionRepository, ReportTemplateRepository, StoredReportTemplate
from .template_parser import ReportTemplateParser

logger = logging.getLogger(__name__)

#: The resolutions that put data into a chapter, mapped to what the chapter
#: writer is told about where it came from. A resolution missing from here —
#: ``pending``, ``dropped`` — carries nothing, which is what makes membership
#: the test for "did the user supply this".
_SUPPLEMENT_SOURCE = {"value": "manual", "sql": "sql", "table": "pasted"}


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
        connections: ConnectionService | None = None,
        max_chapter_attempts: int = 3,
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
        #: Optional: without it a question can still be answered with a typed
        #: value or dropped, which is the whole flow every test needs.
        self.connections = connections
        self.max_chapter_attempts = max_chapter_attempts

    async def upload_template(
        self,
        filename: str,
        content: bytes,
        content_type: str | None = None,
        *,
        owner_id: str | None = None,
    ) -> ReportTemplate:
        if not content:
            raise ValueError("Template file is empty")
        template_id = f"template_{uuid4().hex}"
        template = self.template_parser.parse(template_id, filename, content, content_type)
        # Set after parsing: the parser's job is to read the document, not to
        # know who sent it.
        template = template.model_copy(update={"owner_id": owner_id})
        await self.templates.save(StoredReportTemplate(template=template, content=content))
        logger.info("template_uploaded template_id=%s filename=%s sections=%d", template.template_id, filename, len(template.sections))
        return template

    async def get_template(self, template_id: str) -> ReportTemplate:
        return (await self.templates.get(template_id)).template

    async def list_templates(
        self, offset: int = 0, limit: int = 50, *, owner_id: str | None = None
    ) -> tuple[int, list[ReportTemplate]]:
        items = [stored.template for stored in await self.templates.list()]
        if owner_id is not None:
            items = [item for item in items if item.owner_id == owner_id]
        items.sort(key=lambda item: item.created_at, reverse=True)
        return len(items), items[offset:offset + limit]

    async def list_sessions(
        self, offset: int = 0, limit: int = 20, *, owner_id: str | None = None
    ) -> tuple[int, list[ReportGenerationSession]]:
        items = await self.sessions.list()
        if owner_id is not None:
            items = [item for item in items if item.user_id == owner_id]
        items.sort(key=lambda item: item.updated_at, reverse=True)
        return len(items), items[offset:offset + limit]

    async def create_session(
        self,
        request: CreateReportGenerationRequest,
        user_id: str,
        *,
        on_created: Callable[[ReportGenerationSession], Awaitable[None]] | None = None,
    ) -> ReportGenerationSession:
        # Neither input is required. A template says which chapters exist; with
        # no template the model proposes them and the agreed outline becomes
        # one. Datasets say where the figures come from; with none they are
        # collected from the user instead.
        if not request.template_id and self.planner.llm is None:
            raise ValueError("Planning without a template requires a configured model")
        if request.template_id:
            await self.templates.get(request.template_id)
        available = {dataset.dataset_id for dataset in await self.catalog.list_datasets()}
        missing = [dataset_id for dataset_id in request.dataset_ids if dataset_id not in available]
        if missing:
            raise KeyError(f"Dataset not found: {', '.join(missing)}")
        session = ReportGenerationSession(
            session_id=f"report_{uuid4().hex}",
            user_id=user_id,
            # Empty until a conversation-authored outline is adopted, which is
            # when its synthesized template gets an id.
            template_id=request.template_id or "",
            dataset_ids=request.dataset_ids,
            instruction=request.instruction,
            title=request.title,
        )
        await self.sessions.save(session)
        logger.info("report_session_created session_id=%s template_id=%s datasets=%s", session.session_id, request.template_id, request.dataset_ids)
        if on_created is not None:
            # Hand the caller the session id before the slow part starts. A
            # failure while planning otherwise left the session orphaned: the
            # conversation was never told about it, so the user was invited to
            # retry a run nothing could find, and re-uploaded their files.
            await on_created(session)
        try:
            session = await self._prepare_plan(session)
        except Exception as exc:
            # Same contract as start(): record the failure on the session, then
            # let it propagate. Recording it is what makes the run resumable —
            # planning is the one step that used to fail with nothing on the
            # session to resume from.
            logger.exception("report_plan_failed session_id=%s", session.session_id)
            session.status = ReportGenerationStatus.FAILED
            session.current_step = "create_plan"
            session.error = str(exc)
            session.updated_at = utc_now()
            await self.sessions.save(session)
            raise
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
        except GenerationCancelled:
            # The stop request already persisted the cancelled status and the
            # chapter it stopped on; a run that was told to stop is not a
            # failure and must not overwrite either of those.
            logger.info("report_generation_cancelled session_id=%s step=%s", session_id, session.current_step)
            return await self.sessions.get(session_id)
        except Exception as exc:
            logger.exception("report_generation_failed session_id=%s step=%s", session_id, session.current_step)
            session.status = ReportGenerationStatus.FAILED
            session.error = str(exc)
            session.updated_at = utc_now()
            await self.sessions.save(session)
            raise

    async def resolve_questions(
        self,
        session_id: str,
        request: ResolveQuestionsRequest,
    ) -> ReportGenerationSession:
        """Apply the user's decisions about a chapter's missing data.

        Each question is either supplied or dropped. A dropped metric leaves the
        plan entirely — the chapter must not mention it, nor explain its absence.
        The chapter is regenerated only once none of its questions are pending.
        """
        session = await self.sessions.get(session_id)
        by_id = {item.question_id: item for item in session.pending_questions}
        resolved_ids: set[str] = set()

        for resolution in request.resolutions:
            question = by_id.get(resolution.question_id)
            if question is None:
                raise KeyError(f"Pending report question not found: {resolution.question_id}")
            if resolution.action == "value":
                value = (resolution.value or "").strip()
                if not value:
                    raise UserInputRejected(f"补充值不能为空: {resolution.question_id}")
                question.resolution = "value"
                question.value = value
                question.note = (resolution.note or "").strip() or None
            elif resolution.action == "sql":
                await self._resolve_by_sql(question, resolution)
            elif resolution.action == "table":
                self._resolve_by_paste(question, resolution)
            else:
                question.resolution = "dropped"
                self._drop_metric(session, question)
            question.resolved_at = utc_now()
            resolved_ids.add(question.question_id)
            session.resolved_questions.append(question)

        session.pending_questions = [
            item for item in session.pending_questions if item.question_id not in resolved_ids
        ]
        session.updated_at = utc_now()
        logger.info(
            "questions_resolved session_id=%s resolved=%d remaining=%d dropped=%s",
            session_id,
            len(resolved_ids),
            len(session.pending_questions),
            [item.metric for item in session.resolved_questions if item.resolution == "dropped"] or "-",
        )
        if session.pending_questions:
            await self._save(session)
            return session

        session.status = ReportGenerationStatus.RUNNING
        await self._save(session)
        if request.auto_resume:
            return await self.start(session_id)
        return session

    async def _resolve_by_sql(
        self,
        question: UserQuestion,
        resolution: QuestionResolutionInput,
    ) -> None:
        """Run the user's query and settle the question with what it returned.

        The value is read here rather than taken from the request: the trial
        run in the question card and this one must agree, and only re-running
        the statement proves the number was not edited on the way back.
        """
        if self.connections is None:
            raise UserInputRejected("当前部署未启用数据源连接，请改为直接填写数值")
        shape = self._shape_for(question, resolution)
        connection_id = (resolution.connection_id or "").strip()
        if not connection_id:
            raise UserInputRejected(f"请先选择数据源: {resolution.question_id}")
        query = (resolution.query or "").strip()
        if not query:
            raise UserInputRejected(f"SQL 不能为空: {resolution.question_id}")
        try:
            result = await self.connections.query(connection_id, query, shape)
        except KeyError as exc:
            raise UserInputRejected(f"数据源不存在: {connection_id}") from exc
        if not result.success or result.extraction is None or not result.extraction.usable:
            detail = (result.extraction.error if result.extraction else None) or result.message
            raise UserInputRejected(f"取数失败：{detail}")
        found = result.extraction
        question.resolution = "sql"
        question.value = found.value
        question.dimensions = found.dimensions
        question.columns = found.columns
        question.rows = found.rows
        question.rows_truncated = found.truncated
        question.connection_id = connection_id
        question.connection_name = result.connection_name or None
        question.query = query
        question.note = (resolution.note or "").strip() or None
        logger.info(
            "question_resolved_by_sql question_id=%s metric=%s shape=%s connection_id=%s "
            "dimensions=%s rows=%d truncated=%s",
            question.question_id, question.metric, found.shape, connection_id,
            question.dimensions or "-", len(found.rows), found.truncated,
        )

    @staticmethod
    def _shape_for(question: UserQuestion, resolution: QuestionResolutionInput) -> str:
        """How to read the result of the user's query.

        The question already says whether the chapter needs one figure or a
        list, so the user is not asked to declare it a second time while
        writing their SQL. ``as_table`` is the correction: a question we
        classified as a single figure whose query returns a list is read as
        one, on the user's say-so.
        """
        return "table" if question.expected == "table" or resolution.as_table else "value"

    @staticmethod
    def _resolve_by_paste(
        question: UserQuestion,
        resolution: QuestionResolutionInput,
    ) -> None:
        """Settle a question with rows the user pasted in.

        Parsed here rather than trusted from the request for the same reason a
        SQL answer is re-run: the preview the user approved has to be this
        read of this text, not a second implementation of it in the browser.
        """
        text = (resolution.text or "").strip()
        if not text:
            raise UserInputRejected(f"粘贴的内容不能为空: {resolution.question_id}")
        try:
            parsed = parse_table(text)
        except TableParseError as exc:
            raise UserInputRejected(str(exc)) from exc
        question.resolution = "table"
        question.value = None
        question.columns = parsed.columns
        question.rows = parsed.rows
        question.rows_truncated = parsed.truncated
        question.note = (resolution.note or "").strip() or None
        logger.info(
            "question_resolved_by_paste question_id=%s metric=%s format=%s columns=%s "
            "rows=%d truncated=%s",
            question.question_id, question.metric, parsed.format,
            parsed.columns, len(parsed.rows), parsed.truncated,
        )

    def _drop_unanswerable(
        self,
        session: ReportGenerationSession,
        section: ChapterPlan,
        questions: list[UserQuestion],
    ) -> list[str]:
        """Give up on the data this chapter has asked for once too often.

        The user has already answered every round this chapter was allowed to
        ask; asking again would be the same question with the same answer. The
        metrics leave the plan the same way a user-dropped metric does, so the
        chapter is written without them and never explains their absence. The
        record stays in resolved_questions, which is how the run reports what
        it gave up on.
        """
        dropped: list[str] = []
        already = session.dropped_metrics.get(section.section_id, [])
        # A metric the user supplied a value for is never given up on: throwing
        # it away would discard data they typed in themselves, which is worse
        # than the loop this method exists to break.
        supplied = {
            (item.metric or "").strip()
            for item in session.resolved_questions
            if item.chapter_id == section.section_id and item.resolution in _SUPPLEMENT_SOURCE
        }
        for question in questions:
            metric = (question.metric or "").strip()
            if not metric or metric in already:
                # Nothing left to remove from the plan, so dropping it again
                # would not stop the chapter asking. Let the caller park.
                continue
            if metric in supplied:
                logger.warning(
                    "chapter_asked_for_supplied_metric session_id=%s section_id=%s metric=%s",
                    session.session_id, section.section_id, metric,
                )
                continue
            settled = question.model_copy(
                update={
                    "chapter_id": section.section_id,
                    "chapter_title": section.title,
                    "resolution": "dropped",
                    "note": f"连续 {self.max_chapter_attempts} 轮仍未取到，已自动移出报告",
                    "resolved_at": utc_now(),
                }
            )
            self._drop_metric(session, settled)
            session.resolved_questions.append(settled)
            dropped.append(metric)
        return dropped

    @staticmethod
    def _drop_metric(session: ReportGenerationSession, question: UserQuestion) -> None:
        """Remove a dropped metric from the plan so no chapter plans around it."""
        metric = (question.metric or "").strip()
        chapter_id = question.chapter_id
        if not metric or not chapter_id:
            return
        session.dropped_metrics.setdefault(chapter_id, [])
        if metric not in session.dropped_metrics[chapter_id]:
            session.dropped_metrics[chapter_id].append(metric)
        if session.plan is None:
            return
        for chapter in session.plan.chapters:
            if chapter.section_id == chapter_id:
                chapter.metrics = [item for item in chapter.metrics if item != metric]


    async def approve_plan(self, session_id: str) -> ReportGenerationSession:
        """Approve the current plan as-is and start chapter generation.

        The conversation layer calls this when the user says the plan is good;
        there is no form payload because the plan is edited by talking to it.
        """
        session = await self.sessions.get(session_id)
        if session.plan is None:
            raise ValueError("Report plan has not been generated")
        if session.plan.status != "awaiting_confirmation":
            raise ValueError(f"Report plan cannot be approved from status: {session.plan.status}")
        session.plan.status = "approved"
        session.title = session.plan.title
        session.status = ReportGenerationStatus.RUNNING
        session.current_step = "plan_approved"
        await self._save(session)
        return await self.start(session_id)

    _CANCELLABLE = {
        ReportGenerationStatus.CREATED,
        ReportGenerationStatus.AWAITING_CONFIRMATION,
        ReportGenerationStatus.RUNNING,
        ReportGenerationStatus.WAITING_USER,
    }
    _RESUMABLE = {ReportGenerationStatus.FAILED, ReportGenerationStatus.CANCELLED}

    async def cancel(self, session_id: str) -> ReportGenerationSession:
        """Stop a run in progress, keeping everything it has finished.

        This only flips the stored status. The run itself is cancelled
        cooperatively: it reads the status back at its next checkpoint and
        unwinds there, which is what keeps the session consistent enough to be
        resumed later by :meth:`retry`.
        """
        session = await self.sessions.get(session_id)
        if session.status not in self._CANCELLABLE:
            raise ValueError(f"Session cannot be cancelled from status: {session.status.value}")
        session.status = ReportGenerationStatus.CANCELLED
        session.current_step = "cancelled_by_user"
        session.error = None
        await self._save(session)
        logger.info(
            "report_generation_cancel_requested session_id=%s at_chapter=%s done=%d",
            session_id, session.current_chapter_id or "-", len(session.chapter_drafts),
        )
        return session

    async def _checkpoint(self, session_id: str) -> None:
        """Abort the run if the user has stopped it since the last checkpoint.

        The running loop holds its own copy of the session, so a stop request
        is only visible by reading the stored one back.
        """
        stored = await self.sessions.get(session_id)
        if stored.status == ReportGenerationStatus.CANCELLED:
            raise GenerationCancelled(session_id)

    async def retry(self, session_id: str) -> ReportGenerationSession:
        """Resume a run that a failure or a stop request cut short.

        Finished chapters are already on disk and get skipped, so a resume picks
        up at the chapter that was interrupted. That chapter's interrupted
        attempt is handed back: it died on the way to the model, not on the
        data, and it should not count against how many times the chapter is
        allowed to ask the user for numbers.
        """
        session = await self.sessions.get(session_id)
        if session.status not in self._RESUMABLE:
            raise ValueError(f"Session cannot be resumed from status: {session.status.value}")
        chapter_id = session.current_chapter_id
        session.error = None
        if session.pending_questions:
            # Stopped while it was asking for numbers. The questions are still
            # unanswered, so hand the user back the same card rather than
            # re-running the chapter and asking all over again.
            session.status = ReportGenerationStatus.WAITING_USER
            session.current_step = "await_supplements"
            await self._save(session, resume=True)
            logger.info(
                "report_generation_resumed session_id=%s waiting_questions=%d",
                session_id, len(session.pending_questions),
            )
            return session
        if chapter_id and chapter_id not in session.chapter_drafts:
            attempts = session.chapter_attempts.get(chapter_id, 0)
            if attempts:
                session.chapter_attempts[chapter_id] = attempts - 1
        session.status = ReportGenerationStatus.RUNNING
        await self._save(session, resume=True)
        logger.info(
            "report_generation_resumed session_id=%s from_chapter=%s done=%d",
            session_id, chapter_id or "-", len(session.chapter_drafts),
        )
        return await self.start(session_id)

    async def revise_plan(self, session_id: str, feedback: str) -> ReportGenerationSession:
        """Replace the pending plan with a new version built from user feedback."""
        session = await self.sessions.get(session_id)
        if session.plan is None:
            raise ValueError("Report plan has not been generated")
        if session.plan.status != "awaiting_confirmation":
            raise ValueError(f"Report plan cannot be revised from status: {session.plan.status}")
        if self._is_synthesized(session):
            # The conversation owns the structure here, so a revision may add or
            # drop chapters; the template is rebuilt from the result.
            session.plan = await self.planner.revise_outline(plan=session.plan, feedback=feedback)
            self._adopt_outline(session)
        else:
            if session.template_snapshot is None:
                raise ValueError("Report template snapshot is missing")
            session.plan = await self.planner.revise_plan(
                plan=session.plan,
                template=session.template_snapshot,
                data_sources=session.data_source_metadata,
                feedback=feedback,
            )
        session.title = session.plan.title
        session.status = ReportGenerationStatus.AWAITING_CONFIRMATION
        session.current_step = "await_plan_confirmation"
        await self._save(session)
        logger.info("report_plan_revised session_id=%s version=%d", session_id, session.plan.version)
        return session


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
            await self._checkpoint(session.session_id)
            session.current_chapter_id = section.section_id
            # This chapter is about to be attempted again, so its previous
            # questions are either answered or about to be re-asked.
            session.pending_questions = [
                item for item in session.pending_questions if item.chapter_id != section.section_id
            ]
            attempts = session.chapter_attempts.get(section.section_id, 0) + 1
            session.chapter_attempts[section.section_id] = attempts
            # Past the ask limit the chapter stops asking. Whatever it still
            # cannot find is dropped and the chapter is written without it: a
            # finished report with a named gap beats one that dies at chapter
            # two after the user has answered everything it asked for.
            stop_asking = attempts > self.max_chapter_attempts
            # Persist before the long agent run, otherwise nothing observing the
            # session can tell which chapter is currently being written.
            await self._save(session)
            template_section = template_sections.get(section.section_id)
            if template_section is None:
                raise ValueError(f"Template section not found: {section.section_id}")
            # One agent run writes the whole chapter, subsections included, so a
            # template's H2/H3 structure stays one unit of research and prose.
            subsections = [
                template_sections[item.section_id].model_copy(update={"title": item.title})
                for item in section.subsections
                if item.section_id in template_sections
            ]
            logger.info(
                "chapter_generation_started session_id=%s section_id=%s title=%s subsections=%d",
                session.session_id, section.section_id, section.title, len(subsections),
            )
            # The second pass happens only after a forced drop, and a drop
            # removes metrics from the chapter, so this cannot spin.
            for _ in range(2):
                writer_input = ChapterWriterInput(
                    section=template_section.model_copy(update={"title": section.title}),
                    subsections=subsections,
                    chapter_plan=section,
                    global_context=session.plan.global_context,
                    metrics=section.metrics,
                    report_outline=[item.title for item in session.plan.sections],
                    data_sources=data_sources,
                    user_instruction=session.instruction,
                    supplements=[
                        # A question without a named metric still carries a value the
                        # chapter needs, so label it with what was asked.
                        ChapterSupplement(
                            metric=item.metric or item.content,
                            source=_SUPPLEMENT_SOURCE[item.resolution],
                            value=item.value,
                            note=item.note,
                            dimensions=item.dimensions,
                            columns=item.columns,
                            rows=item.rows,
                            rows_truncated=item.rows_truncated,
                            connection_id=item.connection_id,
                            connection_name=item.connection_name,
                            query=item.query,
                        )
                        for item in session.resolved_questions
                        if item.chapter_id == section.section_id
                        and item.resolution in _SUPPLEMENT_SOURCE
                    ],
                    dropped_metrics=list(session.dropped_metrics.get(section.section_id, [])),
                )
                result = await self.writer.write(
                    writer_input,
                    session,
                    functools.partial(self._checkpoint, session.session_id),
                )
                if result.status != "waiting_user":
                    break
                if not stop_asking:
                    break
                dropped = self._drop_unanswerable(session, section, result.questions)
                if not dropped:
                    break
                logger.warning(
                    "chapter_metrics_force_dropped session_id=%s section_id=%s attempts=%d metrics=%s",
                    session.session_id, section.section_id, attempts, dropped,
                )
            if result.status == "waiting_user":
                # Stop here. A chapter is written only once all of its data is
                # settled, so the run waits for the user rather than moving on
                # and leaving this chapter to be revisited later.
                logger.info(
                    "chapter_waiting_user session_id=%s section_id=%s questions=%d metrics=%s",
                    session.session_id,
                    section.section_id,
                    len(result.questions),
                    [item.metric for item in result.questions if item.metric] or "-",
                )
                session.pending_questions = [
                    question.model_copy(
                        update={"chapter_id": section.section_id, "chapter_title": section.title}
                    )
                    for question in result.questions
                ]
                session.status = ReportGenerationStatus.WAITING_USER
                session.current_step = "await_supplements"
                await self._save(session)
                return session
            if result.status == "failed" or result.draft is None:
                raise ValueError(result.error or f"Chapter writer failed: {section.section_id}")
            session.chapter_drafts[section.section_id] = result.draft
            await self._save(session)
            logger.info(
                "chapter_generation_completed session_id=%s section_id=%s chars=%d evidence=%d content=%s",
                session.session_id,
                section.section_id,
                len(result.draft.content),
                len(result.draft.evidence),
                preview(result.draft.content, limit=500),
            )

        session.current_chapter_id = None
        session.status = ReportGenerationStatus.RUNNING
        session.current_step = "assemble_report"
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
        if session.template_snapshot is None and session.template_id:
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
        if session.template_snapshot is None:
            # Nothing to follow: the model proposes the structure, and the
            # agreed structure becomes the template everything downstream reads.
            session.plan = await self.planner.create_outline(
                instruction=session.instruction,
                data_sources=session.data_source_metadata,
                title=session.title,
            )
            self._adopt_outline(session)
        else:
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

    @staticmethod
    def _is_synthesized(session: ReportGenerationSession) -> bool:
        """Whether this report's structure came from the conversation."""
        snapshot = session.template_snapshot
        return bool(snapshot and snapshot.metadata.get("synthesized"))

    def _adopt_outline(self, session: ReportGenerationSession) -> None:
        """Rebuild the template from the plan just agreed.

        Regenerating rather than patching is what stops the two from drifting:
        the template cannot keep a chapter the plan no longer has.
        """
        template_id = session.template_id or f"template_{uuid4().hex}"
        session.template_snapshot = synthesize_template(
            template_id, session.plan.title, session.plan.chapters
        )
        session.template_id = template_id
        session.plan.template_id = template_id

    async def _build_data_source_metadata(self, dataset_ids: list[str]) -> list[DataSourceMetadata]:
        datasets = {dataset.dataset_id: dataset for dataset in await self.catalog.list_datasets()}
        result: list[DataSourceMetadata] = []
        for dataset_id in dataset_ids:
            dataset = datasets[dataset_id]
            try:
                sheet_models = await self.catalog.sheets(dataset_id)
                sheets = [sheet.model_dump(mode="json") for sheet in sheet_models]
                await self._attach_sheet_values(dataset_id, sheets)
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

    #: A column with at most this many distinct values is worth enumerating; a
    #: wider one is described by its range instead.
    _MAX_ENUM_VALUES = 30
    #: Upper bound on the enumeration scan, so a huge sheet cannot stall setup.
    _MAX_SCAN_ROWS = 5000

    async def _attach_sheet_values(self, dataset_id: str, sheets: list[dict]) -> None:
        """Enumerate what each column actually contains.

        Planning has to pick the report period and the reporting dimensions from
        the data, and it previously saw only five rows off the top of the first
        sheet — all carrying the same month, which hid both how far the data
        reached and which regions or grades existed. Distinct values answer both
        questions directly; wide columns fall back to a range.
        """
        for sheet in sheets:
            name = sheet.get("sheet_name")
            headers = [column.get("name") for column in sheet.get("columns") or []]
            if not headers:
                continue
            try:
                rows = await self._scan_rows(dataset_id, name)
            except Exception as exc:
                logger.warning(
                    "sheet_values_unavailable dataset_id=%s sheet=%s error=%s", dataset_id, name, exc
                )
                continue

            enums: dict[str, list[str]] = {}
            ranges: dict[str, dict[str, Any]] = {}
            for header in headers:
                values = {row[header] for row in rows if row.get(header) is not None}
                if not values:
                    continue
                if len(values) <= self._MAX_ENUM_VALUES:
                    enums[header] = [str(value) for value in self._ordered(values)]
                else:
                    ordered = self._ordered(values)
                    ranges[header] = {
                        "distinct": len(values),
                        "min": str(ordered[0]),
                        "max": str(ordered[-1]),
                    }
            if enums:
                sheet["value_enums"] = enums
            if ranges:
                sheet["value_ranges"] = ranges
            if len(rows) >= self._MAX_SCAN_ROWS:
                sheet["values_truncated"] = True

    @staticmethod
    def _ordered(values: set[Any]) -> list[Any]:
        """Sort numbers as numbers.

        Sorting them as text puts 997000 after 1000000 and reports a nonsense
        range, which the model would take at face value.
        """
        try:
            return sorted(values)
        except TypeError:
            return sorted(values, key=str)

    async def _scan_rows(self, dataset_id: str, sheet_name: str | None) -> list[dict]:
        rows: list[dict] = []
        while len(rows) < self._MAX_SCAN_ROWS:
            page = await self.catalog.read_rows(
                dataset_id, sheet_name, offset=len(rows), limit=500
            )
            rows.extend(page.rows)
            if not page.rows or not page.has_more:
                break
        return rows

    async def register_excel_dataset(
        self, filename: str, content: bytes, *, owner_id: str | None = None
    ) -> str:
        data_dir = settings.data_dir
        try:
            data_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            data_dir = Path(gettempdir()) / "report-agent-data"
            data_dir.mkdir(parents=True, exist_ok=True)
        dataset_id = f"excel_{uuid4().hex[:10]}"
        safe_filename = Path(filename).name
        data_path = data_dir / f"{dataset_id}_{safe_filename}"
        data_path.write_bytes(content)
        try:
            self.catalog.register(
                ExcelDataSource(path=data_path, dataset_id=dataset_id, name=safe_filename),
                owner_id=owner_id,
            )
        except Exception:
            data_path.unlink(missing_ok=True)
            raise
        return dataset_id

    async def _save(self, session: ReportGenerationSession, *, resume: bool = False) -> None:
        """Persist the session, refusing to write over a stop request.

        A run that is mid-chapter when the user stops it can still be holding a
        stale in-memory session whose status is ``running``. Writing that back
        would silently un-cancel the run, so every save doubles as a checkpoint
        and only an explicit resume is allowed to leave the cancelled state.
        """
        if not resume and session.status != ReportGenerationStatus.CANCELLED:
            try:
                stored = await self.sessions.get(session.session_id)
            except KeyError:
                stored = None  # first save of a brand-new session
            if stored is not None and stored.status == ReportGenerationStatus.CANCELLED:
                raise GenerationCancelled(session.session_id)
        session.updated_at = utc_now()
        await self.sessions.save(session)
