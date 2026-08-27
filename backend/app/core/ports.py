from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator

from .models import (
    ColumnSchema,
    DatasetInfo,
    DatasetProfile,
    QueryResult,
    RequestContext,
)


class DataSource(ABC):
    """统一的数据源端口，Excel 和 SQL 数据库都通过此接口暴露。"""

    source_type: str

    @abstractmethod
    async def list_datasets(self) -> list[DatasetInfo]:
        pass

    @abstractmethod
    async def get_schema(self, dataset_id: str) -> list[ColumnSchema]:
        pass

    @abstractmethod
    async def profile(self, dataset_id: str) -> DatasetProfile:
        pass

    @abstractmethod
    async def query(self, dataset_id: str, sql: str, limit: int = 500) -> QueryResult:
        pass


class LlmService(ABC):
    """模型端口。Agent 不绑定 OpenAI 或其他供应商。"""

    @abstractmethod
    async def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        pass

    async def stream(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> AsyncIterator[dict[str, Any]]:
        yield await self.complete(messages, tools)


class ArtifactStore(ABC):
    @abstractmethod
    async def put(self, name: str, content: bytes, content_type: str) -> str:
        pass

    @abstractmethod
    async def get(self, uri: str) -> bytes:
        pass


class UserResolver(ABC):
    @abstractmethod
    async def resolve(self, context: RequestContext) -> RequestContext:
        pass
