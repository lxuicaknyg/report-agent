from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from ...core.connections import ConnectionInput
from ...dependencies import get_connection_service

router = APIRouter(prefix="/connections", tags=["connections"])
logger = logging.getLogger(__name__)


@router.get("/drivers")
async def list_drivers():
    """The supported databases and the fields each needs.

    Declared before the ``/{connection_id}`` route so "drivers" is not read as
    an id.
    """
    return get_connection_service().drivers()


@router.get("")
async def list_connections():
    items = await get_connection_service().list()
    return [item.redacted() for item in items]


@router.post("")
async def create_connection(payload: ConnectionInput):
    try:
        created = await get_connection_service().create(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return created.redacted()


@router.get("/{connection_id}")
async def get_connection(connection_id: str):
    try:
        return (await get_connection_service().get(connection_id)).redacted()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/{connection_id}")
async def update_connection(connection_id: str, payload: ConnectionInput):
    try:
        updated = await get_connection_service().update(connection_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return updated.redacted()


@router.delete("/{connection_id}")
async def delete_connection(connection_id: str):
    try:
        await get_connection_service().delete(connection_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"deleted": True}


@router.post("/{connection_id}/test")
async def test_connection(connection_id: str):
    """Probe the database. Never raises on a failed connection: a refused
    login is a result to show in the form, not a broken request."""
    try:
        return await get_connection_service().test(connection_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
