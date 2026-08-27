"""Login / Logout / Password-Change routes (cookie session-based)."""

from __future__ import annotations

import logging
import secrets
import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__
from app.auth.dependencies import (
    SESSION_CSRF_KEY,
    SESSION_USER_KEY,
    get_current_user,
    require_user,
)
from app.auth.reset_tokens import read_reset_token, token_matches_user
from app.db.models import User
from app.db.service import UserService
from app.db.session import get_session

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="ui/templates")


def _ensure_csrf(request: Request) -> str:
    """Generate or return the per-session CSRF token."""
    token = request.session.get(SESSION_CSRF_KEY)
    if not token:
        token = secrets.token_urlsafe(24)
        request.session[SESSION_CSRF_KEY] = token
    return token


def _check_csrf(request: Request, submitted: str | None) -> None:
    expected = request.session.get(SESSION_CSRF_KEY)
    if not expected or not submitted or not secrets.compare_digest(expected, submitted):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Bad CSRF token")


# --- Login ---


@router.get("/login", response_class=HTMLResponse)
async def login_form(
    request: Request,
    next: str = "/",
    error: str | None = None,
    user: User | None = Depends(get_current_user),
):
    if user is not None:
        return RedirectResponse(url=next or "/", status_code=302)
    csrf = _ensure_csrf(request)
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "version": __version__,
            "next": next,
            "csrf_token": csrf,
            "error": error,
        },
    )


@router.post("/login")
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(...),
    next: str = Form("/"),
    session: AsyncSession = Depends(get_session),
):
    _check_csrf(request, csrf_token)
    svc = UserService(session)
    user = await svc.authenticate(email, password)
    if user is None:
        # Log the attempted address: without it a typo'd e-mail and a wrong
        # password are indistinguishable in the access log. Never log the
        # password itself.
        logger.warning("Failed login attempt for %r", email)
        # Re-render with error; preserve next URL.
        csrf = _ensure_csrf(request)
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "version": __version__,
                "next": next,
                "csrf_token": csrf,
                "error": "Login fehlgeschlagen — E-Mail oder Passwort falsch.",
            },
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    await svc.touch_last_login(user)
    await session.commit()

    # Rotate session contents on login (defense against fixation).
    request.session.clear()
    request.session[SESSION_USER_KEY] = str(user.id)
    request.session[SESSION_CSRF_KEY] = secrets.token_urlsafe(24)

    target = "/account/password" if user.must_change_password else (next or "/")
    return RedirectResponse(url=target, status_code=status.HTTP_303_SEE_OTHER)


# --- Logout ---


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)


# --- Password change ---


@router.get("/account/password", response_class=HTMLResponse)
async def password_form(
    request: Request,
    user: User = Depends(require_user),
    info: str | None = None,
    error: str | None = None,
):
    csrf = _ensure_csrf(request)
    return templates.TemplateResponse(
        request,
        "change_password.html",
        {
            "version": __version__,
            "csrf_token": csrf,
            "user": user,
            "active_page": "account",
            "forced": user.must_change_password,
            "info": info,
            "error": error,
        },
    )


@router.post("/account/password")
async def password_submit(
    request: Request,
    current_password: str = Form(""),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    csrf_token: str = Form(...),
    user: User = Depends(require_user),
    session: AsyncSession = Depends(get_session),
):
    _check_csrf(request, csrf_token)
    svc = UserService(session)

    # On forced first-time change we still require the old (initial) password
    # so a stolen session cookie can't be used to lock out the user.
    def _render(error_msg: str):
        return templates.TemplateResponse(
            request,
            "change_password.html",
            {
                "version": __version__,
                "csrf_token": _ensure_csrf(request),
                "user": user,
                "active_page": "account",
                "forced": user.must_change_password,
                "error": error_msg,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    auth_user = await svc.authenticate(user.email, current_password)
    if auth_user is None:
        return _render("Aktuelles Passwort ist falsch.")

    if new_password != confirm_password:
        return _render("Die beiden neuen Passwörter stimmen nicht überein.")

    if len(new_password) < 10:
        return _render("Mindestlänge 10 Zeichen.")

    await svc.change_password(user, new_password)
    await session.commit()
    return RedirectResponse(
        url="/account/password?info=Passwort+erfolgreich+geändert",
        status_code=status.HTTP_303_SEE_OTHER,
    )


# --- Password reset via admin-issued link ---
#
# No self-service "forgot password" entry point exists: an admin issues the link
# with `invoiceforge user reset-link` and hands it over out of band. The token is
# stateless (see app/auth/reset_tokens.py) — no table, no cleanup job.


async def _user_for_token(token: str, svc: UserService) -> User | None:
    """Resolve a reset token to its user, or None if it is invalid/spent."""
    parsed = read_reset_token(token)
    if parsed is None:
        return None
    uid, fingerprint = parsed
    try:
        user = await svc.get_by_id(uuid.UUID(uid))
    except ValueError:
        return None
    if user is None or not user.is_active:
        return None
    if not token_matches_user(fingerprint, user):
        return None
    return user


def _render_reset_invalid(request: Request):
    return templates.TemplateResponse(
        request,
        "reset_password.html",
        {
            "version": __version__,
            "token_valid": False,
            "error": (
                "Dieser Link ist ungültig, abgelaufen oder wurde bereits verwendet. "
                "Bitte fordere einen neuen an."
            ),
        },
        status_code=status.HTTP_400_BAD_REQUEST,
    )


@router.get("/reset/{token}", response_class=HTMLResponse)
async def reset_form(
    request: Request,
    token: str,
    session: AsyncSession = Depends(get_session),
):
    user = await _user_for_token(token, UserService(session))
    if user is None:
        return _render_reset_invalid(request)

    return templates.TemplateResponse(
        request,
        "reset_password.html",
        {
            "version": __version__,
            "token_valid": True,
            "token": token,
            "email": user.email,
            "csrf_token": _ensure_csrf(request),
        },
    )


@router.post("/reset/{token}")
async def reset_submit(
    request: Request,
    token: str,
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    csrf_token: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    _check_csrf(request, csrf_token)
    svc = UserService(session)
    user = await _user_for_token(token, svc)
    if user is None:
        return _render_reset_invalid(request)

    def _render(error_msg: str):
        return templates.TemplateResponse(
            request,
            "reset_password.html",
            {
                "version": __version__,
                "token_valid": True,
                "token": token,
                "email": user.email,
                "csrf_token": _ensure_csrf(request),
                "error": error_msg,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if new_password != confirm_password:
        return _render("Die beiden Passwörter stimmen nicht überein.")
    if len(new_password) < 10:
        return _render("Mindestlänge 10 Zeichen.")

    # Setting the password rotates the hash, which retires this token.
    await svc.set_password(user, new_password, must_change=False)
    await session.commit()

    # Log the user straight in — they just proved control of the reset link.
    request.session.clear()
    request.session[SESSION_USER_KEY] = str(user.id)
    request.session[SESSION_CSRF_KEY] = secrets.token_urlsafe(24)
    await svc.touch_last_login(user)
    await session.commit()

    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
