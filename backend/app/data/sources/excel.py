from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
import re
import time as clock
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
from openpyxl import load_workbook

from ...core.models import (
    ColumnSchema,
    DataReadResult,
    DatasetInfo,
    DatasetProfile,
    QueryResult,
    SheetInfo,
)
from .base import RegisteredDataSource


def _json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _normalize_headers(values: Iterable[Any]) -> list[str]:
    headers: list[str] = []
    used: dict[str, int] = {}
    for index, value in enumerate(values, start=1):
        name = str(value).strip() if value is not None else ""
        name = name or f"column_{index}"
        count = used.get(name, 0)
        used[name] = count + 1
        headers.append(name if count == 0 else f"{name}_{count + 1}")
    return headers


def _safe_identifier(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", value).strip("_") or "dataset"


class ExcelDataSource(RegisteredDataSource):
    """Excel 读取型数据源。

    常规取数路径使用 openpyxl 的只读模式，不把工作簿整体加载成 DataFrame。
    旧的 SQL 查询接口保留为兼容能力，并仅在显式调用时懒加载 DuckDB/SQLite。
    """

    source_type = "excel"

    def __init__(self, path: str | Path, dataset_id: str, name: str | None = None) -> None:
        self.path = Path(path)
        self.dataset_id = dataset_id
        self.name = name or self.path.stem
        if self.path.suffix.lower() != ".xlsx":
            raise ValueError("openpyxl Excel reader currently supports .xlsx files only")
        try:
            workbook = load_workbook(self.path, read_only=True, data_only=True)
            self._sheet_names = list(workbook.sheetnames)
            workbook.close()
        except Exception as exc:
            raise ValueError(f"Unable to read Excel workbook: {exc}") from exc
        if not self._sheet_names:
            raise ValueError(f"No worksheets found in {self.path}")
        self._query_backend: tuple[str, Any] | None = None

    @property
    def datasets(self) -> list[DatasetInfo]:
        first_sheet = self._sheet_names[0]
        columns = self._read_headers(first_sheet)
        return [
            DatasetInfo(
                dataset_id=self.dataset_id,
                name=self.name,
                source_type="excel",
                source_name=str(self.path),
                row_count=sum(self._row_count(sheet_name) or 0 for sheet_name in self._sheet_names),
                columns=columns,
                metadata={"sheets": self._sheet_names},
            )
        ]

    async def list_sheets(self, dataset_id: str) -> list[SheetInfo]:
        self._check_dataset(dataset_id)
        return [
            SheetInfo(
                sheet_name=sheet_name,
                columns=self._read_headers(sheet_name),
                row_count=self._row_count(sheet_name),
            )
            for sheet_name in self._sheet_names
        ]

    async def get_schema(self, dataset_id: str, sheet_name: str | None = None) -> list[ColumnSchema]:
        self._check_dataset(dataset_id)
        return self._read_headers(sheet_name or self._sheet_names[0])

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
        self._check_dataset(dataset_id)
        if offset < 0:
            raise ValueError("offset must be non-negative")
        if limit < 1 or limit > 10_000:
            raise ValueError("limit must be between 1 and 10000")

        selected_sheet = sheet_name or self._sheet_names[0]
        schema = self._read_headers(selected_sheet)
        headers = [column.name for column in schema]
        selected_columns = columns or headers
        unknown_columns = [column for column in selected_columns if column not in headers]
        if unknown_columns:
            raise ValueError(f"Unknown columns: {', '.join(unknown_columns)}")
        filter_values = filters or {}
        unknown_filters = [column for column in filter_values if column not in headers]
        if unknown_filters:
            raise ValueError(f"Unknown filter columns: {', '.join(unknown_filters)}")

        rows: list[dict[str, Any]] = []
        matched = 0
        for row in self._iter_rows(selected_sheet, headers):
            if not self._matches_filters(row, filter_values):
                continue
            if matched < offset:
                matched += 1
                continue
            rows.append({column: row.get(column) for column in selected_columns})
            matched += 1
            if len(rows) > limit:
                break

        has_more = len(rows) > limit
        rows = rows[:limit]

        return DataReadResult(
            dataset_id=dataset_id,
            sheet_name=selected_sheet,
            columns=selected_columns,
            rows=rows,
            row_count=len(rows),
            offset=offset,
            limit=limit,
            has_more=has_more,
        )

    async def profile(self, dataset_id: str) -> DatasetProfile:
        self._check_dataset(dataset_id)
        sheet_name = self._sheet_names[0]
        schema = self._read_headers(sheet_name)
        headers = [column.name for column in schema]
        missing_values = {column: 0 for column in headers}
        distinct_values: dict[str, set[str]] = {column: set() for column in headers}
        sample_rows: list[dict[str, Any]] = []
        duplicate_keys: set[tuple[str, ...]] = set()
        duplicate_count = 0
        row_count = 0

        for row in self._iter_rows(sheet_name, headers):
            row_count += 1
            if len(sample_rows) < 5:
                sample_rows.append(row)
            row_key = tuple(repr(row.get(column)) for column in headers)
            if row_key in duplicate_keys:
                duplicate_count += 1
            duplicate_keys.add(row_key)
            for column in headers:
                value = row.get(column)
                if value is None:
                    missing_values[column] += 1
                else:
                    distinct_values[column].add(repr(value))

        warnings: list[str] = []
        if row_count == 0:
            warnings.append("Dataset contains no rows")
        if duplicate_count:
            warnings.append(f"Detected {duplicate_count} duplicate rows")
        info = DatasetInfo(
            dataset_id=self.dataset_id,
            name=self.name,
            source_type="excel",
            source_name=str(self.path),
            row_count=row_count,
            columns=schema,
            metadata={"sheets": self._sheet_names},
        )
        return DatasetProfile(
            dataset=info,
            missing_values=missing_values,
            distinct_values={column: len(values) for column, values in distinct_values.items()},
            sample_rows=sample_rows,
            warnings=warnings,
        )

    async def query(self, dataset_id: str, sql: str, limit: int = 500) -> QueryResult:
        self._check_dataset(dataset_id)
        self._assert_read_only(sql)
        started = clock.perf_counter()
        backend, connection = self._get_query_backend()
        if backend == "duckdb":
            result = connection.execute(sql).fetchdf().head(limit)
        else:
            result = pd.read_sql_query(sql, connection).head(limit)
        rows = result.where(pd.notna(result), None).to_dict("records")
        return QueryResult(
            dataset_id=dataset_id,
            columns=[str(column) for column in result.columns],
            rows=rows,
            row_count=len(rows),
            sql=sql,
            execution_time_ms=(clock.perf_counter() - started) * 1000,
        )

    def _read_headers(self, sheet_name: str) -> list[ColumnSchema]:
        if sheet_name not in self._sheet_names:
            raise KeyError(f"Sheet not found: {sheet_name}")
        workbook = load_workbook(self.path, read_only=True, data_only=True)
        try:
            worksheet = workbook[sheet_name]
            first_row = next(worksheet.iter_rows(min_row=1, max_row=1, values_only=True), None)
            if first_row is None:
                return []
            headers = _normalize_headers(first_row)
            second_row = next(worksheet.iter_rows(min_row=2, max_row=2, values_only=True), None)
        finally:
            workbook.close()
        data_types = second_row or []
        return [
            ColumnSchema(
                name=header,
                data_type=type(data_types[index]).__name__ if index < len(data_types) and data_types[index] is not None else "unknown",
                nullable=True,
            )
            for index, header in enumerate(headers)
        ]

    def _iter_rows(self, sheet_name: str, headers: list[str]) -> Iterable[dict[str, Any]]:
        if sheet_name not in self._sheet_names:
            raise KeyError(f"Sheet not found: {sheet_name}")
        workbook = load_workbook(self.path, read_only=True, data_only=True)
        try:
            worksheet = workbook[sheet_name]
            for values in worksheet.iter_rows(min_row=2, values_only=True):
                normalized = [_json_value(value) for value in values]
                if not any(value is not None for value in normalized):
                    continue
                yield {header: normalized[index] if index < len(normalized) else None for index, header in enumerate(headers)}
        finally:
            workbook.close()

    def _row_count(self, sheet_name: str) -> int | None:
        headers = self._read_headers(sheet_name)
        return sum(1 for _ in self._iter_rows(sheet_name, [column.name for column in headers]))

    @staticmethod
    def _matches_filters(row: dict[str, Any], filters: dict[str, object]) -> bool:
        for column, expected in filters.items():
            actual = row.get(column)
            if isinstance(expected, list):
                if actual not in expected:
                    return False
            elif actual != expected and str(actual) != str(expected):
                return False
        return True

    def _get_query_backend(self) -> tuple[str, Any]:
        if self._query_backend is not None:
            return self._query_backend
        frames = pd.read_excel(self.path, sheet_name=None)
        try:
            import duckdb  # type: ignore

            connection = duckdb.connect(database=":memory:")
            for sheet_name, frame in frames.items():
                table_name = f"{_safe_identifier(self.dataset_id)}__{_safe_identifier(sheet_name)}"
                connection.register(table_name, frame)
            self._query_backend = ("duckdb", connection)
        except ImportError:
            import sqlite3

            connection = sqlite3.connect(":memory:", check_same_thread=False)
            for sheet_name, frame in frames.items():
                frame.to_sql(f"{_safe_identifier(self.dataset_id)}__{_safe_identifier(sheet_name)}", connection, if_exists="replace", index=False)
            self._query_backend = ("sqlite", connection)
        return self._query_backend

    @staticmethod
    def _assert_read_only(sql: str) -> None:
        statement = sql.strip().lower()
        if not (statement.startswith("select") or statement.startswith("with")):
            raise ValueError("Only read-only SELECT/WITH queries are allowed")

    def _check_dataset(self, dataset_id: str) -> None:
        if dataset_id != self.dataset_id:
            raise KeyError(f"Dataset not found: {dataset_id}")
