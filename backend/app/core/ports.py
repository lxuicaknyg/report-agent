from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator


class LlmService(ABC):
    """模型端口。Agent 不绑定 OpenAI 或其他供应商。"""

    @abstractmethod
    async def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        pass

    async def stream(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> AsyncIterator[dict[str, Any]]:
        yield await self.complete(messages, tools)

    async def complete_streaming(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """One long answer, streamed.

        Same result as ``complete``; implementations that stream keep the
        connection busy so a gateway does not time out on a slow generation.
        Falls back to ``complete`` when an implementation has nothing better.
        """
        return await self.complete(messages, tools)


class ArtifactStore(ABC):
    @abstractmethod
    async def put(self, name: str, content: bytes, content_type: str) -> str:
        pass

    @abstractmethod
    async def get(self, uri: str) -> bytes:
        pass
