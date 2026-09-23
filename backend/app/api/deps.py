"""Who is calling, and what they are allowed to touch.

Every route in this service requires a login. The token is minted by
``/auth/login`` and carries the user id, so ownership is decided here rather
than in each service: the repositories already store ``user_id`` on the things
worth isolating, and these helpers are what connect the two.

Lives outside ``routes/`` because every route module depends on it — importing
from a sibling route package would make the dependency graph read backwards.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from ..core.auth import AuthUser, InvalidToken
from ..core.models import RequestContext, User
from ..dependencies import get_auth_service


def _bearer(request: Request) -> str:
    header = request.headers.get("Authorization") or ""
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="缺少登录凭证")
    return token.strip()


def current_user(request: Request) -> AuthUser:
    """The signed-in user behind this request.

    Add as a dependency to any route that should require a login; it answers
    401 rather than falling back to an anonymous identity.
    """
    try:
        return get_auth_service().read_token(_bearer(request))
    except InvalidToken as exc:
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录") from exc


def request_context(user: AuthUser = Depends(current_user)) -> RequestContext:
    """A RequestContext carrying who actually made the call.

    Routes that build ``RequestContext()`` with no arguments get the default
    ``local-user`` for everyone — depend on this instead to see the real caller.
    """
    return RequestContext(
        user=User(
            id=str(user.id),
            username=user.username,
            metadata={"role": user.role, "workspace": user.workspace},
        ),
    )


def owner_id(user: AuthUser = Depends(current_user)) -> str:
    """The caller's id as the repositories spell it.

    ``user_id`` is stored as a string throughout (it predates the login, which
    reads an integer column), so every comparison goes through this rather than
    each call site remembering to cast.
    """
    return str(user.id)


def forbid_unless_owner(resource_owner: str | None, caller: str, what: str) -> None:
    """Refuse a resource the caller does not own.

    Answers 404, not 403: telling an outsider that ``conversation_abc123``
    exists but is someone else's is itself a leak, and the id is guessable
    enough to walk. A miss and a trespass should be indistinguishable.

    ``resource_owner`` is None for rows written before ownership existed. Those
    are treated as nobody's rather than everybody's — the alternative leaves
    saved database credentials readable by every account, which is the hole
    this is here to close.
    """
    if resource_owner is None or resource_owner != caller:
        raise HTTPException(status_code=404, detail=f"{what}不存在")
