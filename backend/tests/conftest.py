"""Shared fixtures for the HTTP-level tests."""

from __future__ import annotations

import pytest
from fastapi import FastAPI

from app.api import deps
from app.config import settings
from app.core.auth import AuthUser

#: Where the routes are mounted. Read from settings rather than spelled out, so
#: moving the service's namespace does not mean editing every test.
API = settings.api_prefix

#: The user every authenticated test acts as.
TEST_USER_ID = "1"


def sign_in(app: FastAPI, user_id: str = TEST_USER_ID, role: str = "analyst") -> AuthUser:
    """Make every route see a signed-in caller.

    Overrides the dependency rather than minting a real token: the tests here
    are about the routes, and a real token would drag in the users database.
    Ownership still runs for real — the routes read the id this returns.
    """
    user = AuthUser(id=int(user_id), username=f"user{user_id}", role=role, workspace="default")
    app.dependency_overrides[deps.current_user] = lambda: user
    return user


@pytest.fixture
def api() -> str:
    return API
