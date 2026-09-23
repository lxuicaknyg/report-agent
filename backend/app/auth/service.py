"""Checking credentials and minting the token that stands in for them."""

from __future__ import annotations

import hmac
import logging
import time

import jwt

from ..core.auth import AuthUser, InvalidCredentials, InvalidToken, UserRecord
from .repository import UserRepository

logger = logging.getLogger(__name__)

_ALGORITHM = "HS256"


def verify_password(supplied: str, stored: str) -> bool:
    """Check a password against what the users table holds.

    That column is plaintext in the existing database, so this is a comparison
    rather than a hash check. ``compare_digest`` keeps it constant-time, which
    is all that can be done from this side — the fix is to hash the column, and
    until that happens a database read exposes every account.
    """
    if not stored:
        return False
    return hmac.compare_digest(supplied, stored)


class AuthService:
    def __init__(
        self,
        users: UserRepository,
        *,
        secret: str,
        token_ttl_seconds: int = 12 * 60 * 60,
    ) -> None:
        self.users = users
        self._secret = secret
        self._ttl = token_ttl_seconds

    async def authenticate(self, username: str, password: str) -> UserRecord:
        name = (username or "").strip()
        if not name or not password:
            raise InvalidCredentials()
        record = await self.users.find_by_username(name)
        # Same error either way: which half was wrong is not the caller's
        # business, and answering it enumerates usernames.
        if record is None or not verify_password(password, record.password):
            logger.info("login_rejected username=%s reason=%s", name, "no_user" if record is None else "bad_password")
            raise InvalidCredentials()
        logger.info("login_ok username=%s user_id=%s role=%s", record.username, record.id, record.role)
        return record

    def issue_token(self, user: AuthUser) -> tuple[str, int]:
        """Return the signed token and when it expires, in epoch milliseconds."""
        now = int(time.time())
        expires_at = now + self._ttl
        payload = {
            "sub": str(user.id),
            "username": user.username,
            "role": user.role,
            "workspace": user.workspace,
            "iat": now,
            "exp": expires_at,
        }
        token = jwt.encode(payload, self._secret, algorithm=_ALGORITHM)
        return token, expires_at * 1000

    def read_token(self, token: str) -> AuthUser:
        """Recover the signed-in user from a bearer token."""
        if not token:
            raise InvalidToken()
        try:
            payload = jwt.decode(token, self._secret, algorithms=[_ALGORITHM])
        except jwt.PyJWTError as exc:
            raise InvalidToken() from exc
        try:
            return AuthUser(
                id=int(payload["sub"]),
                username=str(payload["username"]),
                role=str(payload.get("role") or "user"),
                workspace=payload.get("workspace"),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise InvalidToken() from exc
