from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import SQLAlchemyError

from ...core.auth import (
    AuthNotConfigured,
    AuthUser,
    InvalidCredentials,
    LoginRequest,
    LoginResponse,
)
from ...dependencies import get_auth_service
from ..deps import current_user

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest) -> LoginResponse:
    service = get_auth_service()
    try:
        record = await service.authenticate(payload.username, payload.password)
    except InvalidCredentials as exc:
        raise HTTPException(status_code=401, detail="账号或密码不正确") from exc
    except AuthNotConfigured as exc:
        logger.error("login_not_configured: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        # A database that is down is an outage, not a rejected password; saying
        # "wrong password" here would send the user off chasing their own typing.
        logger.exception("login_backend_unavailable")
        raise HTTPException(status_code=503, detail="用户数据库连接失败，请稍后重试") from exc

    user = record.public()
    token, expires_at = service.issue_token(user)
    return LoginResponse(token=token, expires_at=expires_at, user=user)


@router.get("/me", response_model=AuthUser)
async def me(user: AuthUser = Depends(current_user)) -> AuthUser:
    return user
