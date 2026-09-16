import asyncio
import json
import tempfile
from pathlib import Path

from openpyxl import Workbook

from app.conversations.orchestrator import ConversationOrchestrator
from app.core.ports import LlmService
from app.core.reports import ReportGenerationStatus
from app.data.catalog import DataCatalog
from app.infrastructure.artifact_store import InMemoryArtifactStore
from app.infrastructure.conversation_repositories import InMemoryConversationRepository
from app.infrastructure.report_repositories import (
    InMemoryReportSessionRepository,
    InMemoryReportTemplateRepository,
)
from app.reporting.assembler import ReportAssembler
from app.core.reports import ChapterDraft, ChapterWriterResult
from app.reporting.chapter_writer import ChapterWriter, StubChapterWriter
from app.reporting.planner import ReportPlanner
from app.reporting.renderer import MarkdownReportRenderer
from app.reporting.report_generation import ReportGenerationService
from app.reporting.template_parser import ReportTemplateParser

TEMPLATE_BYTES = "# 经营分析报告\n\n## 一、经营概况\n概况正文\n\n## 二、风险情况\n风险正文".encode()


class ScriptedLlm(LlmService):
    """Returns queued payloads so intent routing and revision are deterministic."""

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.prompts: list[list[dict]] = []

    async def complete(self, messages, tools):
        self.prompts.append(messages)
        return {"content": self.responses.pop(0) if self.responses else "{}"}


def excel_bytes() -> bytes:
    path = Path(tempfile.mkdtemp()) / "data.xlsx"
    workbook = Workbook()
    workbook.active.append(["value"])
    workbook.active.append([1])
    workbook.save(path)
    return path.read_bytes()


def build_orchestrator(llm: LlmService | None = None, writer=None) -> ConversationOrchestrator:
    reports = ReportGenerationService(
        sessions=InMemoryReportSessionRepository(),
        templates=InMemoryReportTemplateRepository(),
        template_parser=ReportTemplateParser(),
        planner=ReportPlanner(llm=llm),
        writer=writer or StubChapterWriter(),
        assembler=ReportAssembler(),
        renderer=MarkdownReportRenderer(),
        artifact_store=InMemoryArtifactStore(),
        catalog=DataCatalog(),
    )
    return ConversationOrchestrator(
        conversations=InMemoryConversationRepository(), reports=reports, llm=llm
    )


async def send(orchestrator, conversation_id, text, **files):
    message = await orchestrator.submit_message(conversation_id, text, **files)
    return await orchestrator.process_message(conversation_id, message.message_id)


def test_uploading_files_in_a_message_creates_a_plan():
    async def run():
        orchestrator = build_orchestrator()
        conversation = await orchestrator.create_conversation("local-user")
        replies = await send(
            orchestrator,
            conversation.conversation_id,
            "生成 2026 年一季度经营分析报告",
            template_filename="模板.md",
            template_content=TEMPLATE_BYTES,
            template_content_type="text/markdown",
            data_filename="data.xlsx",
            data_content=excel_bytes(),
        )

        assert [reply.kind for reply in replies] == ["plan"]
        assert replies[0].payload["plan"]["version"] == 1
        assert len(replies[0].payload["plan"]["chapters"]) == 2

        detail = await orchestrator.get_detail(conversation.conversation_id)
        assert detail.conversation.report_session_id is not None
        assert detail.report_session.status == ReportGenerationStatus.AWAITING_CONFIRMATION
        # The thread title comes from the first user message, not a form field.
        assert detail.conversation.title.startswith("生成 2026")

    asyncio.run(run())


def test_a_message_without_attachments_asks_for_them():
    async def run():
        orchestrator = build_orchestrator()
        conversation = await orchestrator.create_conversation("local-user")
        replies = await send(orchestrator, conversation.conversation_id, "帮我写个报告")
        assert [reply.kind for reply in replies] == ["text"]
        assert "上传" in replies[0].content

    asyncio.run(run())


