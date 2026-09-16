from __future__ import annotations

from abc import ABC, abstractmethod

from ..core.conversations import Conversation, Message


class ConversationRepository(ABC):
    @abstractmethod
    async def save(self, conversation: Conversation) -> None:
        pass

    @abstractmethod
    async def get(self, conversation_id: str) -> Conversation:
        pass

    @abstractmethod
    async def list(self, user_id: str | None = None) -> list[Conversation]:
        pass

    @abstractmethod
    async def delete(self, conversation_id: str) -> None:
        pass

    @abstractmethod
    async def append_message(self, message: Message) -> None:
        pass

    @abstractmethod
    async def update_message(self, message: Message) -> None:
        pass

    @abstractmethod
    async def list_messages(self, conversation_id: str) -> list[Message]:
        pass
