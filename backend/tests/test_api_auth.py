"""Accounts, Google sign-in (mocked), user-data isolation and API guard rails. No LLM, scraping or network is involved."""
import pytest
from authlib.integrations.base_client.errors import OAuthError
from fastapi.testclient import TestClient
from starlette.responses import RedirectResponse

from app import config, db, tasks
from app.accounts import store
from app.api import app, routes_auth

GOOGLE_USER = {"sub": "g-123", "email": "asha@example.com", "email_verified": True, "name": "Asha K", "picture": "https://img/x.png"}


@pytest.fixture
def client(temp_db):
    with TestClient(app, follow_redirects=False) as c:
        yield c


class FakeGoogle:
    """Stands in for Authlib's Google client: no browser, no network."""
    userinfo: dict = {}
    fail = False
    redirect_uri = ""

    async def authorize_redirect(self, request, redirect_uri):
        FakeGoogle.redirect_uri = redirect_uri
        return RedirectResponse("https://accounts.google.com/o/oauth2/v2/auth?fake=1")

    async def authorize_access_token(self, request):
        if FakeGoogle.fail:
            raise OAuthError(error="access_denied")
        return {"userinfo": dict(FakeGoogle.userinfo)}


@pytest.fixture
def google(monkeypatch):
    FakeGoogle.fail, FakeGoogle.userinfo = False, dict(GOOGLE_USER)
    monkeypatch.setattr(routes_auth, "_google", lambda: FakeGoogle())


def test_protected_endpoints_require_login(client):
    for path in ("/api/auth/me", "/api/listings", "/api/status", "/api/searches", "/api/trades", "/api/languages"):
        assert client.get(path).status_code == 401, path
    assert client.post("/api/search", json={"request": "delivery job please"}).status_code == 401
    assert client.delete("/api/auth/me").status_code == 401


def test_providers_reports_whether_google_is_configured(client, monkeypatch):
    monkeypatch.setattr(routes_auth, "_google", lambda: None)
    assert client.get("/api/auth/providers").json() == {"google": False}
    assert client.get("/api/auth/google/login").headers["location"] == "/?auth_error=not_configured"
    monkeypatch.setattr(routes_auth, "_google", lambda: FakeGoogle())
    assert client.get("/api/auth/providers").json() == {"google": True}


def test_google_flow_creates_account_and_session(client, google):
    r = client.get("/api/auth/google/login")
    assert "accounts.google.com" in r.headers["location"]
    assert FakeGoogle.redirect_uri == f"{config.BASE_URL}/api/auth/google/callback"
    r = client.get("/api/auth/google/callback?code=x&state=y")
    assert r.status_code == 303 and r.headers["location"] == "/"
    cookie = r.headers["set-cookie"].lower()
    assert "session=" in cookie and "httponly" in cookie and "samesite=lax" in cookie
    me = client.get("/api/auth/me").json()
    assert me["name"] == "Asha K" and me["email"] == "asha@example.com" and me["picture"] == "https://img/x.png"


def test_signing_in_again_reuses_the_account_and_refreshes_profile(client, google):
    client.get("/api/auth/google/callback")
    first = client.get("/api/auth/me").json()["id"]
    client.post("/api/auth/logout")
    FakeGoogle.userinfo = {**GOOGLE_USER, "name": "Asha Kumar", "email": "asha.new@example.com"}      # same person, new name and email
    client.get("/api/auth/google/callback")
    me = client.get("/api/auth/me").json()
    assert me["id"] == first and me["name"] == "Asha Kumar" and me["email"] == "asha.new@example.com"


def test_cancelled_unverified_or_incomplete_sign_in_never_creates_a_session(client, google):
    FakeGoogle.fail = True
    assert client.get("/api/auth/google/callback").headers["location"] == "/?auth_error=cancelled"
    FakeGoogle.fail = False
    FakeGoogle.userinfo = {**GOOGLE_USER, "email_verified": False}
    assert client.get("/api/auth/google/callback").headers["location"] == "/?auth_error=unverified"
    FakeGoogle.userinfo = {"sub": "g-1"}
    assert client.get("/api/auth/google/callback").headers["location"] == "/?auth_error=failed"
    assert client.get("/api/auth/me").status_code == 401


def test_logout_ends_the_session(client, sign_in):
    sign_in(client)
    assert client.get("/api/auth/me").status_code == 200
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401


def test_session_tokens_are_stored_hashed_and_expire(client, sign_in):
    user = sign_in(client)
    token = client.cookies.get("session")
    with store._sessions()() as s:
        rows = s.scalars(store.select(store.LoginSession)).all()
        assert len(rows) == 1 and token not in rows[0].token_hash and rows[0].user_id == user.id
    with store._sessions().begin() as s:
        s.execute(store.update(store.LoginSession).values(expires_at=store._now().replace(year=2000)))
    assert client.get("/api/auth/me").status_code == 401


def test_users_only_see_their_own_searches(client, sign_in):
    a = sign_in(client, "g-a", "Asha")
    store.finish_search(store.start_search(a.id, "delivery job in Kammanahalli"), result={"ranked": [], "language": "English"})
    assert [r["request"] for r in client.get("/api/searches").json()] == ["delivery job in Kammanahalli"]
    sign_in(client, "g-b", "Bala")
    assert client.get("/api/searches").json() == []


def test_user_data_lives_in_its_own_database_not_with_listings(client, sign_in):
    user = sign_in(client)
    store.start_search(user.id, "private request text")
    with db.connect() as con:
        tables = {r["name"] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert tables.isdisjoint({"users", "sessions", "searches", "llm_generations"})
    assert "listings" in tables


def test_clear_history_and_delete_account_remove_everything(client, sign_in):
    user = sign_in(client)
    store.finish_search(store.start_search(user.id, "one"), result={"ranked": []})
    store.start_search(user.id, "two")
    assert client.delete("/api/searches").json() == {"deleted": 2}
    store.start_search(user.id, "three")
    assert client.delete("/api/auth/me").status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    with store._sessions()() as s:
        for model in (store.User, store.LoginSession, store.Search):
            assert s.scalars(store.select(model)).first() is None


def test_postgres_urls_are_pointed_at_the_psycopg_driver():
    assert store._normalise("postgres://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert store._normalise("postgresql://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert store._normalise("sqlite:///x.db") == "sqlite:///x.db"


def test_search_input_validation_and_one_search_at_a_time(client, monkeypatch, sign_in):
    sign_in(client)
    assert client.post("/api/search", json={"request": "hi"}).status_code == 422
    monkeypatch.setattr(tasks, "is_running", lambda kind, owner: True)
    assert client.post("/api/search", json={"request": "I want a delivery job"}).status_code == 409


def test_other_users_tasks_are_invisible(client, sign_in):
    tid = tasks.start("search", lambda emit: "done", owner="someone-else")
    sign_in(client)
    assert client.get(f"/api/tasks/{tid}").status_code == 404
