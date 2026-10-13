"""Profile extraction guard: the worker's profile may only contain what they actually wrote.

The extraction model must quote the worker's own words for every field it fills. Quotes are verified by
string matching in code; a field without a verifiable quote is discarded and reported.
"""
from __future__ import annotations

import re
import unicodedata

from pydantic import BaseModel, Field

from ..sources.apna import TRADE_SLUGS

FIELDS = ["desired_trades", "skills", "experience_months", "home_locality", "has_vehicle",
          "vehicle_type", "owns_tools", "latest_shift_end_hour", "avoid_night_shift", "min_monthly_wage"]


class Evidence(BaseModel):
    field: str = Field(description=f"one of {FIELDS}")
    quote: str = Field(description="exact words copied from the worker's text that support the field")


class Extraction(BaseModel):
    desired_trades: list[str] = Field(description=f"only from {list(TRADE_SLUGS)}; empty if unclear")
    skills: list[str]
    experience_months: int | None
    home_locality: str | None
    has_vehicle: bool | None
    vehicle_type: str | None
    owns_tools: bool | None = Field(description="owns own work tools/equipment (e.g. electrician tools)")
    latest_shift_end_hour: int | None = Field(description="24h clock hour the worker must finish by; null if no limit stated")
    avoid_night_shift: bool | None
    min_monthly_wage: int | None
    evidence: list[Evidence]


def normalize(t: str) -> str:
    """Unicode-normalise (Indian scripts), lower-case, collapse whitespace/dashes: quote matching ignores formatting."""
    return re.sub(r"[\s‐-―]+", " ", unicodedata.normalize("NFKC", t).lower()).strip()


def verify_extraction(x: Extraction, text: str) -> tuple[dict, list[str]]:
    """Keep only fields with a quote that really occurs in the worker's text."""
    hay = normalize(text)
    supported = {e.field for e in x.evidence if e.field in FIELDS and e.quote.strip() and normalize(e.quote) in hay}
    kept, dropped = {}, []
    for f in FIELDS:
        v = getattr(x, f)
        if v is None or v is False or v == []:     # identity checks: 0 months of experience is a real answer
            continue
        if f in supported:
            kept[f] = v
        else:
            dropped.append(f"{f}={v!r} (no verifiable quote in the worker's own words)")
    if "desired_trades" in kept:
        kept["desired_trades"] = [t for t in kept["desired_trades"] if t in TRADE_SLUGS]
    return kept, dropped
