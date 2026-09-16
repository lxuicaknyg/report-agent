from __future__ import annotations

from uuid import uuid4

from pydantic import ValidationError

from ..core.models import AggregateRequest, DataReadRequest, Evidence
from ..core.tooling import Tool, ToolContext, ToolResult
from ..data.catalog import DataCatalog


class ListDatasetsTool(Tool):
    name = "list_datasets"
    description = "List datasets available to the current user."

    def __init__(self, catalog: DataCatalog) -> None:
        self.catalog = catalog

    async def execute(self, context: ToolContext, arguments: dict) -> ToolResult:
        datasets = await self.catalog.list_datasets()
        return ToolResult(success=True, result_for_llm=f"Found {len(datasets)} datasets", data=datasets)


class ProfileDatasetTool(Tool):
    name = "profile_dataset"
    description = "Inspect schema, missing values, distinct values and sample rows."

    def __init__(self, catalog: DataCatalog) -> None:
        self.catalog = catalog

    async def execute(self, context: ToolContext, arguments: dict) -> ToolResult:
        dataset_id = arguments.get("dataset_id")
        try:
            profile = await self.catalog.profile(dataset_id)
            evidence = Evidence(evidence_id=str(uuid4()), kind="dataset", title="Dataset profile", source=dataset_id, value=profile.model_dump())
            return ToolResult(success=True, result_for_llm=f"Profiled dataset {dataset_id}", data=profile, evidence=[evidence])
        except Exception as exc:
            return ToolResult(success=False, result_for_llm=str(exc), error=str(exc))


class ListSheetsTool(Tool):
    name = "list_sheets"
    description = "List sheets available in a file dataset."

    def __init__(self, catalog: DataCatalog) -> None:
        self.catalog = catalog

    async def execute(self, context: ToolContext, arguments: dict) -> ToolResult:
        dataset_id = arguments.get("dataset_id")
        try:
            sheets = await self.catalog.sheets(dataset_id)
            return ToolResult(success=True, result_for_llm=f"Found {len(sheets)} sheets", data=sheets)
        except Exception as exc:
            return ToolResult(success=False, result_for_llm=str(exc), error=str(exc))


class ReadDatasetTool(Tool):
    name = "read_dataset"
    description = "Read rows from a dataset sheet with optional columns, exact filters and pagination."
    parameters_schema = {
        "type": "object",
        "properties": {
            "dataset_id": {"type": "string", "description": "Registered dataset ID"},
            "sheet_name": {"type": ["string", "null"], "description": "Excel worksheet name"},
            "columns": {"type": ["array", "null"], "items": {"type": "string"}},
            "filters": {"type": "object", "additionalProperties": True},
            "offset": {"type": "integer", "minimum": 0, "default": 0},
            "limit": {"type": "integer", "minimum": 1, "maximum": 10000, "default": 100},
        },
        "required": ["dataset_id"],
        "additionalProperties": False,
    }

    def __init__(self, catalog: DataCatalog) -> None:
        self.catalog = catalog

    async def execute(self, context: ToolContext, arguments: dict) -> ToolResult:
        dataset_id = arguments.get("dataset_id")
        request = DataReadRequest(
            sheet_name=arguments.get("sheet_name"),
            columns=arguments.get("columns"),
            filters=arguments.get("filters") or {},
            offset=arguments.get("offset", 0),
            limit=arguments.get("limit", 100),
        )
        try:
            result = await self.catalog.read_rows(
                dataset_id,
                request.sheet_name,
                columns=request.columns,
                filters=request.filters,
                offset=request.offset,
                limit=request.limit,
            )
            evidence = Evidence(
                evidence_id=str(uuid4()),
                kind="dataset",
                title="Dataset rows",
                source=dataset_id,
                value=result.model_dump(),
                method="read_rows",
            )
            return ToolResult(success=True, result_for_llm=f"Read {result.row_count} rows", data=result, evidence=[evidence])
        except Exception as exc:
            return ToolResult(success=False, result_for_llm=str(exc), error=str(exc))


class AggregateDatasetTool(Tool):
    """The only way a report metric gets a number.

    Every field is a slot the caller fills in, never a calculation it writes:
    pick a sheet, name the column to total and the function to total it with.
    The arithmetic happens in the data source, so a metric cannot come back
    wrong because the caller added a column up in its head.
    """

    name = "aggregate_dataset"
    description = (
        "Aggregate one sheet of a dataset: filter rows, group by columns, and "
        "compute sum/count/count_distinct/avg/min/max. Use this for every number "
        "that is a total, a count, an average or an extreme."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "dataset_id": {"type": "string", "description": "Registered dataset ID"},
            "sheet_name": {"type": ["string", "null"], "description": "Worksheet to aggregate"},
            "filters": {
                "type": "array",
                "description": "Row filters, all of which must match",
                "items": {
                    "type": "object",
                    "properties": {
                        "column": {"type": "string"},
                        "op": {
                            "type": "string",
                            "enum": ["eq", "ne", "in", "between", "gte", "lte", "contains"],
                            "default": "eq",
                        },
                        "value": {
                            "description": (
                                "A value; a list for 'in'; a [low, high] pair for 'between'. "
                                "Dates and months may be written as text, e.g. '2026-01'."
                            )
                        },
                    },
                    "required": ["column", "value"],
                    "additionalProperties": False,
                },
            },
            "group_by": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Columns to group by, e.g. a region or a month",
            },
            "metrics": {
                "type": "array",
                "description": "What to compute for each group",
                "items": {
                    "type": "object",
                    "properties": {
                        "column": {"type": "string"},
                        "function": {
                            "type": "string",
                            "enum": ["sum", "count", "count_distinct", "avg", "min", "max"],
                        },
                        "alias": {"type": ["string", "null"], "description": "Result column name"},
                    },
                    "required": ["column", "function"],
                    "additionalProperties": False,
                },
            },
            "order_by": {"type": ["string", "null"], "description": "Result column to sort by"},
            "descending": {"type": "boolean", "default": True},
            "limit": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 100},
        },
        "required": ["dataset_id"],
        "additionalProperties": False,
    }

    def __init__(self, catalog: DataCatalog) -> None:
        self.catalog = catalog

    async def execute(self, context: ToolContext, arguments: dict) -> ToolResult:
        dataset_id = arguments.get("dataset_id")
        try:
            request = AggregateRequest(
                sheet_name=arguments.get("sheet_name"),
                filters=arguments.get("filters") or [],
                group_by=arguments.get("group_by") or [],
                metrics=arguments.get("metrics") or [],
                order_by=arguments.get("order_by"),
                descending=bool(arguments.get("descending", True)),
                limit=int(arguments.get("limit", 100)),
            )
        except ValidationError as exc:
            return ToolResult(success=False, result_for_llm=str(exc), error="invalid_arguments")
        try:
            result = await self.catalog.aggregate(dataset_id, request)
            evidence = Evidence(
                evidence_id=str(uuid4()),
                kind="calculation",
                title="Dataset aggregate",
                source=dataset_id,
                value=result.model_dump(),
                method=request.model_dump_json(exclude_defaults=True),
            )
            summary = (
                f"Aggregated {result.matched_rows} matching rows into {result.row_count} groups"
            )
            return ToolResult(success=True, result_for_llm=summary, data=result, evidence=[evidence])
        except Exception as exc:
            return ToolResult(success=False, result_for_llm=str(exc), error=str(exc))
