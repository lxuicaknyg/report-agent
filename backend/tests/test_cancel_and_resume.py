"""Stopping a run must keep its progress, and resuming must not redo it.

Cancellation is cooperative: the stop request only flips the stored status and
the run notices at its next checkpoint. These tests pin the two things that
makes fragile — that a run cannot un-cancel itself by saving stale state, and
that what it had already finished survives to the resume.
"""

import asyncio
import tempfile
from pathlib import Path

from openpyxl import Workbook

from app.core.reports import (
    ChapterDraft,
    ChapterWriterInput,
    ChapterWriterResult,
    CreateReportGenerationRequest,
    GenerationCancelled,
    ReportGenerationStatus,
    UserQuestion,
)
from app.data.catalog import DataCatalog
from app.data.sources.excel import ExcelDataSource
from app.infrastructure.artifact_store import InMemoryArtifactStore
from app.infrastructure.report_repositories import (
    InMemoryReportSessionRepository,
    InMemoryReportTemplateRepository,
)
from app.reporting.assembler import ReportAssembler
from app.reporting.chapter_writer import ChapterWriter
from app.reporting.planner import ReportPlanner
from app.reporting.renderer import MarkdownReportRenderer
from app.reporting.report_generation import ReportGenerationService
from app.reporting.template_parser import ReportTemplateParser

TEMPLATE = """# 报告

## 一、经营概况
概况正文

## 二、风险情况
风险正文

## 三、展望
展望正文
""".encode()


def excel_bytes() -> bytes:
    path = Path(tempfile.mkdtemp()) / "data.xlsx"
    workbook = Workbook()
    workbook.active.append(["value"])
    workbook.active.append([1])
    workbook.save(path)
    return path.read_bytes()


def build_service(writer: ChapterWriter):
    return ReportGenerationService(
        sessions=InMemoryReportSessionRepository(),
        templates=InMemoryReportTemplateRepository(),
        template_parser=ReportTemplateParser(),
        planner=ReportPlanner(llm=None),
        writer=writer,
        assembler=ReportAssembler(),
        renderer=MarkdownReportRenderer(),
        artifact_store=InMemoryArtifactStore(),
        catalog=DataCatalog(),
    )


def draft(input: ChapterWriterInput, body: str = "章节正文。") -> ChapterWriterResult:
    return ChapterWriterResult(
        status="completed",
        draft=ChapterDraft(
            chapter_id=input.section.section_id,
            section_id=input.section.section_id,
            title=input.section.title,
            content=body,
        ),
    )


class StopsOnNthChapter(ChapterWriter):
    """Writes chapters, and calls the service's stop hook partway through one.

    Standing in for the user pressing 停止 while a chapter is being written:
    the stop lands mid-run, and the checkpoint the writer awaits next is what
    has to notice it.
    """

    def __init__(self, stop_at: int) -> None:
        self.stop_at = stop_at
        self.written: list[str] = []
        self.stop: callable = lambda: None

    async def write(self, input, session, checkpoint=None) -> ChapterWriterResult:
        if len(self.written) == self.stop_at:
            await self.stop()
            # The real agent checks between metrics; here one call stands for
            # the whole research phase.
            if checkpoint is not None:
                await checkpoint()
        self.written.append(input.section.section_id)
        return draft(input)


async def planned_session(service, dataset_id: str):
    """A session with a plan on the table, not yet writing.

    Chapters only start once the plan is approved, which is also the point
    where the session id is known — the writer needs it to stop its own run.
    """
    template = await service.upload_template("t.md", TEMPLATE, "text/markdown")
    path = Path(tempfile.mkdtemp()) / "data.xlsx"
    path.write_bytes(excel_bytes())
    service.catalog.register(ExcelDataSource(path, dataset_id, "data.xlsx"))
    return await service.create_session(
        CreateReportGenerationRequest(
            template_id=template.template_id,
            dataset_ids=[dataset_id],
            instruction="生成",
        ),
        user_id="local-user",
    )


async def started_session(service, dataset_id: str):
    session = await planned_session(service, dataset_id)
    return await service.approve_plan(session.session_id)


