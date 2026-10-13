"""Read-only data endpoints: the trade list, cached listings, and system status."""
from __future__ import annotations

import json
import os

from fastapi import APIRouter, Depends

from ..accounts.store import AuthUser
from .. import auth, config, db
from ..sources.apna import TRADE_SLUGS
from ..sources.refresher import STATUS as REFRESH_STATUS

router = APIRouter(prefix="/api", tags=["data"])


@router.get("/trades")
def trades(user: AuthUser = Depends(auth.current_user)):
    return list(TRADE_SLUGS)


@router.get("/listings")
def listings(trade: str | None = None, q: str | None = None, limit: int = 100, user: AuthUser = Depends(auth.current_user)):
    sql, args = "SELECT * FROM listings WHERE 1=1", []
    if trade:
        sql += " AND (','||trades||',') LIKE ?"
        args.append(f"%,{trade},%")
    if q:
        sql += " AND (title LIKE ? OR employer LIKE ? OR locality LIKE ?)"
        args += [f"%{q}%"] * 3
    sql += " ORDER BY acquired_at DESC LIMIT ?"
    args.append(max(1, min(limit, 500)))
    with db.connect() as con:
        rows = con.execute(sql, args).fetchall()
    keys = ("url", "title", "employer", "locality", "salary_text", "trades", "posted_at", "valid_through", "acquired_at")
    return [{**{k: r[k] for k in keys}, "tags": json.loads(r["tags_json"]), "source": "apna.co (real, scraped)"} for r in rows]


@router.get("/status")
def status(user: AuthUser = Depends(auth.current_user)):
    with db.connect() as con:
        total = con.execute("SELECT COUNT(*) FROM listings").fetchone()[0]
        by_trade = [dict(r) for r in con.execute("SELECT trades, COUNT(*) n, MAX(acquired_at) last FROM listings GROUP BY trades ORDER BY n DESC")]
        runs = [dict(r) for r in con.execute("SELECT * FROM scrape_runs ORDER BY id DESC LIMIT 10")]
    tracing = os.getenv("LANGSMITH_TRACING", "false").lower() == "true" and bool(os.getenv("LANGSMITH_API_KEY"))
    return {"listings": total, "by_trade": by_trade, "recent_scrape_runs": runs, "refresh_ttl_hours": config.REFRESH_TTL_HOURS,
            "llm": {"provider": "groq", "model": config.GROQ_MODEL, "configured": bool(config.GROQ_API_KEY)},
            "langsmith": {"tracing": tracing, "project": os.getenv("LANGSMITH_PROJECT", "default")},
            "background_refresh_minutes": config.AUTO_REFRESH_MINUTES, "last_background_refresh": REFRESH_STATUS["last_cycle_at"]}
