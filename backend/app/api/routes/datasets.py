from __future__ import annotations

from pathlib import Path
import tempfile
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from ...config import settings
from ...core.models import DataReadRequest
from ...dependencies import get_catalog
from ...data.sources.excel import ExcelDataSource
from ...data.sources.sql import SqlDataSource
from ..deps import forbid_unless_owner, owner_id

router = APIRouter(prefix="/datasets", tags=["datasets"])


def _owned(dataset_id: str, caller: str) -> None:
    """Refuse a dataset the caller did not upload.

    Ownership lives in the catalog, which is in-memory: an upload recovered
    from disk after a restart comes back ownerless and is refused here. That is
    the conservative half of the trade — the report that needs it reads through
    the catalog directly and still works.
    """
    catalog = get_catalog()
    try:
        catalog.get_source(dataset_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="数据集不存在") from exc
    forbid_unless_owner(catalog.owner_of(dataset_id), caller, "数据集")


def _upload_dir() -> Path:
    """Where uploads are written.

    ``settings.data_dir`` and not ``./data``: the latter is inside the project
    tree, which is not on the container's volume and is watched by
    ``uvicorn --reload``. It is also the directory the catalog's restore hook
    scans, so an upload written anywhere else cannot be recovered after a
    restart.
    """
    data_dir = settings.data_dir
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        # Keeps local/test environments usable when the configured directory is
        # read-only. Production deployments should point STATE_DIR at a volume.
        data_dir = Path(tempfile.gettempdir()) / "report-agent-data"
        data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


@router.get("")
async def list_datasets(caller: str = Depends(owner_id)):
    return await get_catalog().list_datasets(caller)


@router.post("/excel")
async def upload_excel(file: UploadFile = File(...), caller: str = Depends(owner_id)):
    filename = file.filename or "upload.xlsx"
    if not filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Only .xlsx files are supported by the openpyxl reader")
    dataset_id = f"excel_{uuid4().hex[:10]}"
    # Stored as "<dataset_id>_<original filename>" — the restore hook parses
    # the id back out of the name, so the shape matters.
    path = _upload_dir() / f"{dataset_id}_{Path(filename).name}"
    path.write_bytes(await file.read())
    try:
        source = ExcelDataSource(path=path, dataset_id=dataset_id, name=filename)
        get_catalog().register(source, owner_id=caller)
        return source.datasets[0]
    except Exception as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/sql")
async def register_sql(payload: dict, caller: str = Depends(owner_id)):
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
        get_catalog().register(source, owner_id=caller)
        return source.datasets[0]
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{dataset_id}/sheets")
async def dataset_sheets(dataset_id: str, caller: str = Depends(owner_id)):
    _owned(dataset_id, caller)
    try:
        return await get_catalog().sheets(dataset_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NotImplementedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{dataset_id}/schema")
async def dataset_schema(
    dataset_id: str,
    sheet_name: str | None = None,
    caller: str = Depends(owner_id),
):
    _owned(dataset_id, caller)
    try:
        return await get_catalog().schema(dataset_id, sheet_name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{dataset_id}/preview")
async def preview_dataset(
    dataset_id: str,
    request: DataReadRequest,
    caller: str = Depends(owner_id),
):
    _owned(dataset_id, caller)
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
