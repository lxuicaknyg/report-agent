from __future__ import annotations

import re
import time

import pandas as pd
from sqlalchemy import create_engine, inspect, text

from ...core.models import ColumnSchema, DatasetInfo, DatasetProfile, QueryResult
from .base import RegisteredDataSource


class SqlDataSource(RegisteredDataSource):
    """SQLAlchemy 数据源；默认只允许只读查询。"""

    source_type = "sql"

    def __init__(self, connection_url: str, dataset_id: str, table_name: str, description: str | None = None) -> None:
        self.engine = create_engine(connection_url, future=True)
        self.dataset_id = dataset_id
        self.table_name = table_name
        self.description = description

    @property
    def datasets(self) -> list[DatasetInfo]:
        return [
            DatasetInfo(
                dataset_id=self.dataset_id,
                name=self.table_name,
                source_type="sql",
                source_name=self.table_name,
                description=self.description,
                columns=self._schema(),
            )
        ]

    async def get_schema(self, dataset_id: str, sheet_name: str | None = None) -> list[ColumnSchema]:
        if sheet_name:
            raise ValueError("SQL data sources do not have sheets")
        self._check_dataset(dataset_id)
        return self._schema()

    def _schema(self) -> list[ColumnSchema]:
        inspector = inspect(self.engine)
        return [
            ColumnSchema(
                name=item["name"],
                data_type=str(item["type"]),
                nullable=bool(item.get("nullable", True)),
            )
            for item in inspector.get_columns(self.table_name)
        ]

    async def profile(self, dataset_id: str) -> DatasetProfile:
        self._check_dataset(dataset_id)
        result = await self.query(dataset_id, f"SELECT * FROM {self._quoted_table()} LIMIT 5", limit=5)
        schema = await self.get_schema(dataset_id)
        info = self.datasets[0].model_copy(update={"columns": schema, "row_count": None})
        return DatasetProfile(dataset=info, sample_rows=result.rows)

    async def query(self, dataset_id: str, sql: str, limit: int = 500) -> QueryResult:
        self._check_dataset(dataset_id)
        self._assert_read_only(sql)
        started = time.perf_counter()
        with self.engine.connect() as connection:
            frame = pd.read_sql_query(text(sql), connection).head(limit)
        rows = frame.where(pd.notna(frame), None).to_dict("records")
        return QueryResult(dataset_id=dataset_id, columns=[str(column) for column in frame.columns], rows=rows, row_count=len(rows), sql=sql, execution_time_ms=(time.perf_counter() - started) * 1000)

    def _quoted_table(self) -> str:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_\.]*", self.table_name):
            raise ValueError("Unsafe table name")
        return self.table_name

    def _check_dataset(self, dataset_id: str) -> None:
        if dataset_id != self.dataset_id:
            raise KeyError(f"Dataset not found: {dataset_id}")

    @staticmethod
    def _assert_read_only(sql: str) -> None:
        if not sql.strip().lower().startswith(("select", "with")):
            raise ValueError("Only read-only SELECT/WITH queries are allowed")