def test_plan_is_revised_by_talking_to_it():
    async def run():
        revised_plan = json.dumps(
            {
                "title": "2026 一季度经营分析报告",
                "global_context": {"report_period": "2025 上半年", "dimensions": {}},
                "chapters": [{"section_id": "section_1", "title": "一、经营概况", "metrics": ["营收"]}],
            },
            ensure_ascii=False,
        )
        # 1: initial plan, 2: intent classification, 3: the revision itself.
        llm = ScriptedLlm(
            [
                json.dumps(
                    {
                        "title": "经营分析报告",
                        "global_context": {"report_period": "2026Q1", "dimensions": {}},
                        "chapters": [
                            {"section_id": "section_1", "title": "一、经营概况", "metrics": []},
                            {"section_id": "section_2", "title": "二、风险情况", "metrics": []},
                        ],
                    },
                    ensure_ascii=False,
                ),
                json.dumps({"intent": "revise_plan"}),
                revised_plan,
            ]
        )
        orchestrator = build_orchestrator(llm)
        conversation = await orchestrator.create_conversation("local-user")
        await send(
            orchestrator,
            conversation.conversation_id,
            "生成经营分析报告",
            template_filename="模板.md",
            template_content=TEMPLATE_BYTES,
            template_content_type="text/markdown",
            data_filename="data.xlsx",
            data_content=excel_bytes(),
        )

        replies = await send(
            orchestrator, conversation.conversation_id, "去掉风险章节，报告期间改成 2025 上半年"
        )

        assert [reply.kind for reply in replies] == ["plan"]
        plan = replies[0].payload["plan"]
        assert plan["version"] == 2
        assert plan["status"] == "awaiting_confirmation"
        assert [chapter["section_id"] for chapter in plan["chapters"]] == ["section_1"]
        assert plan["global_context"]["report_period"] == "2025 上半年"
        # Both plan versions stay in the thread, so the user can look back.
        detail = await orchestrator.get_detail(conversation.conversation_id)
        assert [message.payload["plan"]["version"] for message in detail.messages if message.kind == "plan"] == [1, 2]

    asyncio.run(run())


def test_approving_in_chat_runs_generation_to_completion():
    async def run():
        orchestrator = build_orchestrator()
        conversation = await orchestrator.create_conversation("local-user")
        await send(
            orchestrator,
            conversation.conversation_id,
            "生成经营分析报告",
            template_filename="模板.md",
            template_content=TEMPLATE_BYTES,
            template_content_type="text/markdown",
            data_filename="data.xlsx",
            data_content=excel_bytes(),
        )

        replies = await send(orchestrator, conversation.conversation_id, "确认，开始生成")

        assert [reply.kind for reply in replies] == ["progress", "report"]
        assert replies[1].payload["artifacts"]
        # The progress message is posted before the run and updated after it,
        # so the thread is never silent and never stale.
        stored = await orchestrator.conversations.list_messages(conversation.conversation_id)
        progress = next(item for item in stored if item.kind == "progress")
        assert progress.payload["chapters"]
        assert all(chapter["completed"] for chapter in progress.payload["chapters"])
        detail = await orchestrator.get_detail(conversation.conversation_id)
        assert detail.report_session.status == ReportGenerationStatus.COMPLETED

    asyncio.run(run())


def test_second_report_in_one_conversation_is_refused():
    async def run():
        orchestrator = build_orchestrator()
        conversation = await orchestrator.create_conversation("local-user")
        for _ in range(2):
            replies = await send(
                orchestrator,
                conversation.conversation_id,
                "生成经营分析报告",
                template_filename="模板.md",
                template_content=TEMPLATE_BYTES,
                template_content_type="text/markdown",
                data_filename="data.xlsx",
                data_content=excel_bytes(),
            )
        assert replies[0].kind == "text"
        assert "新建" in replies[0].content

    asyncio.run(run())


