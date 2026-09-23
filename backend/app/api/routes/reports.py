from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile

from ...dependencies import get_report_generation_service
from ..deps import forbid_unless_owner, owner_id

router = APIRouter(prefix="/reports", tags=["reports"])


async def _owned_session(session_id: str, caller: str):
    """Load a report session, or 404 if it is not the caller's.

    A finished report is the most sensitive thing this service holds — it is
    the customer's numbers written out in prose — so an id belonging to someone
    else reads exactly like an id belonging to nobody.
    """
    try:
        session = await get_report_generation_service().get_session(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="报告不存在") from exc
    forbid_unless_owner(session.user_id, caller, "报告")
    return session


@router.post("/templates")
async def upload_report_template(
    file: UploadFile = File(...),
    caller: str = Depends(owner_id),
):
    filename = file.filename or "template.txt"
    try:
        template = await get_report_generation_service().upload_template(
            filename=filename,
            content=await file.read(),
            content_type=file.content_type,
            owner_id=caller,
        )
        return template
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/templates")
async def list_report_templates(
    offset: int = 0,
    limit: int = 50,
    caller: str = Depends(owner_id),
):
    try:
        total, items = await get_report_generation_service().list_templates(
            offset, limit, owner_id=caller
        )
        return {"total": total, "has_more": offset + len(items) < total, "items": items}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/templates/{template_id}")
async def get_report_template(template_id: str, caller: str = Depends(owner_id)):
    try:
        template = await get_report_generation_service().get_template(template_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="模板不存在") from exc
    forbid_unless_owner(template.owner_id, caller, "模板")
    return template


@router.get("")
async def list_report_generations(
    offset: int = 0,
    limit: int = 20,
    caller: str = Depends(owner_id),
):
    try:
        total, items = await get_report_generation_service().list_sessions(
            offset, limit, owner_id=caller
        )
        return {"total": total, "has_more": offset + len(items) < total, "items": items}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{session_id}")
async def get_report_generation(session_id: str, caller: str = Depends(owner_id)):
    return await _owned_session(session_id, caller)


@router.get("/{session_id}/artifacts/{artifact_id}")
async def download_report_artifact(
    session_id: str,
    artifact_id: str,
    caller: str = Depends(owner_id),
):
    await _owned_session(session_id, caller)
    try:
        artifact, content = await get_report_generation_service().get_artifact(session_id, artifact_id)
        return Response(
            content=content,
            media_type=artifact.content_type,
            headers={"Content-Disposition": f'attachment; filename="{artifact.name}"'},
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
