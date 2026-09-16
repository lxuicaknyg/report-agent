from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

from .models import utc_now
from .reports import ReportGenerationSession

MessageRole = Literal["user", "assistant"]
MessageKind = Literal["text", "plan", "progress", "question", "report", "error"]
AttachmentKind = Literal["template", "data"]


class MessageIntent(str, Enum):
    """What a user message means, given the conversation's current state."""

    CREATE = "create"
    REVISE_PLAN = "revise_plan"
    APPROVE_PLAN = "approve_plan"
    ANSWER = "answer"
    RETRY = "retry"
    CHAT = "chat"


class MessageAttachment(BaseModel):
    filename: str
    kind: AttachmentKind
    size: int = 0


class Message(BaseModel):
    """One turn in a conversation.

    ``content`` is the human-readable text; ``payload`` carries the structured
    data the UI renders for non-text kinds (plan, progress, report). The UI
    picks a renderer from ``kind`` and never inspects business state itself.
    """

    message_id: str
    conversation_id: str
    role: MessageRole
    kind: MessageKind = "text"
    content: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    attachments: list[MessageAttachment] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class Conversation(BaseModel):
    """A chat thread. At most one report is generated per conversation."""

    conversation_id: str
    user_id: str
    title: str = "新会话"
    report_session_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ConversationDetail(BaseModel):
    conversation: Conversation
    messages: list[Message] = Field(default_factory=list)
    report_session: ReportGenerationSession | None = None


class CreateConversationRequest(BaseModel):
    title: str | None = None


class PostMessageRequest(BaseModel):
    text: str = Field(min_length=1)
