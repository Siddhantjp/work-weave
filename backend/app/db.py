"""SQLite storage for LISTING data only: scraped listings, scrape log, geocode cache.
Accounts and user searches live in app.accounts (separate database); the LLM cache lives in app.llm.

Rule: never hold a connection open across network I/O (WAL + short transactions keep the server,
scrapers and scripts from blocking each other).
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
  url TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  source_id TEXT,
  trades TEXT NOT NULL,              -- comma-separated search categories that surfaced it
  title TEXT NOT NULL,
  employer TEXT,
  locality TEXT,
  address TEXT,
  salary_text TEXT,
  salary_min INTEGER,
  salary_max INTEGER,
  tags_json TEXT NOT NULL DEFAULT '[]',
  description TEXT,                  -- from the detail page; NULL until fetched
  posted_at TEXT,
  valid_through TEXT,
  employment_type TEXT,
  raw_detail_json TEXT,
  acquired_at TEXT NOT NULL,         -- when the listing card was scraped (UTC ISO)
  detail_acquired_at TEXT
);
CREATE TABLE IF NOT EXISTS scrape_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  source TEXT NOT NULL,
  trade TEXT NOT NULL,
  status TEXT NOT NULL,              -- ok | failed
  pages INTEGER DEFAULT 0,
  listings_seen INTEGER DEFAULT 0,
  error_type TEXT,
  error_message TEXT
);
CREATE TABLE IF NOT EXISTS geo_cache (
  query TEXT PRIMARY KEY,
  lat REAL, lon REAL,                -- NULL when not found / outside Bengaluru
  resolved_name TEXT,
  fetched_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS listing_vectors (          -- embeddings for retrieval (see search/index.py)
  url TEXT PRIMARY KEY REFERENCES listings(url),
  content_hash TEXT NOT NULL,        -- hash of the embedded text + index version: re-embed only when it changes
  vec BLOB NOT NULL                  -- 768 float32, unit length
);
CREATE TABLE IF NOT EXISTS listing_requirements (   -- used by the stable-matching extension only
  url TEXT PRIMARY KEY REFERENCES listings(url),
  content_hash TEXT NOT NULL,
  requirements_json TEXT NOT NULL,
  model TEXT NOT NULL,
  structured_at TEXT NOT NULL
);
-- user data used to live here; it must not (see app.accounts)
DROP TABLE IF EXISTS llm_cache;
DROP TABLE IF EXISTS llm_generations;
DROP TABLE IF EXISTS sessions;
DROP TABLE IF EXISTS searches;
DROP TABLE IF EXISTS users;
"""

_initialised: set[str] = set()


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect():
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(config.DB_PATH, timeout=60)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=60000")
    if str(config.DB_PATH) not in _initialised:           # schema DDL once per process
        con.executescript(SCHEMA)
        _initialised.add(str(config.DB_PATH))
    try:
        yield con
        con.commit()
    finally:
        con.close()


# ------------------------------ listings --------------------------------- #
def upsert_card(con: sqlite3.Connection, c: dict) -> None:
    row = con.execute("SELECT trades FROM listings WHERE url=?", (c["url"],)).fetchone()
    if row:
        trades = sorted(set(row["trades"].split(",")) | {c["trade"]})
        con.execute("UPDATE listings SET trades=?, acquired_at=?, salary_text=?, salary_min=?, salary_max=?, tags_json=? WHERE url=?",
                    (",".join(trades), now(), c["salary_text"], c["salary_min"], c["salary_max"], json.dumps(c["tags"]), c["url"]))
    else:
        con.execute("""INSERT INTO listings (url, source, source_id, trades, title, employer, locality,
                       salary_text, salary_min, salary_max, tags_json, acquired_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (c["url"], c["source"], c["source_id"], c["trade"], c["title"], c["employer"], c["locality"],
                     c["salary_text"], c["salary_min"], c["salary_max"], json.dumps(c["tags"]), now()))


def save_detail(con: sqlite3.Connection, url: str, d: dict) -> None:
    con.execute("""UPDATE listings SET description=?, posted_at=?, valid_through=?, employment_type=?,
                   address=?, raw_detail_json=?, detail_acquired_at=? WHERE url=?""",
                (d["description"], d["posted_at"], d["valid_through"], d["employment_type"], d["address"],
                 json.dumps(d["raw"], ensure_ascii=False), now(), url))


def log_run(con: sqlite3.Connection, *, started_at: str, source: str, trade: str, status: str, pages: int = 0,
            listings_seen: int = 0, error_type: str | None = None, error_message: str | None = None) -> None:
    con.execute("""INSERT INTO scrape_runs (started_at, finished_at, source, trade, status, pages, listings_seen,
                   error_type, error_message) VALUES (?,?,?,?,?,?,?,?,?)""",
                (started_at, now(), source, trade, status, pages, listings_seen, error_type, error_message))


def last_ok_scrape(con: sqlite3.Connection, trade: str) -> str | None:
    return con.execute("SELECT MAX(finished_at) t FROM scrape_runs WHERE trade=? AND status='ok'", (trade,)).fetchone()["t"]
