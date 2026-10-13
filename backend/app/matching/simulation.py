"""SIMULATED worker generator. Every worker produced here is synthetic and carries simulated=True.

Honesty note: the sampling weights below are ASSUMPTIONS chosen for a plausible Bengaluru mix.
They are NOT yet calibrated against PLFS or any national survey; the brief's "grounded in survey
statistics" claim must not be made until they are. Localities are sampled from localities that
appear in REAL scraped listings, so distances are meaningful.

Each worker comes with (a) a ground-truth profile and (b) a natural-language description that
states exactly the ground-truth fields, enabling extraction precision/recall measurement.
"""
from __future__ import annotations

import random

from .. import db
from ..models import WorkerProfile

# trade -> (sampling weight, P(owns vehicle), P(owns tools), skills phrase)       [ASSUMED]
TRADE_MIX = {
    "delivery": (0.30, 0.80, 0.0, "delivery"),
    "driver": (0.20, 0.30, 0.0, "driving"),
    "domestic worker": (0.15, 0.05, 0.0, "housekeeping and cleaning"),
    "security guard": (0.10, 0.10, 0.0, "security guard duty"),
    "electrician": (0.10, 0.40, 0.65, "electrical wiring"),
    "cook": (0.10, 0.10, 0.0, "cooking"),
    "plumber": (0.05, 0.40, 0.65, "plumbing and pipe fitting"),
}
EXPERIENCE_MONTHS = [0, 6, 12, 18, 24, 36, 60, 96]
SHIFT_LIMITS = [18, 20, 21, 22]


def real_localities(min_listings: int = 1) -> list[str]:
    with db.connect() as con:
        rows = con.execute("SELECT locality, COUNT(*) n FROM listings WHERE locality IS NOT NULL AND locality != 'Bengaluru/Bangalore' "
                           "GROUP BY locality HAVING n >= ? ORDER BY locality", (min_listings,)).fetchall()
    return [r["locality"].replace(", Bengaluru/Bangalore", "") for r in rows]


def _fmt_exp(m: int) -> str:
    if m == 0:
        return "I am a fresher with no experience"
    return f"I have {m // 12} years of experience" if m % 12 == 0 and m >= 12 else f"I have {m} months of experience"


def generate(n: int, seed: int, localities: list[str] | None = None) -> list[tuple[str, WorkerProfile]]:
    rng = random.Random(seed)
    locs = localities or real_localities()
    if not locs:
        raise RuntimeError("no real localities cached; run the scraper first (no fabricated fallback)")
    trades, weights = zip(*[(t, v[0]) for t, v in TRADE_MIX.items()])
    out = []
    for i in range(n):
        t = rng.choices(trades, weights)[0]
        _, pv, pt, skill = TRADE_MIX[t]
        exp = rng.choice(EXPERIENCE_MONTHS)
        loc = rng.choice(locs)
        veh = rng.random() < pv
        tools = (rng.random() < pt) if pt else None
        lim = rng.choice(SHIFT_LIMITS) if rng.random() < 0.35 else None
        parts = [f"I do {skill} work", _fmt_exp(exp), f"I live in {loc}"]
        if veh:
            parts.append("I own a two-wheeler")
        if tools:
            parts.append("I own my tools")
        if lim:
            h = lim - 12
            parts.append(f"I cannot work after {h} PM")
        desc = ". ".join(parts) + "."
        prof = WorkerProfile(simulated=True, description=desc, desired_trades=[t], skills=[skill], experience_months=exp,
                             home_locality=loc, has_vehicle=True if veh else None, vehicle_type="two-wheeler" if veh else None,
                             owns_tools=True if tools else None, latest_shift_end_hour=lim, avoid_night_shift=bool(lim))
        out.append((f"SIM-{i + 1:03d}", prof))
    return out
