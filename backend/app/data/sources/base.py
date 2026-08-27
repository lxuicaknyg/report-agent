from __future__ import annotations

from abc import ABC, abstractmethod

from ...core.models import ColumnSchema, DataReadResult, DatasetInfo, DatasetProfile, QueryResult, SheetInfo


class RegisteredDataSource(ABC):
    source_type: str

    @property
    @abstractmethod
    def datasets(self) -> list[DatasetInfo]:
        pass

    @abstractmethod
    async def get_schema(self, dataset_id: str, sheet_name: str | None = None) -> list[ColumnSchema]:
        pass

    async def list_sheets(self, dataset_id: str) -> list[SheetInfo]:
        raise NotImplementedError(f"Sheet listing is not supported by {self.source_type}")

    async def read_rows(
        self,
        dataset_id: str,
        sheet_name: str | None = None,
        *,
        columns: list[str] | None = None,
        filters: dict[str, object] | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> DataReadResult:
        raise NotImplementedError(f"Row reading is not supported by {self.source_type}")

    @abstractmethod
    async def profile(self, dataset_id: str) -> DatasetProfile:
        pass

    @abstractmethod
    async def query(self, dataset_id: str, sql: str, limit: int = 500) -> QueryResult:
        pass
