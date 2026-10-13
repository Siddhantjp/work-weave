"""Polite scraper for public Apna job listing pages (Bengaluru).

Compliance: honours robots.txt (checked before every URL), identifies itself with an
honest User-Agent, enforces a minimum interval between requests, retries with
exponential backoff, and raises explicit errors on blocks / unparseable pages.
It never substitutes placeholder data: on failure it raises.
"""
from __future__ import annotations

import html
import json
import re
import time
import urllib.robotparser
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup

from .. import config, db

BASE = "https://apna.co"
SOURCE = "apna"
USER_AGENT = "AcademicResearchBot/0.1 (university project on stable matching; low-rate, robots.txt-compliant)"

# trade -> apna.co category slug
TRADE_SLUGS = {
    "delivery": "delivery",
    "electrician": "electrician",
    "plumber": "plumber",
    "security guard": "security-guard",
    "driver": "driver",
    "domestic worker": "housekeeping",
    "cook": "cook",
}


# Apna pads sparse categories with neighbouring ones (e.g. the plumber page lists
# electricians). Keep a card only if its TITLE matches the trade; dropped counts are reported.
TRADE_KEYWORDS = {
    "delivery": r"deliver",
    "electrician": r"electric",
    "plumber": r"plumb|pipe|water filter",
    "security guard": r"securit|guard|loss prevention",
    "driver": r"driver|chauffeur",
    "domestic worker": r"house\s*keep|clean|maid|helper|domestic|attender",
    "cook": r"cook|chef",
}


class ScrapeError(Exception):
    pass


class RobotsDisallowed(ScrapeError):
    pass


class ScrapeBlocked(ScrapeError):
    """Server refused us (403/429/captcha) even after backoff."""


class ScrapeParseError(ScrapeError):
    """Page fetched but contained no recognisable listings: layout changed or empty."""


class Fetcher:
    def __init__(self, min_interval: float | None = None, max_retries: int = 3):
        self.min_interval = config.SCRAPER_MIN_INTERVAL_S if min_interval is None else min_interval
        self.max_retries = max_retries
        self._last = 0.0
        self.client = httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=25, follow_redirects=True)
        self.robots = urllib.robotparser.RobotFileParser()
        self._load_robots()

    def _load_robots(self) -> None:
        try:
            r = self.client.get(f"{BASE}/robots.txt")
        except httpx.HTTPError as e:
            raise ScrapeBlocked(f"cannot fetch robots.txt: {e}") from e
        if r.status_code in (401, 403):
            raise ScrapeBlocked(f"robots.txt returned {r.status_code}")
        self.robots.parse(r.text.splitlines() if r.status_code == 200 else [])

    def get(self, url: str) -> str:
        if not self.robots.can_fetch(USER_AGENT, url):
            raise RobotsDisallowed(f"robots.txt disallows {url}")
        last_err: Exception | None = None
        for attempt in range(self.max_retries + 1):
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            try:
                r = self.client.get(url)
            except httpx.HTTPError as e:
                last_err = e
            else:
                if r.status_code == 200:
                    if re.search(r"captcha|access denied|unusual traffic", r.text[:5000], re.I):
                        raise ScrapeBlocked(f"block page detected at {url}")
                    return r.text
                if r.status_code in (403, 401):
                    raise ScrapeBlocked(f"HTTP {r.status_code} at {url}")
                last_err = ScrapeError(f"HTTP {r.status_code} at {url}")
                if r.status_code == 404:
                    raise last_err
            if attempt < self.max_retries:
                time.sleep(2 ** (attempt + 1))
        raise ScrapeBlocked(f"gave up on {url} after {self.max_retries + 1} attempts: {last_err}")


# ------------------------------ parsing ---------------------------------- #
def _salary(text: str) -> tuple[int | None, int | None]:
    nums = [int(n.replace(",", "")) for n in re.findall(r"₹\s*([\d,]+)", text)]
    return (nums[0], nums[1]) if len(nums) >= 2 else ((nums[0], nums[0]) if nums else (None, None))