def test_a_question_asked_before_any_report_gets_answered():
    async def run():
        llm = ScriptedLlm(["净息差 = 利息净收入 / 平均生息资产。"])
        orchestrator = build_orchestrator(llm)
        conversation = await orchestrator.create_conversation("local-user")
        replies = await send(orchestrator, conversation.conversation_id, "净息差怎么算？")
        assert [reply.kind for reply in replies] == ["text"]
        assert "利息净收入" in replies[0].content

    asyncio.run(run())


def test_transport_failures_are_reported_in_plain_language():
    async def run():
        class BrokenLlm(LlmService):
            async def complete(self, messages, tools):
                raise ConnectionError("Connection error.")

        orchestrator = build_orchestrator(BrokenLlm())
        conversation = await orchestrator.create_conversation("local-user")
        replies = await send(
            orchestrator,
            conversation.conversation_id,
            "生成经营分析报告",
            template_filename="模板.md",
            template_content=TEMPLATE_BYTES,
            template_content_type="text/markdown",
            data_filename="data.xlsx",
            data_content=excel_bytes(),
        )
        assert [reply.kind for reply in replies] == ["error"]
        assert "模型服务连接失败" in replies[0].content

    asyncio.run(run())


def test_a_chapter_missing_data_asks_before_the_next_chapter_starts():
    async def run():
        from app.core.reports import ChapterDraft, ChapterWriterResult, UserQuestion
        from app.reporting.chapter_writer import ChapterWriter

        class PartialWriter(ChapterWriter):
            async def write(self, input, session, checkpoint=None):
                section_id = input.section.section_id
                if section_id == "section_2":
                    return ChapterWriterResult(
                        status="waiting_user",
                        questions=[
                            UserQuestion(
                                question_id="q1",
                                metric="2025年同期交易金额",
                                expected="value",
                                content="需要历史同期数据才能算同比",
                            )
                        ],
                    )
                return ChapterWriterResult(
                    status="completed",
                    draft=ChapterDraft(
                        chapter_id=section_id,
                        section_id=section_id,
                        title=input.section.title,
                        content="正文",
                    ),
                )

        orchestrator = build_orchestrator()
        orchestrator.reports.writer = PartialWriter()
        conversation = await orchestrator.create_conversation("local-user")
        await send(
            orchestrator,
            conversation.conversation_id,
            "生成经营分析报告",
            template_filename="模板.md",
            template_content=TEMPLATE_BYTES,
            template_content_type="text/markdown",
            data_filename="data.xlsx",
            data_content=excel_bytes(),
        )

        replies = await send(orchestrator, conversation.conversation_id, "确认，开始生成")

        # The run stops at that chapter and asks, naming the metric.
        assert [reply.kind for reply in replies] == ["progress", "question"]
        question = replies[1]
        assert question.payload["chapters"][0]["title"] == "二、风险情况"
        assert question.payload["chapters"][0]["questions"][0]["metric"] == "2025年同期交易金额"
        assert "缺少数据" in question.content

        detail = await orchestrator.get_detail(conversation.conversation_id)
        assert detail.report_session.status == ReportGenerationStatus.WAITING_USER
        # The chapters that had enough data are already drafted and visible.
        assert set(detail.report_session.chapter_drafts) == {"section_1"}

    asyncio.run(run())


class FailsOnceMidRun(ChapterWriter):
    """Writes chapters normally, except the Nth call blows up the way a dead
    gateway does: no result, no questions, just an exception."""

    def __init__(self, fail_on_call: int) -> None:
        self.fail_on_call = fail_on_call
        self.written: list[str] = []
        self.calls = 0

    async def write(self, input, session, checkpoint=None) -> ChapterWriterResult:
        self.calls += 1
        if self.calls == self.fail_on_call:
            raise RuntimeError("504 Gateway Time-out")
        self.written.append(input.section.section_id)
        return ChapterWriterResult(
            status="completed",
            draft=ChapterDraft(
                chapter_id=input.section.section_id,
                section_id=input.section.section_id,
                title=input.section.title,
                content="正文",
            ),
        )


