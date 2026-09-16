from __future__ import annotations

import json
from pathlib import Path

from ..conversations.repository import ConversationRepository
from ..core.conversations import Conversation, Message


class InMemoryConversationRepository(ConversationRepository):
    def __init__(self) -> None:
        self._conversations: dict[str, Conversation] = {}
        self._messages: dict[str, list[Message]] = {}

    async def save(self, conversation: Conversation) -> None:
        self._conversations[conversation.conversation_id] = conversation.model_copy(deep=True)
        self._messages.setdefault(conversation.conversation_id, [])

    async def get(self, conversation_id: str) -> Conversation:
        try:
            return self._conversations[conversation_id].model_copy(deep=True)
        except KeyError as exc:
            raise KeyError(f"Conversation not found: {conversation_id}") from exc

    async def list(self, user_id: str | None = None) -> list[Conversation]:
        return [
            item.model_copy(deep=True)
            for item in self._conversations.values()
            if user_id is None or item.user_id == user_id
        ]

    async def delete(self, conversation_id: str) -> None:
        self._conversations.pop(conversation_id, None)
        self._messages.pop(conversation_id, None)

    async def append_message(self, message: Message) -> None:
        self._messages.setdefault(message.conversation_id, []).append(message.model_copy(deep=True))

    async def update_message(self, message: Message) -> None:
        items = self._messages.setdefault(message.conversation_id, [])
        for index, existing in enumerate(items):
            if existing.message_id == message.message_id:
                items[index] = message.model_copy(deep=True)
                return
        items.append(message.model_copy(deep=True))

    async def list_messages(self, conversation_id: str) -> list[Message]:
        return [item.model_copy(deep=True) for item in self._messages.get(conversation_id, [])]


class PersistentConversationRepository(InMemoryConversationRepository):
    """File-backed conversations so a backend restart does not lose the thread.

    Mirrors ``PersistentReportSessionRepository``: load on construction, flush
    the whole document on every write. Volume here is a chat log per user, so
    the simplicity is worth more than incremental writes.
    """

    def __init__(self, path: Path) -> None:
        super().__init__()
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, ValueError):
            return
        if not isinstance(raw, dict):
            return
        for value in raw.get("conversations", []):
            try:
                conversation = Conversation.model_validate(value)
            except ValueError:
                continue
            self._conversations[conversation.conversation_id] = conversation
            self._messages.setdefault(conversation.conversation_id, [])
        for value in raw.get("messages", []):
            try:
                message = Message.model_validate(value)
            except ValueError:
                continue
            if message.conversation_id in self._conversations:
                self._messages.setdefault(message.conversation_id, []).append(message)

    def _flush(self) -> None:
        payload = {
            "conversations": [item.model_dump(mode="json") for item in self._conversations.values()],
            "messages": [
                message.model_dump(mode="json")
                for items in self._messages.values()
                for message in items
            ],
        }
        tmp = self.path.with_suffix(f"{self.path.suffix}.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    async def save(self, conversation: Conversation) -> None:
        await super().save(conversation)
        self._flush()

    async def delete(self, conversation_id: str) -> None:
        await super().delete(conversation_id)
        self._flush()

    async def append_message(self, message: Message) -> None:
        await super().append_message(message)
        self._flush()

    async def update_message(self, message: Message) -> None:
        await super().update_message(message)
        self._flush()
