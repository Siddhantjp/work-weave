"""Tools the search agent can call. Both touch the outside world (apna.co), so both are traced in LangSmith."""
from __future__ import annotations

from langchain_core.tools import tool
from langsmith import traceable

from .. import db
from ..sources.apna import TRADE_SLUGS, Fetcher, ScrapeError, fetch_missing_details, is_stale, scrape_trade

DETAIL_FETCH_LIMIT = 10


@tool
def scrape_apna(trades: list[str], force: bool = False) -> dict:
    """Check apna.co live for the given trades in Bengaluru and store/refresh the listings (polite, robots.txt-compliant).
    Trades whose cache is still fresh are skipped."""
    todo = [t for t in trades if t in TRADE_SLUGS and is_stale(t, force)]
    if not todo:
        return {"scraped": [], "failed": [], "skipped_fresh": trades}
    try:
        fetcher = Fetcher()
    except ScrapeError as e:
        return {"scraped": [], "failed": [{"trade": t, "error": f"{type(e).__name__}: {e}"} for t in todo], "skipped_fresh": []}
    results = [scrape_trade(fetcher, t) for t in todo]
    return {"scraped": [r for r in results if r["status"] == "ok"],
            "failed": [{"trade": r["trade"], "error": f"{r['error_type']}: {r['error']}"} for r in results if r["status"] != "ok"],
            "skipped_fresh": [t for t in trades if t not in todo]}


@traceable(run_type="tool", name="fetch_listing_details")
def fetch_details(urls: list[str]) -> dict:
    """Fetch full descriptions for listings that only have a card."""
    with db.connect() as con:
        missing = [u for u in urls if not con.execute("SELECT detail_acquired_at FROM listings WHERE url=?", (u,)).fetchone()[0]]
    if not missing:
        return {"fetched": 0, "failed": []}
    try:
        return fetch_missing_details(Fetcher(), missing, limit=DETAIL_FETCH_LIMIT)
    except ScrapeError as e:
        return {"fetched": 0, "failed": [{"error": str(e)}]}
