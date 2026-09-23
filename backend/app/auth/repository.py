"""Reading the users table."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from ..core.auth import AuthNotConfigured, UserRecord

logger = logging.getLogger(__name__)


class UserRepository:
    """Looks accounts up in the shared ``users`` table.

    Read-only: this service authenticates against the table but does not own
    it, so it never creates, updates or deletes rows.
    """

    def __init__(self, database_url: str, *, connect_timeout: int = 5) -> None:
        self._database_url = database_url
        self._connect_timeout = connect_timeout
        self._engine: Engine | None = None

    def _get_engine(self) -> Engine:
        # Built on first use and pooled: connecting per login would add a
        # round trip to every sign-in, and a bad URL should surface as a failed
        # login rather than a backend that refuses to boot.
        if not self._database_url:
            raise AuthNotConfigured("AUTH_DATABASE_URL 未配置，请在 backend/.env 中设置用户库连接串")
        if self._engine is None:
            self._engine = create_engine(
                self._database_url,
                future=True,
                pool_pre_ping=True,
                pool_recycle=1800,
                connect_args={"connect_timeout": self._connect_timeout},
            )
        return self._engine

    async def find_by_username(self, username: str) -> UserRecord | None:
        return await asyncio.to_thread(self._find_by_username, username)

    def _find_by_username(self, username: str) -> UserRecord | None:
        statement = text(
            "SELECT id, username, password, role, workspace, created_at, updated_at "
            "FROM users WHERE username = :username LIMIT 1"
        )
        with self._get_engine().connect() as connection:
            row = connection.execute(statement, {"username": username}).mappings().first()
        if row is None:
            return None
        data: dict[str, Any] = dict(row)
        return UserRecord(
            id=int(data["id"]),
            username=str(data["username"]),
            password=str(data["password"] or ""),
            role=str(data.get("role") or "user"),
            workspace=data.get("workspace"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )
