from __future__ import annotations

from collections.abc import Callable

from .sources.base import RegisteredDataSource
from ..core.models import (
    AggregateRequest,
    AggregateResult,
    DataReadResult,
    DatasetInfo,
    DatasetProfile,
    QueryResult,
    SheetInfo,
)


class DataCatalog:
    """统一管理 Excel、CSV、DuckDB 和外部 SQL 数据源。"""

    def __init__(
        self,
        *,
        restore: Callable[[str], RegisteredDataSource | None] | None = None,
    ) -> None:
        self._sources: dict[str, RegisteredDataSource] = {}
        #: Looks up a dataset the catalog has never seen, so an upload can
        #: outlive the process that registered it.
        self._restore = restore

    def register(self, source: RegisteredDataSource) -> None:
        for dataset in source.datasets:
            if dataset.dataset_id in self._sources:
                raise ValueError(f"Dataset already registered: {dataset.dataset_id}")
            self._sources[dataset.dataset_id] = source

    def get_source(self, dataset_id: str) -> RegisteredDataSource:
        source = self._sources.get(dataset_id)
        if source is None and self._restore is not None:
            recovered = self._restore(dataset_id)
            if recovered is not None:
                self.register(recovered)
                source = self._sources.get(dataset_id)
        if source is None:
            raise KeyError(f"Dataset not found: {dataset_id}")
        return source

    async def list_datasets(self) -> list[DatasetInfo]:
        return [dataset for source in self._sources.values() for dataset in source.datasets]

    async def schema(self, dataset_id: str, sheet_name: str | None = None):
        return await self.get_source(dataset_id).get_schema(dataset_id, sheet_name)

    async def sheets(self, dataset_id: str) -> list[SheetInfo]:
        return await self.get_source(dataset_id).list_sheets(dataset_id)

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
        return await self.get_source(dataset_id).read_rows(
            dataset_id,
            sheet_name,
            columns=columns,
            filters=filters,
            offset=offset,
            limit=limit,
        )

    async def aggregate(self, dataset_id: str, request: AggregateRequest) -> AggregateResult:
        return await self.get_source(dataset_id).aggregate(dataset_id, request)

    async def profile(self, dataset_id: str) -> DatasetProfile:
        return await self.get_source(dataset_id).profile(dataset_id)

    async def query(self, dataset_id: str, sql: str, limit: int = 500) -> QueryResult:
        return await self.get_source(dataset_id).query(dataset_id, sql, limit)