def test_stopping_mid_run_keeps_the_chapters_already_written():
    async def run():
        writer = StopsOnNthChapter(stop_at=1)
        service = build_service(writer)
        pending = await planned_session(service, "excel_cancel_1")
        # The stop fires from inside the second chapter, so the first is done
        # and the third is never reached.
        writer.stop = lambda: service.cancel(pending.session_id)

        session = await service.approve_plan(pending.session_id)

        assert session.status == ReportGenerationStatus.CANCELLED
        assert session.current_step == "cancelled_by_user"
        assert writer.written == ["section_1"]
        assert list(session.chapter_drafts) == ["section_1"]
        # The chapter it stopped on is the one a resume picks up at.
        assert session.current_chapter_id == "section_2"
        assert session.error is None

    asyncio.run(run())


def test_a_stopped_run_resumes_at_the_chapter_it_stopped_on():
    async def run():
        writer = StopsOnNthChapter(stop_at=1)
        service = build_service(writer)
        pending = await planned_session(service, "excel_cancel_2")
        writer.stop = lambda: service.cancel(pending.session_id)
        session = await service.approve_plan(pending.session_id)
        assert session.status == ReportGenerationStatus.CANCELLED

        # Nothing left to stop it this time.
        writer.stop_at = -1
        resumed = await service.retry(session.session_id)

        assert resumed.status == ReportGenerationStatus.COMPLETED
        # section_1 was already on disk and is not rewritten.
        assert writer.written == ["section_1", "section_2", "section_3"]
        assert len(resumed.chapter_drafts) == 3
        assert resumed.artifacts

    asyncio.run(run())


def test_a_stale_save_from_the_interrupted_run_cannot_un_cancel_it():
    async def run():
        service = build_service(_NeverCalled())
        session = await started_session(service, "excel_cancel_3")
        # The run finished, so stage a running session by hand: this is the
        # copy an in-flight run would still be holding.
        stale = await service.sessions.get(session.session_id)
        stale.status = ReportGenerationStatus.RUNNING
        await service.sessions.save(stale)

        await service.cancel(session.session_id)
        stale.chapter_drafts = {}
        try:
            await service._save(stale)
        except GenerationCancelled as exc:
            assert exc.session_id == session.session_id
        else:
            raise AssertionError("a stale save must not overwrite a stop request")

        stored = await service.sessions.get(session.session_id)
        assert stored.status == ReportGenerationStatus.CANCELLED
        assert stored.chapter_drafts

    asyncio.run(run())


class _NeverCalled(ChapterWriter):
    async def write(self, input, session, checkpoint=None) -> ChapterWriterResult:
        return draft(input)


class AsksThenStops(ChapterWriter):
    """Asks the user for a number on its first run, then writes."""

    def __init__(self) -> None:
        self.calls = 0

    async def write(self, input, session, checkpoint=None) -> ChapterWriterResult:
        self.calls += 1
        if self.calls == 1:
            return ChapterWriterResult(
                status="waiting_user",
                questions=[
                    UserQuestion(
                        question_id="question_1",
                        chapter_id=input.section.section_id,
                        metric="累计交易金额",
                        content="缺少累计交易金额",
                    )
                ],
            )
        return draft(input)


def test_stopping_while_it_waits_on_the_user_resumes_back_into_waiting():
    async def run():
        writer = AsksThenStops()
        service = build_service(writer)
        session = await started_session(service, "excel_cancel_4")
        assert session.status == ReportGenerationStatus.WAITING_USER
        assert session.pending_questions

        await service.cancel(session.session_id)
        resumed = await service.retry(session.session_id)

        # The question is still unanswered, so the resume hands it back rather
        # than re-running the chapter and asking all over again.
        assert resumed.status == ReportGenerationStatus.WAITING_USER
        assert [item.question_id for item in resumed.pending_questions] == ["question_1"]
        assert writer.calls == 1

    asyncio.run(run())


def test_a_finished_report_cannot_be_stopped():
    async def run():
        service = build_service(_NeverCalled())
        session = await started_session(service, "excel_cancel_5")
        assert session.status == ReportGenerationStatus.COMPLETED
        try:
            await service.cancel(session.session_id)
        except ValueError as exc:
            assert "completed" in str(exc)
        else:
            raise AssertionError("a completed report has nothing to stop")

    asyncio.run(run())
