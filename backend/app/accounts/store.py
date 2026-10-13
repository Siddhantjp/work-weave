"""The accounts database: users, login sessions and what each user searched for.

Postgres in production (any provider: Render, Neon, Supabase...) through DATABASE_URL; a local SQLite file when
that is not set, so development needs nothing installed. The same SQLAlchemy code runs on both.
Nothing in here touches listing data, and listing code never touches this.
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, create_engine, delete, event, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .. import config


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("provider", "provider_sub"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uuid.uuid4().hex)
    provider: Mapped[str] = mapped_column(String(32))
    provider_sub: Mapped[str] = mapped_column(String(255))            # the provider's stable id for this person
    email: Mapped[str] = mapped_column(String(320))
    name: Mapped[str] = mapped_column(String(200))
    picture: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_login_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class LoginSession(Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)     # only a hash is stored, never the cookie value
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Search(Base):
    __tablename__ = "searches"
    __table_args__ = (Index("ix_searches_user_created", "user_id", "created_at"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    request: Mapped[str] = mapped_column(Text)                                # exactly what the user typed or said
    language: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="running")        # running | done | failed
    result: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB(), "postgresql"), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


@dataclass(frozen=True)
class AuthUser:
    id: str
    name: str
    email: str
    picture: str | None


# ------------------------------- engine ---------------------------------- #
_engine: Engine | None = None
_Session: sessionmaker | None = None


def _normalise(url: str) -> str:
    """Providers hand out postgres:// or postgresql://; SQLAlchemy needs to be told to use the psycopg 3 driver."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def _sessions() -> sessionmaker:
    global _engine, _Session
    if _Session is None:
        url = _normalise(config.USER_DATABASE_URL)
        sqlite = url.startswith("sqlite")
        if sqlite:
            from pathlib import Path
            Path(url.split("///", 1)[1]).parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(url, pool_pre_ping=True, **({"connect_args": {"check_same_thread": False, "timeout": 30}} if sqlite else {}))
        if sqlite:
            @event.listens_for(_engine, "connect")
            def _pragmas(dbapi, _):                                         # concurrent requests + cascading deletes
                cur = dbapi.cursor()
                cur.execute("PRAGMA journal_mode=WAL"); cur.execute("PRAGMA foreign_keys=ON"); cur.execute("PRAGMA busy_timeout=30000")
                cur.close()
        Base.metadata.create_all(_engine)
        _Session = sessionmaker(_engine, expire_on_commit=False)
    return _Session


def reset() -> None:
    """Forget the engine (tests point the store at a temporary database)."""
    global _engine, _Session
    if _engine is not None:
        _engine.dispose()
    _engine = _Session = None


def _as_user(u: User) -> AuthUser:
    return AuthUser(u.id, u.name, u.email, u.picture)


# ------------------------------- accounts -------------------------------- #
def upsert_user(provider: str, sub: str, email: str, name: str, picture: str | None) -> AuthUser:
    """Create the account on first sign-in, refresh name/photo on later ones. Matching is by the provider's id, not the email."""
    with _sessions().begin() as s:
        u = s.scalar(select(User).where(User.provider == provider, User.provider_sub == sub))
        if u is None:
            u = User(provider=provider, provider_sub=sub, email=email, name=name or email.split("@")[0], picture=picture)
            s.add(u)
        else:
            u.email, u.name, u.picture, u.last_login_at = email, name or u.name, picture, _now()
        s.flush()
        return _as_user(u)


def delete_user(user_id: str) -> None:
    """Right to erasure: the account, its sessions and every search it made."""
    with _sessions().begin() as s:
        s.execute(delete(Search).where(Search.user_id == user_id))
        s.execute(delete(LoginSession).where(LoginSession.user_id == user_id))
        s.execute(delete(User).where(User.id == user_id))


# ------------------------------- sessions -------------------------------- #
def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    with _sessions().begin() as s:
        s.execute(delete(LoginSession).where(LoginSession.expires_at < _now()))                 # tidy up expired ones
        s.add(LoginSession(token_hash=_hash(token), user_id=user_id, expires_at=_now() + timedelta(days=config.SESSION_DAYS)))
    return token


def user_for_token(token: str) -> AuthUser | None:
    with _sessions()() as s:
        u = s.scalar(select(User).join(LoginSession, LoginSession.user_id == User.id)
                     .where(LoginSession.token_hash == _hash(token), LoginSession.expires_at > _now()))
        return _as_user(u) if u else None


def end_session(token: str) -> None:
    with _sessions().begin() as s:
        s.execute(delete(LoginSession).where(LoginSession.token_hash == _hash(token)))


# ------------------------------- searches -------------------------------- #
def start_search(user_id: str, request: str) -> int:
    with _sessions().begin() as s:
        row = Search(user_id=user_id, request=request)
        s.add(row)
        s.flush()
        return row.id


def finish_search(search_id: int, result: dict | None = None, error: str | None = None) -> None:
    with _sessions().begin() as s:
        s.execute(update(Search).where(Search.id == search_id).values(
            status="failed" if error else "done", result=result, error=error, language=(result or {}).get("language")))


def list_searches(user_id: str, limit: int = 20) -> list[dict]:
    with _sessions()() as s:
        rows = s.scalars(select(Search).where(Search.user_id == user_id).order_by(Search.id.desc()).limit(limit)).all()
        return [{"id": r.id, "request": r.request, "created_at": r.created_at.isoformat(timespec="seconds"), "status": r.status,
                 "error": r.error, "result": r.result} for r in rows]


def clear_searches(user_id: str) -> int:
    with _sessions().begin() as s:
        return s.execute(delete(Search).where(Search.user_id == user_id)).rowcount or 0