def parse_cards(page_html: str, trade: str) -> list[dict]:
    soup = BeautifulSoup(page_html, "html.parser")
    out = []
    for a in soup.select('a[data-testid="job-card"]'):
        href = a.get("href", "")
        if not href.startswith("/job/"):
            continue
        parts = [s.strip() for s in a.stripped_strings if s.strip()]
        if len(parts) < 3:
            continue
        title, employer = parts[0], parts[1]
        salary_text = next((p for p in parts if p.startswith("₹")), None)
        locality = next((p for p in parts[2:] if "Bengaluru" in p or "Bangalore" in p), None)
        tags = [p for p in parts[2:] if p not in (salary_text, locality)]
        smin, smax = _salary(salary_text or "")
        out.append({
            "url": urljoin(BASE, href), "source": SOURCE, "source_id": href.rsplit("-", 1)[-1],
            "trade": trade, "title": title, "employer": employer, "locality": locality,
            "salary_text": salary_text, "salary_min": smin, "salary_max": smax, "tags": tags,
        })
    return out


def parse_detail(page_html: str) -> dict:
    soup = BeautifulSoup(page_html, "html.parser")
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            d = json.loads(s.string or "")
        except json.JSONDecodeError:
            continue
        if isinstance(d, dict) and d.get("@type") == "JobPosting":
            desc = BeautifulSoup(html.unescape(d.get("description", "")), "html.parser").get_text(" ", strip=True)
            addr = (d.get("jobLocation") or {}).get("address") or {}
            return {
                "description": re.sub(r"\s+", " ", desc),
                "posted_at": d.get("datePosted"), "valid_through": d.get("validThrough"),
                "employment_type": d.get("employmentType"),
                "address": addr.get("streetAddress") if isinstance(addr, dict) else None,
                "raw": d,
            }
    raise ScrapeParseError("no JobPosting JSON-LD on detail page")


# ------------------------------ orchestration ----------------------------- #
def is_stale(trade: str, force: bool = False) -> bool:
    """True when this trade has never been scraped successfully, or not within REFRESH_TTL_HOURS."""
    if force:
        return True
    with db.connect() as con:
        last = db.last_ok_scrape(con, trade)
    return not last or datetime.fromisoformat(last) < datetime.now(timezone.utc) - timedelta(hours=config.REFRESH_TTL_HOURS)


def scrape_trade(f: Fetcher, trade: str, max_pages: int = 1) -> dict:
    """Scrape one trade's category page(s) and upsert the cards. Failures are logged and returned, never hidden.
    Network I/O runs with no database connection held open."""
    slug = TRADE_SLUGS[trade]
    started = db.now()
    pages = seen = dropped = 0
    try:
        for p in range(1, max_pages + 1):
            url = f"{BASE}/jobs/{slug}-jobs-in-bengaluru" + (f"?page={p}" if p > 1 else "")
            cards = parse_cards(f.get(url), trade)
            if not cards:
                if p == 1:
                    raise ScrapeParseError(f"no job cards found at {url} (layout change or empty category)")
                break
            pages += 1
            kept = [c for c in cards if re.search(TRADE_KEYWORDS[trade], c["title"], re.I)]
            dropped += len(cards) - len(kept)
            with db.connect() as con:
                for c in kept:
                    db.upsert_card(con, c)
            seen += len(kept)
        with db.connect() as con:
            db.log_run(con, started_at=started, source=SOURCE, trade=trade, status="ok", pages=pages, listings_seen=seen)
        return {"trade": trade, "status": "ok", "pages": pages, "listings_seen": seen, "dropped_irrelevant": dropped}
    except ScrapeError as e:
        with db.connect() as con:
            db.log_run(con, started_at=started, source=SOURCE, trade=trade, status="failed", pages=pages,
                       listings_seen=seen, error_type=type(e).__name__, error_message=str(e))
        return {"trade": trade, "status": "failed", "error_type": type(e).__name__, "error": str(e)}


def fetch_missing_details(f: Fetcher, urls: list[str], limit: int = 12) -> dict:
    """Fetch full descriptions for listings that only have a card. Each write is its own short transaction."""
    fetched, failed = 0, []
    for u in urls:
        if fetched >= limit:
            break
        with db.connect() as con:
            row = con.execute("SELECT detail_acquired_at FROM listings WHERE url=?", (u,)).fetchone()
        if row and row["detail_acquired_at"]:
            continue
        try:
            detail = parse_detail(f.get(u))
        except ScrapeError as e:
            failed.append({"url": u, "error": f"{type(e).__name__}: {e}"})
            continue
        with db.connect() as con:
            db.save_detail(con, u, detail)
        fetched += 1
    return {"fetched": fetched, "failed": failed}
