"""Locality -> coordinates via OpenStreetMap Nominatim (usage policy: <=1 req/s, identifying
User-Agent, cache results). Distances are computed here, in code, never guessed by the LLM."""
from __future__ import annotations

import math
import re
import time

import httpx

from .. import db

UA = "AcademicResearchBot/0.1 (university project on stable matching)"
BBOX = (12.70, 13.30, 77.35, 77.90)   # lat_min, lat_max, lon_min, lon_max (Bengaluru)
_last = 0.0


def _clean(loc: str) -> str:
    return re.sub(r"\s*,?\s*Bengaluru/Bangalore\s*$", "", loc).strip()


def geocode(locality: str | None) -> tuple[float, float] | None:
    global _last
    if not locality or not _clean(locality):
        return None
    q = f"{_clean(locality)}, Bengaluru, Karnataka, India"
    with db.connect() as con:
        c = con.execute("SELECT lat, lon FROM geo_cache WHERE query=?", (q,)).fetchone()
    if c:
        return (c["lat"], c["lon"]) if c["lat"] is not None else None
    time.sleep(max(0.0, 1.1 - (time.monotonic() - _last)))          # network I/O with no DB connection held
    _last = time.monotonic()
    lat = lon = name = None
    try:
        r = httpx.get("https://nominatim.openstreetmap.org/search", headers={"User-Agent": UA}, timeout=20,
                      params={"q": q, "format": "jsonv2", "limit": 1, "countrycodes": "in"})
        r.raise_for_status()
        hits = r.json()
    except (httpx.HTTPError, ValueError):
        return None            # transient failure: do not cache, try again next time
    if hits:
        la, lo = float(hits[0]["lat"]), float(hits[0]["lon"])
        if BBOX[0] <= la <= BBOX[1] and BBOX[2] <= lo <= BBOX[3]:
            lat, lon, name = la, lo, hits[0].get("display_name")
    with db.connect() as con:
        con.execute("INSERT OR REPLACE INTO geo_cache VALUES (?,?,?,?,?)", (q, lat, lon, name, db.now()))
    return (lat, lon) if lat is not None else None


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(h))


def distance_km(home: str | None, job_locality: str | None) -> float | None:
    """Straight-line km between two localities; None if either cannot be resolved."""
    a, b = geocode(home), geocode(job_locality)
    return round(haversine_km(a, b), 1) if a and b else None