PLAN_REPLY = json.dumps(
    {
        "title": "经营分析报告",
        "global_context": {"report_period": "2026Q1"},
        "chapters": [
            {"section_id": "section_1", "title": "一、经营概况", "metrics": ["A"], "subsections": []},
            {"section_id": "section_2", "title": "二、风险情况", "metrics": ["B"], "subsections": []},
        ],
    },
    ensure_ascii=False,
)


async def failed_run(llm, writer):
    """Drive a conversation to a run that died part-way."""
    orchestrator = build_orchestrator(llm, writer)
    conversation = await orchestrator.create_conversation("local-user")
    await send(
        orchestrator,
        conversation.conversation_id,
        "生成经营分析报告",
        template_filename="模板.md",
        template_content=TEMPLATE_BYTES,
        data_filename="数据.xlsx",
        data_content=excel_bytes(),
    )
    await send(orchestrator, conversation.conversation_id, "确认，开始生成")
    session = await orchestrator.reports.sessions.get(
        (await orchestrator.conversations.get(conversation.conversation_id)).report_session_id
    )
    assert session.status == ReportGenerationStatus.FAILED
    return orchestrator, conversation, session


def test_a_failed_run_never_claims_it_restarted_itself():
    """The model cannot restart anything, and left to chat it says it did."""

    async def run():
        llm = ScriptedLlm([
            PLAN_REPLY,
            '{"intent": "approve_plan"}',
            '{"intent": "chat"}',
            "我已重新发起生成，完成后会通知您。",  # the lie, if it were ever asked
        ])
        orchestrator, conversation, _ = await failed_run(llm, FailsOnceMidRun(fail_on_call=2))

        replies = await send(orchestrator, conversation.conversation_id, "现在怎么样了")

        assert len(replies) == 1
        reply = replies[0].content
        assert "重新发起" not in reply
        assert "我没有自动重跑" in reply
        assert "已经写完 1 章" in reply

    asyncio.run(run())


def test_retrying_a_failed_run_resumes_instead_of_rewriting():
    async def run():
        llm = ScriptedLlm([PLAN_REPLY, '{"intent": "approve_plan"}', '{"intent": "retry"}'])
        writer = FailsOnceMidRun(fail_on_call=2)
        orchestrator, conversation, failed = await failed_run(llm, writer)
        assert writer.written == ["section_1"]

        replies = await send(orchestrator, conversation.conversation_id, "重试")

        session = await orchestrator.reports.sessions.get(failed.session_id)
        assert session.status == ReportGenerationStatus.COMPLETED
        assert session.error is None
        # The finished chapter is not written a second time.
        assert writer.written == ["section_1", "section_2"]
        assert [item.kind for item in replies] == ["progress", "report"]

    asyncio.run(run())


def test_retry_without_the_model_still_lands_on_a_keyword():
    """Intent classification is best-effort; the fallback must not send a
    retry into free-form chat, which is where the lying happens."""

    async def run():
        writer = FailsOnceMidRun(fail_on_call=2)
        orchestrator, conversation, failed = await failed_run(None, writer)

        await send(orchestrator, conversation.conversation_id, "接着跑")

        session = await orchestrator.reports.sessions.get(failed.session_id)
        assert session.status == ReportGenerationStatus.COMPLETED

    asyncio.run(run())


def test_a_gateway_error_page_is_not_pasted_into_the_thread():
    orchestrator = build_orchestrator()
    html = (
        "<html>\n<head><title>504 Gateway Time-out</title></head>\n"
        "<body bgcolor=\"white\">\n<center><h1>504 Gateway Time-out</h1></center>\n</body>\n</html>"
    )
    text = orchestrator._failure_text(html)
    assert "<html" not in text
    assert "504 Gateway Time-out" in text
    assert orchestrator._failure_text(None) == "未知原因"


