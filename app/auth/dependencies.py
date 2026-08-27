"""FastAPI dependencies for session-based authentication.

Two ways to authenticate:
  1. Cookie session (browser UI) — primary path
  2. X-API-Key header (API clients) — fallback for `/api/v1/*`

`require_user` is the strict gate: returns the User or raises a redirect/401.
`require_admin` additionally checks `is_admin=True`.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Tenant, User
from app.db.session import get_session

SESSION_USER_KEY = "user_id"
SESSION_CSRF_KEY = "csrf_token"


def _hash_api_key(key: str) -> str:
    import hashlib

    return hashlib.sha256(key.encode()).hexdigest()


async def _user_from_session(
    request: Request, session: AsyncSession
) -> User | None:
    """Resolve a User from the session cookie, if any."""
    user_id_str = request.session.get(SESSION_USER_KEY)
    if not user_id_str:
        return None
    try:
        user_id = uuid.UUID(user_id_str)
    except (ValueError, TypeError):
        return None
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        # Session points to a deleted/disabled user — clear it.
        request.session.pop(SESSION_USER_KEY, None)
        return None
    return user


async def _user_from_api_key(
    api_key: str, session: AsyncSession
) -> User | None:
    """Resolve a User by the API key of their tenant."""
    key_hash = _hash_api_key(api_key)
    result = await session.execute(
        select(Tenant).where(Tenant.api_key_hash == key_hash, Tenant.is_active == True)  # noqa: E712
    )
    tenant = result.scalar_one_or_none()
    if tenant is None:
        return None
    user_result = await session.execute(
        select(User).where(User.tenant_id == tenant.id, User.is_active == True)  # noqa: E712
    )
    return user_result.scalar_one_or_none()


async def get_current_user(
    request: Request,
    x_api_key: Annotated[str | None, Header()] = None,
    session: AsyncSession = Depends(get_session),
) -> User | None:
    """Return the authenticated User, or None if no session/key present.

    Prefers the cookie session over the X-API-Key header.
    """
    user = await _user_from_session(request, session)
    if user:
        return user
    if x_api_key:
        return await _user_from_api_key(x_api_key, session)
    return None


async def require_user(
    request: Request,
    user: User | None = Depends(get_current_user),
) -> User:
    """Browser-friendly auth gate.

    On API paths (/api/...) returns 401 JSON.
    On UI paths returns a 302 redirect to /login (preserving the next URL).
    Also enforces password-change for users with must_change_password=True.
    """
    if user is None:
        if request.url.path.startswith("/api/"):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )
        # Redirect via exception so it works inside Depends() chains.
        raise _RedirectException(
            f"/login?next={request.url.path}"
        )

    # First-login password change is mandatory for browser users, but must NOT
    # short-circuit /api/* calls — API clients can't follow a 302 to an HTML
    # page and the Mandanten-API-Key path is tenant-scoped, not user-scoped.
    if (
        user.must_change_password
        and not request.url.path.startswith("/api/")
        and not _is_password_change_path(request.url.path)
    ):
        raise _RedirectException("/account/password")

    return user


async def require_admin(
    user: User = Depends(require_user),
) -> User:
    """Same as `require_user` but additionally requires is_admin=True."""
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator privilege required",
        )
    return user


def _is_password_change_path(path: str) -> bool:
    return path.startswith("/account/password") or path == "/logout"


class _RedirectException(Exception):
    """Raised inside dependencies to trigger a 302; caught by an exception handler."""

    def __init__(self, url: str) -> None:
        self.url = url
        super().__init__(url)


def install_redirect_handler(app) -> None:
    """Register the FastAPI exception handler that converts our redirect
    exceptions into actual 302 responses. Called once from main.py.
    """

    @app.exception_handler(_RedirectException)
    async def _handler(_request: Request, exc: _RedirectException):
        return RedirectResponse(url=exc.url, status_code=status.HTTP_302_FOUND)
