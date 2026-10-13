"""Shared fixtures. Tests never touch the real databases, the network, Groq or LangSmith."""
import os

os.environ["LANGSMITH_TRACING"] = "false"       # tests must never send traces to the real LangSmith project
os.environ["LANGCHAIN_TRACING_V2"] = "false"

import pytest  # noqa: E402

from app import config, db  # noqa: E402
from app.accounts import store  # noqa: E402


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    """Empty, isolated databases per test: listings, accounts and the LLM cache are three different files."""
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "listings.db")
    monkeypatch.setattr(config, "CACHE_DB_PATH", tmp_path / "cache.db")
    monkeypatch.setattr(config, "USER_DATABASE_URL", f"sqlite:///{(tmp_path / 'users.db').as_posix()}")
    store.reset()
    yield
    store.reset()
    db._initialised.discard(str(tmp_path / "listings.db"))


@pytest.fixture
def sign_in():
    """sign_in(client, sub, name) logs a Google-style user in without going through Google."""
    def _go(client, sub="g-1", name="Asha", email=None):
        user = store.upsert_user("google", sub, email or f"{name.lower()}@example.com", name, None)
        client.cookies.set("session", store.create_session(user.id))
        return user
    return _go
