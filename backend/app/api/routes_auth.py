"""Sign in with Google (OpenID Connect), sessions, and the user's right to delete their data."""
from __future__ import annotations

from authlib.integrations.base_client.errors import OAuthError
from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Cookie, Depends, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import RedirectResponse

from .. import auth, config
from ..accounts import store
from ..accounts.store import AuthUser

router = APIRouter(prefix="/api/auth", tags=["auth"])

oauth = OAuth()
if config.GOOGLE_CLIENT_ID and config.GOOGLE_CLIENT_SECRET:
    oauth.register(name="google", client_id=config.GOOGLE_CLIENT_ID, client_secret=config.GOOGLE_CLIENT_SECRET,
                   server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
                   client_kwargs={"scope": "openid email profile"})


def _google():
    return oauth.create_client("google") if "google" in oauth._registry else None


def _fail(code: str) -> RedirectResponse:
    return RedirectResponse(f"/?auth_error={code}", status_code=303)


@router.get("/providers")
def providers():
    return {"google": _google() is not None}


@router.get("/google/login")
async def google_login(request: Request):
    g = _google()
    if g is None:
        return _fail("not_configured")
    return await g.authorize_redirect(request, f"{config.BASE_URL}/api/auth/google/callback")


@router.get("/google/callback")
async def google_callback(request: Request):
    g = _google()
    if g is None:
        return _fail("not_configured")
    try:
        token = await g.authorize_access_token(request)
    except OAuthError:                                                   # user pressed Cancel, or the handshake expired
        return _fail("cancelled")
    info = token.get("userinfo") or {}
    if not info.get("sub") or not info.get("email"):
        return _fail("failed")
    if info.get("email_verified") is False:
        return _fail("unverified")
    user = await run_in_threadpool(store.upsert_user, "google", info["sub"], info["email"], info.get("name") or "", info.get("picture"))
    session = await run_in_threadpool(store.create_session, user.id)
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(auth.COOKIE, session, httponly=True, samesite="lax", secure=config.COOKIE_SECURE, max_age=60 * 60 * 24 * config.SESSION_DAYS)
    return resp


@router.post("/logout")
def logout(resp: Response, session: str | None = Cookie(default=None)):
    if session:
        store.end_session(session)
    resp.delete_cookie(auth.COOKIE)
    return {"ok": True}


@router.get("/me")
def me(user: AuthUser = Depends(auth.current_user)):
    return {"id": user.id, "name": user.name, "email": user.email, "picture": user.picture}


@router.delete("/me")
def delete_me(resp: Response, user: AuthUser = Depends(auth.current_user)):
    """Delete the account and everything stored about it."""
    store.delete_user(user.id)
    resp.delete_cookie(auth.COOKIE)
    return {"ok": True}
