"""Deterministic viability grading. Separates three outcomes the brief requires:
  hard_conflict       -> infeasible for the worker; never ranked
  needs_clarification -> information missing; kept, flagged
  feasible            -> no conflict found
Only the worker's own HARD constraints are applied here (shift limits). Employer-side
requirement mismatches are the Employer Preference Agent's job, not the worker's."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..models import ListingRequirements, WorkerProfile


@dataclass
class Verdict:
    status: str                               # feasible | needs_clarification | hard_conflict
    conflicts: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)   # soft-preference observations


def check_limits(w: WorkerProfile, r: ListingRequirements | None) -> Verdict:
    if r is None:
        return Verdict("needs_clarification", missing=["listing requirements not yet extracted"])
    conflicts, missing, notes = [], [], []

    shift_constrained = w.avoid_night_shift or w.latest_shift_end_hour is not None
    if shift_constrained:
        if r.shift == "night":
            conflicts.append("night shift conflicts with the worker's working-hour restriction")
        elif r.shift == "rotational" and w.avoid_night_shift:
            conflicts.append("rotational shifts may include nights; worker cannot work nights")
        elif r.shift_end_hour is not None and w.latest_shift_end_hour is not None:
            overnight = r.shift_start_hour is not None and r.shift_end_hour <= r.shift_start_hour
            if overnight or r.shift_end_hour > w.latest_shift_end_hour:
                conflicts.append(f"shift ends {r.shift_end_hour}:00 but worker must finish by {w.latest_shift_end_hour}:00")
        elif r.shift == "unknown" and r.shift_end_hour is None:
            missing.append("shift timing not stated in listing")

    if w.min_monthly_wage and r.wage_max is not None and r.wage_max < w.min_monthly_wage:
        notes.append(f"top of stated wage (₹{r.wage_max}) is below worker's minimum (₹{w.min_monthly_wage})")
    elif w.min_monthly_wage and r.wage_max is None:
        missing.append("wage not stated")

    if conflicts:
        return Verdict("hard_conflict", conflicts, missing, notes)
    return Verdict("needs_clarification" if missing else "feasible", [], missing, notes)
