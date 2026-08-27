from __future__ import annotations

from pathlib import Path
import tempfile
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile

from ...core.models import DataReadRequest
from ...dependencies import get_catalog
from ...data.sources.excel import ExcelDataSource
from ...data.sources.sql import SqlDataSource

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.get("")
async def list_datasets():
    return await get_catalog().list_datasets()


@router.post("/excel")
async def upload_excel(file: UploadFile = File(...)):
    filename = file.filename or "upload.xlsx"
    if not filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Only .xlsx files are supported by the openpyxl reader")
    data_dir = Path("./data")
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        # Keeps local/test environments usable when the working directory is
        # read-only. Production deployments should configure DATA_DIR explicitly.
        data_dir = Path(tempfile.gettempdir()) / "report-agent-data"
        data_dir.mkdir(parents=True, exist_ok=True)
    dataset_id = f"excel_{uuid4().hex[:10]}"
    path = data_dir / f"{dataset_id}_{filename}"
    path.write_bytes(await file.read())
    try:
        source = ExcelDataSource(path=path, dataset_id=dataset_id, name=filename)
        get_catalog().register(source)
        return source.datasets[0]
    except Exception as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/sql")
async def register_sql(payload: dict):
    """Register a read-only SQL dataset.

    Production deployments should resolve connection URLs from a secret manager
    instead of accepting credentials directly from end users.
    """
    required = ("connection_url", "dataset_id", "table_name")
    missing = [key for key in required if not payload.get(key)]
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing fields: {', '.join(missing)}")
    try:
        source = SqlDataSource(
            connection_url=payload["connection_url"],
            dataset_id=payload["dataset_id"],
            table_name=payload["table_name"],
            description=payload.get("description"),
        )
        get_catalog().register(source)
        return source.datasets[0]
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{dataset_id}/sheets")
async def dataset_sheets(dataset_id: str):
    try:
        return await get_catalog().sheets(dataset_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NotImplementedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{dataset_id}/schema")
async def dataset_schema(dataset_id: str, sheet_name: str | None = None):
    try:
        return await get_catalog().schema(dataset_id, sheet_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{dataset_id}/preview")
async def preview_dataset(dataset_id: str, request: DataReadRequest):
    try:
        return await get_catalog().read_rows(
            dataset_id,
            request.sheet_name,
            columns=request.columns,
            filters=request.filters,
            offset=request.offset,
            limit=request.limit,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (NotImplementedError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
