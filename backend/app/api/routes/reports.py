from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Response, UploadFile

from ...core.models import RequestContext
from ...core.reports import AnswerReportQuestionRequest, CreateReportGenerationRequest
from ...dependencies import get_agent, get_report_generation_service, get_report_service

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

@router.get("/templates/{template_id}")
async def get_report_template(template_id: str):
    try:
        return await get_report_generation_service().get_template(template_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("")
async def create_report_generation(request: CreateReportGenerationRequest):
    try:
        session = await get_report_generation_service().create_session(
            request,
            user_id=RequestContext().user.id,
        )
        return session
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{session_id}")
async def get_report_generation(session_id: str):
    try:
        return await get_report_generation_service().get_session(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{session_id}/answers")
async def answer_report_question(session_id: str, request: AnswerReportQuestionRequest):
    try:
        return await get_report_generation_service().answer_question(session_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{session_id}/resume")
async def resume_report_generation(session_id: str):
    try:
        return await get_report_generation_service().start(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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


@router.post("/draft")
async def create_legacy_profile_report(payload: dict):
    """Backward-compatible profile report endpoint."""
    try:
        profile = await get_agent().profile(RequestContext(), payload["dataset_id"])
        report = get_report_service().create_profile_report(profile, payload.get("title"))
        return {"report": report, "markdown": get_report_service().to_markdown(report)}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
