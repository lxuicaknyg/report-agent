from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from ...core.connections import (
    AnalysisSqlRequest,
    ConnectionInput,
    ConnectionQueryRequest,
)
from ...dependencies import get_connection_service
from ..deps import forbid_unless_owner, owner_id

router = APIRouter(prefix="/connections", tags=["connections"])
logger = logging.getLogger(__name__)


async def _owned(connection_id: str, caller: str) -> None:
    """Refuse a connection the caller did not save.

    These rows hold database credentials. ``/query`` runs statements through
    them, so an unchecked id here is not just a read of someone else's config —
    it is the ability to query their warehouse under their login.
    """
    try:
        connection = await get_connection_service().get(connection_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="数据源不存在") from exc
    forbid_unless_owner(connection.owner_id, caller, "数据源")


@router.get("/drivers")
async def list_drivers(caller: str = Depends(owner_id)):
    """The supported databases and the fields each needs.

    Declared before the ``/{connection_id}`` route so "drivers" is not read as
    an id.
    """
    return get_connection_service().drivers()


@router.get("")
async def list_connections(caller: str = Depends(owner_id)):
    items = await get_connection_service().list(caller)
    return [item.redacted() for item in items]


@router.post("")
async def create_connection(payload: ConnectionInput, caller: str = Depends(owner_id)):
    try:
        created = await get_connection_service().create(payload, owner_id=caller)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return created.redacted()


@router.get("/{connection_id}")
async def get_connection(connection_id: str, caller: str = Depends(owner_id)):
    await _owned(connection_id, caller)
    return (await get_connection_service().get(connection_id)).redacted()


@router.put("/{connection_id}")
async def update_connection(
    connection_id: str,
    payload: ConnectionInput,
    caller: str = Depends(owner_id),
):
    await _owned(connection_id, caller)
    try:
        updated = await get_connection_service().update(connection_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return updated.redacted()


@router.delete("/{connection_id}")
async def delete_connection(connection_id: str, caller: str = Depends(owner_id)):
    await _owned(connection_id, caller)
    try:
        await get_connection_service().delete(connection_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"deleted": True}


@router.post("/{connection_id}/test")
async def test_connection(connection_id: str, caller: str = Depends(owner_id)):
    """Probe the database. Never raises on a failed connection: a refused
    login is a result to show in the form, not a broken request."""
    await _owned(connection_id, caller)
    try:
        return await get_connection_service().test(connection_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{connection_id}/query")
async def query_connection(
    connection_id: str,
    payload: ConnectionQueryRequest,
    caller: str = Depends(owner_id),
):
    """Trial-run a read-only statement and report what it would supply.

    Like ``/test``, a statement the database refuses is a result to render
    beside the editor, not a failed request; only an unknown connection is an
    error here.
    """
    await _owned(connection_id, caller)
    try:
        return await get_connection_service().query(connection_id, payload.query, payload.shape)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{connection_id}/analysis-sql")
async def generate_analysis_sql(
    connection_id: str,
    payload: AnalysisSqlRequest,
    caller: str = Depends(owner_id),
):
    """Rewrite a working query into a year-on-year / period-on-period one.

    Generates only — the user runs the result through ``/query`` themselves, so
    they read the SQL before it touches the database. A generation that fails
    comes back on the payload, like a refused statement does.
    """
    await _owned(connection_id, caller)
    try:
        return await get_connection_service().analysis_sql(
            connection_id, payload.sql, payload.analysis_type
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
