from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(BaseModel):
    id: str
    username: str | None = None
    group_memberships: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RequestContext(BaseModel):
    user: User = Field(default_factory=lambda: User(id="local-user"))
    request_id: str | None = None
    conversation_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ColumnSchema(BaseModel):
    name: str
    data_type: str
    nullable: bool = True
    description: str | None = None


class SheetInfo(BaseModel):
    sheet_name: str
    #: The identifier this sheet is queryable as in SQL. Spelled out rather
    #: than derived, so nothing downstream has to guess at quoting rules.
    table_name: str | None = None
    columns: list[ColumnSchema] = Field(default_factory=list)
    row_count: int | None = None


#: What an aggregation may ask a column for. Deliberately small: the model
#: picks one of these, it does not describe a calculation.
AggregateFunction = Literal["sum", "count", "count_distinct", "avg", "min", "max"]

#: How a filter compares a column to a value. No expressions, no arithmetic.
FilterOperator = Literal["eq", "ne", "in", "between", "gte", "lte", "contains"]


class AggregateFilter(BaseModel):
    column: str
    op: FilterOperator = "eq"
    #: A single value, or the list/pair that ``in`` and ``between`` need.
    value: Any = None


class AggregateMetric(BaseModel):
    column: str
    function: AggregateFunction
    #: What the result column is called; defaults to ``function_column``.
    alias: str | None = None


class AggregateRequest(BaseModel):
    """A slot-filling aggregation: pick a sheet, columns and a function.

    The model never writes the calculation, only says which column to total and
    how to slice it. Everything arithmetic happens here, so a metric cannot be
    wrong because the model added six numbers up in its head — and cannot be
    surprising because the model wrote its own query.
    """

    sheet_name: str | None = None
    filters: list[AggregateFilter] = Field(default_factory=list)
    group_by: list[str] = Field(default_factory=list)
    metrics: list[AggregateMetric] = Field(default_factory=list)
    order_by: str | None = None
    descending: bool = True
    limit: int = Field(default=100, ge=1, le=1000)


class AggregateResult(BaseModel):
    dataset_id: str
    sheet_name: str
    columns: list[str] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0
    #: Rows the filters matched before grouping — the denominator a reader
    #: needs to tell "no matching data" from "everything summed to zero".
    matched_rows: int = 0


class DataReadRequest(BaseModel):
    sheet_name: str | None = None
    columns: list[str] | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=10_000)


class DataReadResult(BaseModel):
    dataset_id: str
    sheet_name: str
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    offset: int
    limit: int
    has_more: bool = False


class DatasetInfo(BaseModel):
    dataset_id: str
    name: str
    source_type: Literal["excel", "csv", "sql"]
    source_name: str | None = None
    description: str | None = None
    row_count: int | None = None
    columns: list[ColumnSchema] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DatasetProfile(BaseModel):
    dataset: DatasetInfo
    missing_values: dict[str, int] = Field(default_factory=dict)
    distinct_values: dict[str, int] = Field(default_factory=dict)
    sample_rows: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class QueryResult(BaseModel):
    dataset_id: str
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    sql: str
    execution_time_ms: float | None = None


class Evidence(BaseModel):
    evidence_id: str
    kind: Literal["dataset", "query", "research", "calculation", "generated_sql"]
    title: str
    source: str
    value: Any = None
    method: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AnalysisRequest(BaseModel):
    question: str = Field(min_length=1)
    dataset_id: str | None = None
    sql: str | None = None
    limit: int = Field(default=500, ge=1, le=10_000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AnalysisResult(BaseModel):
    question: str
    answer: str
    query_result: QueryResult | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)


class ReportDraft(BaseModel):
    title: str
    executive_summary: str
    sections: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    format: Literal["markdown", "html"] = "markdown"
