from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Response, UploadFile

from ...dependencies import get_report_generation_service

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("/templates")
async def upload_report_template(file: UploadFile = File(...)):
    filename = file.filename or "template.txt"
    try:
        template = await get_report_generation_service().upload_template(
            filename=filename,
            content=await file.read(),
            content_type=file.content_type,
        )
        return template
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/templates")
async def list_report_templates(offset: int = 0, limit: int = 50):
    try:
        total, items = await get_report_generation_service().list_templates(offset, limit)
        return {"total": total, "has_more": offset + len(items) < total, "items": items}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/templates/{template_id}")
async def get_report_template(template_id: str):
    try:
        return await get_report_generation_service().get_template(template_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("")
async def list_report_generations(offset: int = 0, limit: int = 20):
    try:
        total, items = await get_report_generation_service().list_sessions(offset, limit)
        return {"total": total, "has_more": offset + len(items) < total, "items": items}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{session_id}")
async def get_report_generation(session_id: str):
    try:
        return await get_report_generation_service().get_session(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{session_id}/artifacts/{artifact_id}")
async def download_report_artifact(session_id: str, artifact_id: str):
    try:
        artifact, content = await get_report_generation_service().get_artifact(session_id, artifact_id)
        return Response(
            content=content,
            media_type=artifact.content_type,
            headers={"Content-Disposition": f'attachment; filename="{artifact.name}"'},
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