def test_a_plan_that_fails_can_be_retried_without_re_uploading():
    """Planning is a slow model call, and the provider drops one now and then.
    Losing the upload to that used to be the user's problem to fix."""

    class FailsFirstPlan(LlmService):
        def __init__(self) -> None:
            self.calls = 0

        async def complete(self, messages, tools):
            self.calls += 1
            if self.calls == 1:
                raise ConnectionError("Connection error.")
            return {"content": PLAN_REPLY}

    async def run():
        llm = FailsFirstPlan()
        orchestrator = build_orchestrator(llm)
        conversation = await orchestrator.create_conversation("local-user")
        replies = await send(
            orchestrator,
            conversation.conversation_id,
            "生成经营分析报告",
            template_filename="模板.md",
            template_content=TEMPLATE_BYTES,
            template_content_type="text/markdown",
            data_filename="data.xlsx",
            data_content=excel_bytes(),
        )
        assert [reply.kind for reply in replies] == ["error"]

        # The conversation knows about its report even though planning never
        # finished, which is what makes the next line possible.
        conversation = await orchestrator.conversations.get(conversation.conversation_id)
        assert conversation.report_session_id
        session = await orchestrator.reports.sessions.get(conversation.report_session_id)
        assert session.status == ReportGenerationStatus.FAILED

        replies = await send(orchestrator, conversation.conversation_id, "重试")

        assert [reply.kind for reply in replies][-1] == "plan"
        session = await orchestrator.reports.sessions.get(conversation.report_session_id)
        assert session.plan is not None
        assert session.status == ReportGenerationStatus.AWAITING_CONFIRMATION
        # The template was parsed before the failure and is not re-parsed.
        assert session.template_snapshot is not None

    asyncio.run(run())


def test_stopping_a_run_says_so_in_the_thread_and_keeps_the_progress():
    """The user pressed 停止 here, so this is where they should be able to read
    what state the report was left in."""

    async def run():
        writer = FailsOnceMidRun(fail_on_call=2)
        orchestrator, conversation, failed = await failed_run(None, writer)
        # A failed run is cancellable the same way a running one is; what
        # matters is that the stop is recorded and the drafts survive.
        session = await orchestrator.reports.sessions.get(failed.session_id)
        session.status = ReportGenerationStatus.RUNNING
        await orchestrator.reports.sessions.save(session)

        stopped = await orchestrator.cancel_generation(conversation.conversation_id)

        assert stopped.status == ReportGenerationStatus.CANCELLED
        assert list(stopped.chapter_drafts) == ["section_1"]
        messages = await orchestrator.conversations.list_messages(conversation.conversation_id)
        last = messages[-1]
        assert last.kind == "progress"
        assert "已停止生成" in last.content and "1/2" in last.content

    asyncio.run(run())


def test_saying_continue_after_a_stop_picks_up_the_unwritten_chapter():
    """A stopped run is not a dead end, and "继续" is what a user actually says."""

    async def run():
        writer = FailsOnceMidRun(fail_on_call=2)
        orchestrator, conversation, failed = await failed_run(None, writer)
        session = await orchestrator.reports.sessions.get(failed.session_id)
        session.status = ReportGenerationStatus.RUNNING
        await orchestrator.reports.sessions.save(session)
        await orchestrator.cancel_generation(conversation.conversation_id)

        await send(orchestrator, conversation.conversation_id, "继续")

        resumed = await orchestrator.reports.sessions.get(failed.session_id)
        assert resumed.status == ReportGenerationStatus.COMPLETED
        # section_1 was on disk before the stop and is not written twice.
        assert writer.written == ["section_1", "section_2"]

    asyncio.run(run())
