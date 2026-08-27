from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ...dependencies import get_agent
from ...core.models import AnalysisRequest, RequestContext

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.post("/profile")
async def profile_dataset(payload: dict):
    try:
        return await get_agent().profile(RequestContext(), payload["dataset_id"])
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/query")
async def query_dataset(request: AnalysisRequest):
    try:
        return await get_agent().query(RequestContext(), request)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

