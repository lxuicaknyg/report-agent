from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
import time as clock
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
from openpyxl import load_workbook

from ...core.models import (
    AggregateFilter,
    AggregateMetric,
    AggregateRequest,
    AggregateResult,
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
                table_name=self.table_name(sheet_name),
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

    async def aggregate(self, dataset_id: str, request: AggregateRequest) -> AggregateResult:
        """Run a slot-filled aggregation over one sheet.

        The caller says which column to total and how to slice it; every sum,
        count and average is computed here. Nothing in the request is a string
        the caller composed, so there is no query to get wrong and no room to
        smuggle a calculation past this boundary.
        """
        self._check_dataset(dataset_id)
        sheet_name = request.sheet_name or self._sheet_names[0]
        if sheet_name not in self._sheet_names:
            raise ValueError(
                f"Sheet not found: {sheet_name}. Available sheets: {self._sheet_names}"
            )
        frame = pd.read_excel(self.path, sheet_name=sheet_name)
        known = list(frame.columns)

        referenced = (
            [item.column for item in request.filters]
            + list(request.group_by)
            + [item.column for item in request.metrics]
        )
        unknown = [name for name in referenced if name not in known]
        if unknown:
            raise ValueError(f"Unknown columns: {', '.join(unknown)}. Available: {known}")
        if not request.metrics and not request.group_by:
            raise ValueError("Provide at least one metric or one group_by column")

        for item in request.filters:
            frame = frame[_filter_mask(frame, item)]
        matched = len(frame)

        if request.metrics:
            named = {
                (item.alias or f"{item.function}_{item.column}"): item
                for item in request.metrics
            }
            if request.group_by:
                grouped = frame.groupby(request.group_by, dropna=False)
                result = pd.DataFrame(
                    {alias: _apply(grouped[item.column], item.function) for alias, item in named.items()}
                ).reset_index()
            else:
                result = pd.DataFrame(
                    [{alias: _apply(frame[item.column], item.function) for alias, item in named.items()}]
                )
        else:
            # No metric asked for: the caller wants the distinct combinations,
            # which is how a dimension's values get enumerated.
            result = frame[request.group_by].drop_duplicates().reset_index(drop=True)

        order_by = request.order_by
        if order_by:
            if order_by not in result.columns:
                raise ValueError(f"Unknown order_by column: {order_by}. Available: {list(result.columns)}")
            result = result.sort_values(order_by, ascending=not request.descending)
        result = result.head(request.limit)

        rows = result.where(pd.notna(result), None).to_dict("records")
        return AggregateResult(
            dataset_id=dataset_id,
            sheet_name=sheet_name,
            columns=[str(column) for column in result.columns],
            rows=[{str(key): _plain(value) for key, value in row.items()} for row in rows],
            row_count=len(rows),
            matched_rows=matched,
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
                connection.register(self.table_name(sheet_name), frame)
            self._query_backend = ("duckdb", connection)
        except ImportError:
            import sqlite3

            connection = sqlite3.connect(":memory:", check_same_thread=False)
            for sheet_name, frame in frames.items():
                frame.to_sql(self.table_name(sheet_name), connection, if_exists="replace", index=False)
            self._query_backend = ("sqlite", connection)
        return self._query_backend

    @staticmethod
    def table_name(sheet_name: str) -> str:
        """The SQL table a sheet is queryable as.

        The sheet name is used as-is and quoted in SQL. Sanitising it to ASCII
        mapped every all-CJK sheet name onto the same identifier, so a workbook
        with Chinese sheet names registered four tables under one name and
        every query silently hit whichever sheet was loaded last.
        """
        return sheet_name

    @staticmethod
    def _assert_read_only(sql: str) -> None:
        statement = sql.strip().lower()
        if not (statement.startswith("select") or statement.startswith("with")):
            raise ValueError("Only read-only SELECT/WITH queries are allowed")

    def _check_dataset(self, dataset_id: str) -> None:
        if dataset_id != self.dataset_id:
            raise KeyError(f"Dataset not found: {dataset_id}")


def _plain(value: Any) -> Any:
    """Numbers a JSON payload can carry, dates a reader can recognise."""
    if isinstance(value, (datetime, date, time, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "item"):  # numpy scalar
        return value.item()
    return value


def _apply(series: Any, function: str) -> Any:
    if function == "sum":
        return series.sum()
    if function == "count":
        return series.count()
    if function == "count_distinct":
        return series.nunique()
    if function == "avg":
        return series.mean()
    if function == "min":
        return series.min()
    if function == "max":
        return series.max()
    raise ValueError(f"Unsupported aggregate function: {function}")


def _filter_mask(frame: pd.DataFrame, item: AggregateFilter) -> Any:
    """Compare one column to one value.

    Dates and months are the filter that matters most here and they arrive as
    strings ("2026-01"), so a column of timestamps is compared as text — that
    makes a prefix like "2026-01" behave the way the caller means it to.
    """
    column = frame[item.column]
    value = item.value
    if item.op == "in":
        values = value if isinstance(value, list) else [value]
        return _comparable(column, values[0]).isin([_scalar(one) for one in values])
    if item.op == "between":
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            raise ValueError("between expects a [low, high] pair")
        low, high = (_scalar(value[0]), _scalar(value[1]))
        compared = _comparable(column, value[0])
        return (compared >= low) & (compared <= high)
    if item.op == "contains":
        return column.astype(str).str.contains(str(value), na=False)
    compared = _comparable(column, value)
    scalar = _scalar(value)
    if item.op == "eq":
        return compared == scalar
    if item.op == "ne":
        return compared != scalar
    if item.op == "gte":
        return compared >= scalar
    if item.op == "lte":
        return compared <= scalar
    raise ValueError(f"Unsupported filter operator: {item.op}")


def _comparable(column: pd.Series, value: Any) -> pd.Series:
    """Line a column up with the value it is being compared to.

    A month written as "2026-01" cannot be compared to a timestamp, and the
    caller has no way to know how the sheet stored its dates; rendering the
    column as text when the value is text makes both spellings work.
    """
    if isinstance(value, str) and pd.api.types.is_datetime64_any_dtype(column):
        return column.astype(str).str.slice(0, len(value))
    if isinstance(value, str):
        return column.astype(str)
    return column


def _scalar(value: Any) -> Any:
    return value
