"""Login domain types.

The users table is owned elsewhere (it predates this service), so these mirror
its columns rather than defining them.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class AuthUser(BaseModel):
    """A user as the rest of the system sees them — never carries the password."""

    id: int
    username: str
    role: str = "user"
    workspace: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class UserRecord(BaseModel):
    """A raw row, password included. Stays between the repository and the
    service that checks it; everything else takes :class:`AuthUser`."""

    id: int
    username: str
    password: str
    role: str = "user"
    workspace: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def public(self) -> AuthUser:
        return AuthUser(
            id=self.id,
            username=self.username,
            role=self.role,
            workspace=self.workspace,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    #: Epoch milliseconds, so the browser can compare against Date.now().
    expires_at: int
    user: AuthUser


class InvalidCredentials(Exception):
    """Wrong username or password.

    Deliberately one error for both: saying which half was wrong tells an
    attacker which usernames exist.
    """


class InvalidToken(Exception):
    """The bearer token is missing, malformed, expired, or not ours."""


class AuthNotConfigured(Exception):
    """No user database was configured, so nobody can sign in.

    Separate from a connection failure: this one is a deployment step that was
    skipped, and the fix is editing .env rather than looking at the database.
    """
