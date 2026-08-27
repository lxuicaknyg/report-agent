from __future__ import annotations

from uuid import uuid4

from ..core.models import DataReadRequest, Evidence
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


class QueryDatasetTool(Tool):
    name = "query_dataset"
    description = "Execute a read-only SQL query against a registered dataset."
    parameters_schema = {
        "type": "object",
        "properties": {
            "dataset_id": {"type": "string", "description": "Registered dataset ID"},
            "sql": {"type": "string", "description": "Read-only SELECT or WITH query"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 10000, "default": 500},
        },
        "required": ["dataset_id", "sql"],
        "additionalProperties": False,
    }

    def __init__(self, catalog: DataCatalog) -> None:
        self.catalog = catalog

    async def execute(self, context: ToolContext, arguments: dict) -> ToolResult:
        dataset_id = arguments.get("dataset_id")
        sql = arguments.get("sql")
        limit = int(arguments.get("limit", 500))
        try:
            result = await self.catalog.query(dataset_id, sql, limit=limit)
            evidence = Evidence(evidence_id=str(uuid4()), kind="query", title="Dataset query", source=dataset_id, value=result.model_dump(), method=sql)
            return ToolResult(success=True, result_for_llm=f"Query returned {result.row_count} rows", data=result, evidence=[evidence])
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
