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
        #: Who uploaded each dataset, for the HTTP surface to filter on. Kept
        #: here rather than on the sources because it is not a property of the
        #: data — a source class should not have to know about logins.
        #:
        #: In memory only, like the sources themselves: a dataset recovered by
        #: ``_restore`` after a restart comes back ownerless and so is
        #: unreachable over HTTP. The report that needs it reads through
        #: ``get_source`` and is unaffected.
        self._owners: dict[str, str | None] = {}
        #: Looks up a dataset the catalog has never seen, so an upload can
        #: outlive the process that registered it.
        self._restore = restore

    def register(self, source: RegisteredDataSource, *, owner_id: str | None = None) -> None:
        for dataset in source.datasets:
            if dataset.dataset_id in self._sources:
                raise ValueError(f"Dataset already registered: {dataset.dataset_id}")
            self._sources[dataset.dataset_id] = source
            self._owners[dataset.dataset_id] = owner_id

    def owner_of(self, dataset_id: str) -> str | None:
        """Who uploaded this dataset, or None if it predates the catalog's
        knowledge of it (a restored upload, or a pre-login registration)."""
        return self._owners.get(dataset_id)

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

    async def list_datasets(self, owner_id: str | None = None) -> list[DatasetInfo]:
        """Every registered dataset, or only one user's.

        The default is unfiltered: the report tools read through here and run
        on behalf of a session that has already been authorised. Only the HTTP
        surface passes an owner.
        """
        return [
            dataset
            for dataset_id, source in self._sources.items()
            for dataset in source.datasets
            if dataset.dataset_id == dataset_id
            and (owner_id is None or self._owners.get(dataset_id) == owner_id)
        ]

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
