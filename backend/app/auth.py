"""Who is calling? A FastAPI dependency that turns the session cookie into a signed-in user (or 401)."""
from __future__ import annotations

from fastapi import Cookie, HTTPException

from .accounts import store
from .accounts.store import AuthUser

COOKIE = "session"


def current_user(session: str | None = Cookie(default=None)) -> AuthUser:
    user = store.user_for_token(session) if session else None
    if not user:
        raise HTTPException(401, "Please sign in.")
    return user
