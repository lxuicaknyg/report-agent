from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException, Request, UploadFile

from ...core.conversations import CreateConversationRequest
from ...core.models import RequestContext
from ...dependencies import get_conversation_orchestrator

router = APIRouter(prefix="/conversations", tags=["conversations"])
logger = logging.getLogger(__name__)


@router.post("")
async def create_conversation(request: CreateConversationRequest | None = None):
    return await get_conversation_orchestrator().create_conversation(
        user_id=RequestContext().user.id,
        title=request.title if request else None,
    )


@router.get("")
async def list_conversations():
    return await get_conversation_orchestrator().list_conversations(RequestContext().user.id)


@router.get("/{conversation_id}")
async def get_conversation(conversation_id: str):
    try:
        return await get_conversation_orchestrator().get_detail(conversation_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{conversation_id}")
async def delete_conversation(conversation_id: str):
    await get_conversation_orchestrator().delete_conversation(conversation_id)
    return {"deleted": True}


@router.post("/{conversation_id}/cancel")
async def cancel_generation(conversation_id: str):
    """Stop the run this conversation is driving, keeping its progress.

    The stored status is flipped first so the run aborts at its next checkpoint
    even if the task handle is gone (a different worker, a restarted process);
    cancelling the task on top of that just makes it stop within a second
    instead of at the end of the current model call.
    """
    orchestrator = get_conversation_orchestrator()
    try:
        session = await orchestrator.cancel_generation(conversation_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    task = _running.get(conversation_id)
    if task is not None and not task.done():
        task.cancel()
    return session


@router.post("/{conversation_id}/messages")
async def post_message(conversation_id: str, request: Request):
    """The single write path: everything the user does is a message.

    Uploads are resolved synchronously so a bad file fails here; the model
    work (planning, revising, generating) runs in the background and its
    output arrives as new assistant messages.
    """
    orchestrator = get_conversation_orchestrator()
    try:
        text, files = await _read_message_request(request)
        message = await orchestrator.submit_message(conversation_id, text, **files)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    task = asyncio.create_task(orchestrator.process_message(conversation_id, message.message_id))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    # Keyed by conversation so a stop request can reach into the model call the
    # run is currently blocked on. One conversation drives one report, so the
    # newest task is always the one worth cancelling.
    _running[conversation_id] = task
    task.add_done_callback(lambda done: _forget(conversation_id, done))
    return message


_background_tasks: set[asyncio.Task] = set()
_running: dict[str, asyncio.Task] = {}


def _forget(conversation_id: str, task: asyncio.Task) -> None:
    if _running.get(conversation_id) is task:
        _running.pop(conversation_id, None)


async def _read_message_request(request: Request) -> tuple[str, dict[str, object]]:
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("application/json"):
        payload = await request.json()
        extra: dict[str, object] = {}
        if isinstance(payload.get("resolutions"), list):
            extra["resolutions"] = payload["resolutions"]
        return str(payload.get("text") or ""), extra

    form = await request.form()
    files: dict[str, object] = {}
    raw_resolutions = form.get("resolutions")
    if isinstance(raw_resolutions, str) and raw_resolutions.strip():
        parsed = json.loads(raw_resolutions)
        if isinstance(parsed, list):
            files["resolutions"] = parsed
    template_file = form.get("template_file")
    data_file = form.get("data_file")
    if _is_upload(template_file):
        files["template_filename"] = template_file.filename
        files["template_content"] = await template_file.read()
        files["template_content_type"] = template_file.content_type
    if _is_upload(data_file):
        files["data_filename"] = data_file.filename
        files["data_content"] = await data_file.read()
    return str(form.get("text") or ""), files


def _is_upload(value: object) -> bool:
    return isinstance(value, UploadFile) or callable(getattr(value, "read", None))
