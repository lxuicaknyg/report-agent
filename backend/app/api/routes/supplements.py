"""Reading pasted data back to the user before they commit it.

One endpoint, and it changes nothing: it parses text and hands back the table
that text would become. The supplement itself is still submitted as a message,
like every other write — this only exists so the user sees the rows that would
land in their report before they are in it.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...core.tabular import TableParseError, parse_table
from ..deps import owner_id

router = APIRouter(prefix="/supplements", tags=["supplements"])
logger = logging.getLogger(__name__)


class TablePreviewRequest(BaseModel):
    text: str


@router.post("/preview")
async def preview_pasted_table(
    payload: TablePreviewRequest,
    caller: str = Depends(owner_id),
):
    """Parse pasted text into the table a supplement would carry.

    A paste that cannot be read is a 400 with the reason: the message is
    written for the person who pasted it, and the editor shows it beside their
    text rather than turning it into a failed request nobody can act on.
    """
    try:
        return parse_table(payload.text)
    except TableParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
