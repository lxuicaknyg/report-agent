from __future__ import annotations

import json
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

from ..core.conversations import (
    Conversation,
    ConversationDetail,
    Message,
    MessageAttachment,
    MessageIntent,
)
from ..core.models import utc_now
from ..core.ports import LlmService
from ..core.reports import (
    CreateReportGenerationRequest,
    QuestionResolutionInput,
    ReportGenerationSession,
    ReportGenerationStatus,
    ResolveQuestionsRequest,
)
from ..infrastructure.logging import preview
from ..reporting.report_generation import ReportGenerationService
from .repository import ConversationRepository

logger = logging.getLogger(__name__)

APPROVAL_MARKERS = (
    "确认", "同意", "可以了", "没问题", "就这样", "开始生成", "开始吧",
    "生成吧", "执行吧", "没有问题", "ok", "okay", "approve", "go ahead",
)
RETRY_MARKERS = (
    "重试", "再试", "继续", "接着", "重跑", "再跑", "retry", "resume",
)
REVISION_MARKERS = (
    "改", "修改", "调整", "删掉", "删除", "去掉", "不要", "增加", "加上",
    "补充", "换成", "替换", "重排", "调换", "改成",
)


class ConversationOrchestrator:
    """Turns chat messages into report-generation actions.

    This is the only write path in the system: the UI renders the message
    stream and posts text, and every state transition — creating the report,
    revising the plan, approving it, answering a chapter question — is decided
    here from the message plus the conversation's current state.
    """

    def __init__(
        self,
        conversations: ConversationRepository,
        reports: ReportGenerationService,
        llm: LlmService | None = None,
    ) -> None:
        self.conversations = conversations
        self.reports = reports
        self.llm = llm

    # ── conversation lifecycle ────────────────────────────────────────────

    async def create_conversation(self, user_id: str, title: str | None = None) -> Conversation:
        conversation = Conversation(
            conversation_id=f"conv_{uuid4().hex}",
            user_id=user_id,
            title=(title or "").strip() or "新会话",
        )
        await self.conversations.save(conversation)
        return conversation

    async def list_conversations(self, user_id: str | None = None) -> list[Conversation]:
        items = await self.conversations.list(user_id)
        return sorted(items, key=lambda item: item.updated_at, reverse=True)

    async def get_detail(self, conversation_id: str) -> ConversationDetail:
        conversation = await self.conversations.get(conversation_id)
        messages = await self.conversations.list_messages(conversation_id)
        session = await self._load_session(conversation)
        return ConversationDetail(conversation=conversation, messages=messages, report_session=session)

    async def delete_conversation(self, conversation_id: str) -> None:
        await self.conversations.delete(conversation_id)

    async def cancel_generation(self, conversation_id: str) -> ReportGenerationSession:
        """Stop the report this conversation is generating.

        The stop is recorded in the thread as well as on the session: the user
        asked for it here, so this is where they should be able to read what
        state the report was left in.
        """
        conversation = await self.conversations.get(conversation_id)
        if not conversation.report_session_id:
            raise KeyError(f"Conversation has no report session: {conversation_id}")
        session = await self.reports.cancel(conversation.report_session_id)
        done = len(session.chapter_drafts)
        total = len(session.plan.sections) if session.plan else 0
        progress = f"已完成 {done}/{total} 章" if total else f"已完成 {done} 章"
        await self._emit(
            conversation,
            kind="progress",
            content=f"已停止生成，{progress}，进度已保留。说「继续」就从中断的章节接着写。",
        )
        return session

    # ── message intake ────────────────────────────────────────────────────

    async def submit_message(
        self,
        conversation_id: str,
        text: str,
        *,
        template_filename: str | None = None,
        template_content: bytes | None = None,
        template_content_type: str | None = None,
        data_filename: str | None = None,
        data_content: bytes | None = None,
        resolutions: list[dict[str, Any]] | None = None,
    ) -> Message:
        """Persist the user's turn, resolving any uploads into stored resources.

        Upload parsing happens here so a bad file fails the request directly.
        The slow model work runs afterwards in ``process_message``.
        """
        conversation = await self.conversations.get(conversation_id)
        content = text.strip()
        if not content:
            raise ValueError("Message text is required")

        attachments: list[MessageAttachment] = []
        payload: dict[str, Any] = {"resolutions": resolutions} if resolutions else {}
        if template_content and template_filename:
            template = await self.reports.upload_template(
                template_filename, template_content, template_content_type
            )
            payload["template_id"] = template.template_id
            attachments.append(
                MessageAttachment(filename=template_filename, kind="template", size=len(template_content))
            )
        if data_content and data_filename:
            dataset_id = await self.reports.register_excel_dataset(data_filename, data_content)
            payload["dataset_ids"] = [dataset_id]
            attachments.append(
                MessageAttachment(filename=data_filename, kind="data", size=len(data_content))
            )

        message = Message(
            message_id=f"msg_{uuid4().hex}",
            conversation_id=conversation_id,
            role="user",
            kind="text",
            content=content,
            payload=payload,
            attachments=attachments,
        )
        await self.conversations.append_message(message)
        logger.info(
            "user_message conversation_id=%s message_id=%s attachments=%s text=%s",
            conversation_id,
            message.message_id,
            [item.filename for item in attachments] or "-",
            preview(content),
        )

        if conversation.title in {"", "新会话"}:
            conversation.title = content[:20] + ("…" if len(content) > 20 else "")
        conversation.updated_at = utc_now()
        await self.conversations.save(conversation)
        return message

    async def process_message(self, conversation_id: str, message_id: str) -> list[Message]:
        """Act on a submitted user message and append the assistant's turns."""
        conversation = await self.conversations.get(conversation_id)
        messages = await self.conversations.list_messages(conversation_id)
        user_message = next((item for item in messages if item.message_id == message_id), None)
        if user_message is None:
            raise KeyError(f"Message not found: {message_id}")

        try:
            session = await self._load_session(conversation)
            intent = await self._classify(conversation, session, user_message, messages)
            logger.info(
                "conversation_intent conversation_id=%s intent=%s status=%s",
                conversation_id, intent.value, session.status.value if session else "none",
            )
            return await self._act(conversation, session, user_message, intent, messages)
        except Exception as exc:
            logger.exception("conversation_processing_failed conversation_id=%s", conversation_id)
            return [await self._emit(conversation, kind="error", content=self._error_text(exc))]

    def _error_text(self, exc: Exception) -> str:
        """User-facing failure text. The full traceback stays in the log."""
        name = type(exc).__name__
        if "Connection" in name or "Timeout" in name:
            return "模型服务连接失败。说「重试」可以从中断的地方接着写。"
        detail = self._failure_text(str(exc)) if str(exc).strip() else f"处理失败：{name}"
        return f"{detail}（详细原因见后端日志）"

    # ── intent routing ────────────────────────────────────────────────────

    async def _classify(
        self,
        conversation: Conversation,
        session: ReportGenerationSession | None,
        user_message: Message,
        history: list[Message],
    ) -> MessageIntent:
        has_inputs = bool(user_message.payload.get("template_id")) and bool(
            user_message.payload.get("dataset_ids")
        )
        if has_inputs:
            return MessageIntent.CREATE
        if session is None:
            return MessageIntent.CHAT

        awaiting_plan = session.plan is not None and session.plan.status == "awaiting_confirmation"
        awaiting_answer = (
            session.status == ReportGenerationStatus.WAITING_USER and bool(session.pending_questions)
        )
        # Neither a failed run nor a stopped one is a dead end: their finished
        # chapters are on disk, so the user can say "继续" and pick up where it
        # stopped.
        can_retry = session.status in {
            ReportGenerationStatus.FAILED,
            ReportGenerationStatus.CANCELLED,
        }
        if not awaiting_plan and not awaiting_answer and not can_retry:
            return MessageIntent.CHAT

        if awaiting_plan:
            candidates = ["approve_plan", "revise_plan", "chat"]
        elif awaiting_answer:
            candidates = ["answer", "chat"]
        else:
            candidates = ["retry", "chat"]

        if self.llm is not None:
            resolved = await self._classify_with_model(session, user_message, history, candidates)
            if resolved is not None:
                return resolved

        text = user_message.content.lower()
        if awaiting_answer:
            return MessageIntent.ANSWER
        if can_retry:
            return (
                MessageIntent.RETRY
                if any(marker in text for marker in RETRY_MARKERS)
                else MessageIntent.CHAT
            )
        if any(marker in text for marker in REVISION_MARKERS):
            return MessageIntent.REVISE_PLAN
        if any(marker in text for marker in APPROVAL_MARKERS):
            return MessageIntent.APPROVE_PLAN
        return MessageIntent.CHAT

    async def _classify_with_model(
        self,
        session: ReportGenerationSession,
        user_message: Message,
        history: list[Message],
        candidates: list[str],
    ) -> MessageIntent | None:
        context = {
            "candidates": candidates,
            "report_status": session.status.value,
            "current_plan": session.plan.model_dump(mode="json") if session.plan else None,
            "pending_questions": [
                {"question_id": item.question_id, "content": item.content}
                for item in session.pending_questions
            ],
            "recent_messages": [
                {"role": item.role, "content": item.content} for item in history[-6:]
            ],
            "user_message": user_message.content,
        }
        try:
            response = await self.llm.complete(
                [
                    {"role": "system", "content": self._intent_system_prompt()},
                    {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
                ],
                [],
            )
            payload = self._parse_json(response.get("content", ""))
            value = str(payload.get("intent", "")).strip()
            if value in candidates:
                return MessageIntent(value)
        except Exception:
            logger.warning("intent_classification_failed session_id=%s", session.session_id, exc_info=True)
        return None

    @staticmethod
    def _intent_system_prompt() -> str:
        return (
            "你是报告助手的意图识别器。根据当前报告状态和用户这句话，判断用户想做什么。"
            "candidates 给出本轮允许的意图，只能从中选一个：\n"
            "- approve_plan：用户认可当前计划，要求开始生成正文\n"
            "- revise_plan：用户要求修改计划（期间、维度、章节增删改、指标增删）\n"
            "- answer：用户在回答系统提出的待确认问题\n"
            "- retry：上一轮生成中断了，用户要求重跑或从中断处继续\n"
            "- chat：用户在提问或闲聊，不需要改变报告状态\n"
            "注意：既认可又提修改意见时选 revise_plan。"
            "只返回 JSON：{\"intent\": string}"
        )

    # ── actions ───────────────────────────────────────────────────────────

    async def _act(
        self,
        conversation: Conversation,
        session: ReportGenerationSession | None,
        user_message: Message,
        intent: MessageIntent,
        history: list[Message],
    ) -> list[Message]:
        if intent is MessageIntent.CREATE:
            return await self._create_report(conversation, user_message)
        # A question asked before any report exists is still a question; only
        # the report-mutating intents actually need a session.
        if intent is MessageIntent.CHAT or session is None:
            return [
                await self._emit(
                    conversation,
                    kind="text",
                    content=await self._chat_reply(session, user_message, history),
                )
            ]
        if intent is MessageIntent.REVISE_PLAN:
            revised = await self.reports.revise_plan(session.session_id, user_message.content)
            return [await self._emit_plan(conversation, revised, revised=True)]
        if intent is MessageIntent.APPROVE_PLAN:
            return await self._run(
                conversation,
                session,
                lambda: self.reports.approve_plan(session.session_id),
                opening="计划已确认，开始生成章节。",
            )
        if intent is MessageIntent.RETRY:
            return await self._run(
                conversation,
                session,
                lambda: self.reports.retry(session.session_id),
                opening=(
                    "好的，从上次中断的章节接着写，已经写完的不会重跑。"
                    if session.chapter_drafts
                    else "好的，从上次中断的地方接着来。"
                ),
            )
        if intent is MessageIntent.ANSWER:
            resolutions = self._read_resolutions(user_message, session)
            return await self._run(
                conversation,
                session,
                lambda: self.reports.resolve_questions(
                    session.session_id,
                    ResolveQuestionsRequest(resolutions=resolutions, auto_resume=True),
                ),
                opening="已记录本章的补充项，继续生成。",
            )
        raise ValueError(f"Unhandled conversation intent: {intent.value}")

    @staticmethod
    def _read_resolutions(
        user_message: Message,
        session: ReportGenerationSession,
    ) -> list[QuestionResolutionInput]:
        """Decisions come from the question card; typing answers the open one.

        The card submits every question of the chapter at once, which is how a
        chapter gets fully settled before it is rewritten. Free text stays
        supported for the common single-question case.
        """
        raw = user_message.payload.get("resolutions")
        if isinstance(raw, list) and raw:
            return [QuestionResolutionInput.model_validate(item) for item in raw]
        if len(session.pending_questions) != 1:
            raise ValueError(
                f"本章还有 {len(session.pending_questions)} 项待处理，请在上方卡片中逐项确认后提交"
            )
        return [
            QuestionResolutionInput(
                question_id=session.pending_questions[0].question_id,
                action="value",
                value=user_message.content,
            )
        ]

    async def _create_report(self, conversation: Conversation, user_message: Message) -> list[Message]:
        if conversation.report_session_id:
            return [
                await self._emit(
                    conversation,
                    kind="text",
                    content="一个会话只生成一份报告。要做新的报告，请新建一个会话。",
                )
            ]
        async def link(created: ReportGenerationSession) -> None:
            conversation.report_session_id = created.session_id
            conversation.updated_at = utc_now()
            await self.conversations.save(conversation)

        # Linked before planning, not after: planning is a slow model call, and
        # a conversation that does not know its report cannot retry one.
        session = await self.reports.create_session(
            CreateReportGenerationRequest(
                template_id=str(user_message.payload["template_id"]),
                dataset_ids=[str(item) for item in user_message.payload["dataset_ids"]],
                instruction=user_message.content,
            ),
            user_id=conversation.user_id,
            on_created=link,
        )
        return [await self._emit_plan(conversation, session, revised=False)]

    async def _emit_plan(
        self,
        conversation: Conversation,
        session: ReportGenerationSession,
        *,
        revised: bool,
    ) -> Message:
        plan = session.plan
        if plan is None:
            return await self._emit(conversation, kind="error", content="报告计划生成失败，请重试。")
        logger.info(
            "report_plan session_id=%s version=%d title=%s period=%s dimensions=%s chapters=%s",
            session.session_id,
            plan.version,
            plan.title,
            plan.global_context.report_period,
            preview(plan.global_context.dimensions),
            preview([{"title": item.title, "metrics": item.metrics} for item in plan.chapters], limit=800),
        )
        lead = f"已更新报告计划（v{plan.version}）" if revised else f"已生成报告计划（v{plan.version}）"
        content = (
            f"{lead}：《{plan.title}》，共 {len(plan.chapters)} 个章节。\n"
            "确认无误就说「确认，开始生成」；想改直接说，例如「去掉风险章节」"
            "「报告期间改成 2025 上半年」「第三章加上同比指标」。"
        )
        return await self._emit(
            conversation,
            kind="plan",
            content=content,
            payload={"session_id": session.session_id, "plan": plan.model_dump(mode="json")},
        )

    async def _run(
        self,
        conversation: Conversation,
        session: ReportGenerationSession,
        runner: Callable[[], Awaitable[ReportGenerationSession]],
        *,
        opening: str,
    ) -> list[Message]:
        """Post progress before the run so the thread is never silent, then
        update that same message with the run's outcome."""
        progress = await self._emit(
            conversation,
            kind="progress",
            content=opening,
            payload=self._progress_payload(session),
        )
        finished = await runner()
        progress.payload = self._progress_payload(finished)
        await self.conversations.update_message(progress)
        return [progress, *await self._emit_outcome(conversation, finished)]

    async def _emit_outcome(
        self,
        conversation: Conversation,
        session: ReportGenerationSession,
    ) -> list[Message]:
        emitted: list[Message] = []
        if session.status == ReportGenerationStatus.WAITING_USER:
            if session.pending_questions:
                emitted.append(await self._emit_supplement_request(conversation, session))
            else:
                # Never leave the thread silent: a paused run the user cannot
                # see or act on is worse than an explicit failure.
                emitted.append(
                    await self._emit(
                        conversation,
                        kind="error",
                        content="报告生成已暂停，但没有收到具体的补充项。请重新确认计划或调整指令后重试。",
                    )
                )
        elif session.status == ReportGenerationStatus.AWAITING_CONFIRMATION:
            # A retry that got as far as a plan has something to show. Without
            # this the thread ended on "continuing…" and the freshly built plan
            # sat there invisible, waiting for a confirmation nobody was asked
            # for.
            emitted.append(await self._emit_plan(conversation, session, revised=False))
        elif session.status == ReportGenerationStatus.COMPLETED:
            emitted.append(
                await self._emit(
                    conversation,
                    kind="report",
                    content=f"《{session.title or '报告'}》已生成完毕，可以下载。"
                    + self._given_up_note(session),
                    payload={
                        "session_id": session.session_id,
                        "artifacts": [item.model_dump(mode="json") for item in session.artifacts],
                    },
                )
            )
        elif session.status == ReportGenerationStatus.FAILED:
            emitted.append(
                await self._emit(
                    conversation,
                    kind="error",
                    content=f"报告生成中断：{self._failure_text(session.error)}"
                    "\n已经写完的章节保留着，说「重试」可以从中断处接着写。",
                )
            )
        return emitted

    @staticmethod
    def _failure_text(error: str | None) -> str:
        """Turn a stored failure into something worth showing in a chat bubble.

        Gateways answer with a whole HTML error page, and dropping that into
        the thread tells the user nothing while burying what did happen.
        """
        raw = (error or "").strip()
        if not raw:
            return "未知原因"
        if "<html" in raw.lower():
            title = re.search(r"<title>(.*?)</title>", raw, re.IGNORECASE | re.DOTALL)
            detail = title.group(1).strip() if title else "错误页"
            return f"模型服务返回了 {detail}"
        return preview(raw, limit=200)

    @staticmethod
    def _given_up_note(session: ReportGenerationSession) -> str:
        """Name the metrics the run dropped on its own.

        A report that quietly came out one metric short is worse than one that
        says so: the user asked for those numbers and is entitled to know they
        are not in there.
        """
        given_up = [
            item.metric
            for item in session.resolved_questions
            if item.resolution == "dropped" and item.note and "已自动移出报告" in item.note
        ]
        if not given_up:
            return ""
        return (
            "\n注意：以下指标反复取数未果，已移出报告，正文没有引用它们——"
            + "、".join(dict.fromkeys(filter(None, given_up)))
            + "。"
        )

    async def _emit_supplement_request(
        self,
        conversation: Conversation,
        session: ReportGenerationSession,
    ) -> Message:
        """Ask for the data the current chapter needs before it can be written.

        Generation is sequential and a chapter is only written once its data is
        settled, so the run pauses here; supplying these values resumes this
        chapter and then continues into the next one.
        """
        chapters: list[dict[str, Any]] = []
        for question in session.pending_questions:
            chapter_id = question.chapter_id or ""
            entry = next((item for item in chapters if item["section_id"] == chapter_id), None)
            if entry is None:
                entry = {
                    "section_id": chapter_id,
                    "title": question.chapter_title or chapter_id,
                    "questions": [],
                }
                chapters.append(entry)
            entry["questions"].append(question.model_dump(mode="json"))

        planned = len(session.plan.chapters) if session.plan else len(session.chapter_drafts)
        lines = [f"已完成 {len(session.chapter_drafts)}/{planned} 个章节，当前章节缺少数据："]
        for entry in chapters:
            missing = "、".join(
                item.get("metric") or item.get("content", "") for item in entry["questions"]
            )
            lines.append(f"· {entry['title']}：{missing}")
        lines.append("补充后我会写完这一章，再继续下一章。")

        logger.info(
            "supplement_request session_id=%s chapters=%d questions=%d",
            session.session_id, len(chapters), len(session.pending_questions),
        )
        return await self._emit(
            conversation,
            kind="question",
            content="\n".join(lines),
            payload={"session_id": session.session_id, "chapters": chapters},
        )

    @staticmethod
    def _progress_payload(session: ReportGenerationSession) -> dict[str, Any]:
        plan_chapters = session.plan.chapters if session.plan else []
        return {
            "session_id": session.session_id,
            "status": session.status.value,
            "current_step": session.current_step,
            "chapters": [
                {
                    "section_id": chapter.section_id,
                    "title": chapter.title,
                    "completed": chapter.section_id in session.chapter_drafts,
                }
                for chapter in plan_chapters
            ],
        }

    async def _chat_reply(
        self,
        session: ReportGenerationSession | None,
        user_message: Message,
        history: list[Message],
    ) -> str:
        # A failed run is the one state where free-form chat is dangerous: the
        # model has no way to restart anything, but every instinct it has is to
        # say it just did. Answer from the state machine instead.
        if session is not None and session.status == ReportGenerationStatus.FAILED:
            return self._state_hint(session)
        if self.llm is None:
            return self._state_hint(session)
        try:
            response = await self.llm.complete(
                [
                    {
                        "role": "system",
                        "content": (
                            "你是报告生成助手。请用简洁的中文回答用户问题。"
                            "当前报告状态见 report_status；不要假装已经完成尚未完成的工作。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "report_status": session.status.value if session else "none",
                                "recent_messages": [
                                    {"role": item.role, "content": item.content} for item in history[-6:]
                                ],
                                "question": user_message.content,
                            },
                            ensure_ascii=False,
                        ),
                    },
                ],
                [],
            )
            reply = str(response.get("content", "")).strip()
            return reply or self._state_hint(session)
        except Exception:
            logger.warning("chat_reply_failed", exc_info=True)
            return self._state_hint(session)

    @staticmethod
    def _missing_inputs_hint() -> str:
        return "请通过「+」上传一个报告模板（docx/md/txt）和一个 Excel 数据文件，并说明你要生成什么报告。"

    def _state_hint(self, session: ReportGenerationSession | None) -> str:
        if session is None:
            return self._missing_inputs_hint()
        if session.plan is not None and session.plan.status == "awaiting_confirmation":
            return "当前计划还在等你确认。确认就说「确认，开始生成」，要改直接说要改什么。"
        if session.status == ReportGenerationStatus.RUNNING:
            return "报告正在生成中，完成后我会把结果发在这里。"
        if session.status == ReportGenerationStatus.COMPLETED:
            return "报告已经生成完毕，章节正文在上面，文档可以在上面下载。"
        if session.status == ReportGenerationStatus.FAILED:
            done = len(session.chapter_drafts)
            written = f"已经写完 {done} 章，" if done else ""
            return (
                f"上一轮生成中断了：{self._failure_text(session.error)}\n"
                f"{written}报告停在这里，我没有自动重跑。说「重试」我就从中断的地方接着写。"
            )
        if session.status == ReportGenerationStatus.CANCELLED:
            done = len(session.chapter_drafts)
            total = len(session.plan.sections) if session.plan else 0
            progress = f"已完成 {done}/{total} 章" if total else f"已完成 {done} 章"
            return f"生成已停止，{progress}，进度都还在。说「继续」我就从中断的章节接着写。"
        return "我在。需要我做什么？"

    # ── helpers ───────────────────────────────────────────────────────────

    async def _load_session(self, conversation: Conversation) -> ReportGenerationSession | None:
        if not conversation.report_session_id:
            return None
        try:
            return await self.reports.get_session(conversation.report_session_id)
        except KeyError:
            return None

    async def _emit(
        self,
        conversation: Conversation,
        *,
        kind: str,
        content: str,
        payload: dict[str, Any] | None = None,
    ) -> Message:
        message = Message(
            message_id=f"msg_{uuid4().hex}",
            conversation_id=conversation.conversation_id,
            role="assistant",
            kind=kind,  # type: ignore[arg-type]
            content=content,
            payload=payload or {},
        )
        await self.conversations.append_message(message)
        conversation.updated_at = utc_now()
        await self.conversations.save(conversation)
        logger.info(
            "assistant_message conversation_id=%s kind=%s content=%s",
            conversation.conversation_id,
            kind,
            preview(content),
        )
        return message

    @staticmethod
    def _parse_json(content: Any) -> dict[str, Any]:
        if not isinstance(content, str):
            return {}
        value = content.strip()
        if value.startswith("```"):
            value = value.split("\n", 1)[1] if "\n" in value else value
            value = value.rsplit("```", 1)[0].strip()
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            start, end = value.find("{"), value.rfind("}")
            if start < 0 or end <= start:
                return {}
            try:
                parsed = json.loads(value[start:end + 1])
            except json.JSONDecodeError:
                return {}
        return parsed if isinstance(parsed, dict) else {}
