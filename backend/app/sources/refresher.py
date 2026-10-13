"""Optional background refresher (off unless AUTO_REFRESH_MINUTES > 0): re-scrapes stale trades and re-indexes.
Uses the same scrape code the search agent calls on demand; failures are recorded, never hidden."""
from __future__ import annotations

import asyncio
import threading

from .. import db
from ..search.index import index_listings
from .apna import TRADE_SLUGS, Fetcher, ScrapeError, is_stale, scrape_trade

_lock = threading.Lock()
STATUS: dict = {"running": False, "last_cycle_at": None, "last_result": None}


def refresh_cycle(force: bool = False) -> dict:
    """Scrape every trade whose cache is stale (or all, if force). Non-reentrant."""
    if not _lock.acquire(blocking=False):
        return {"skipped": "a refresh cycle is already running"}
    try:
        STATUS["running"] = True
        todo = [t for t in TRADE_SLUGS if is_stale(t, force)]
        results: list[dict] = []
        if todo:
            try:
                f = Fetcher()
                results = [scrape_trade(f, t) for t in todo]
            except ScrapeError as e:
                results = [{"status": "failed", "error_type": type(e).__name__, "error": str(e)}]
        out = {"stale_trades": todo, "results": results, "indexed": index_listings() if todo else 0, "at": db.now()}
        STATUS.update(last_cycle_at=out["at"], last_result=out)
        return out
    finally:
        STATUS["running"] = False
        _lock.release()


async def loop(interval_minutes: float) -> None:
    while True:
        await asyncio.to_thread(refresh_cycle)
        await asyncio.sleep(interval_minutes * 60)
