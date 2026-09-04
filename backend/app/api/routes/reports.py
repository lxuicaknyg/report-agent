from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile

from ...core.models import RequestContext
from ...core.reports import AnswerReportQuestionRequest, ConfirmReportPlanRequest, CreateReportGenerationRequest
from ...dependencies import get_agent, get_report_generation_service, get_report_service, get_workflow_intake_service

router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("/workflows/intake")
async def intake_report_workflow(
    template_file: UploadFile = File(...),
    data_file: UploadFile = File(...),
    instruction: str = Form(...),
    title: str | None = Form(None),
    workflow: str = Form("report_generation"),
):
    try:
        template_name = template_file.filename or "template.txt"
        data_name = data_file.filename or "data.xlsx"
        decision, session = await get_workflow_intake_service().intake_report(
            template_filename=template_name,
            template_content=await template_file.read(),
            template_content_type=template_file.content_type,
            data_filename=data_name,
            data_content=await data_file.read(),
            instruction=instruction,
            title=title,
            workflow=workflow,
            user_id=RequestContext().user.id,
        )
        return {
            "request_id": f"request_{session.session_id.removeprefix('report_')}",
            "intent": decision.workflow.value,
            "confidence": decision.confidence,
            "status": "accepted",
            "session": session,
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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


@router.post("/{session_id}/answers")
async def answer_report_question(session_id: str, request: AnswerReportQuestionRequest):
    try:
        return await get_report_generation_service().answer_question(session_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{session_id}/plan/confirm")
async def confirm_report_plan(session_id: str, request: ConfirmReportPlanRequest):
    try:
        return await get_report_generation_service().confirm_plan(session_id, request)
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
