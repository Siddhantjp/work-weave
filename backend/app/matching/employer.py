"""Employer Preference Agent.

Builds, for ONE listing, a strict ranking of applicants using ONLY the listing's stated
requirements. Deliberately BLIND to worker-side utilities: the worker's wage floor, shift
limits and ranking of this listing are never shown to it (enforced by `employer_view`).

Step 1 (code):  hard requirement filter -> unacceptable applicants are not ranked.
Step 2 (LLM):   rank the remaining applicants with a rationale each.
Step 3 (code):  validate the permutation; omissions are appended in a deterministic order.
"""
from __future__ import annotations

from dataclasses import dataclass

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from ..llm import invoke_structured
from ..models import ListingRequirements, WorkerProfile


def employer_view(w: WorkerProfile, distance_km: float | None) -> dict:
    """The ONLY worker information an employer agent may see. Worker preferences
    (min wage, shift limits, desired trades, rankings) are excluded by construction."""
    return {"skills": w.skills, "experience_months": w.experience_months, "has_vehicle": w.has_vehicle,
            "vehicle_type": w.vehicle_type, "owns_tools": w.owns_tools, "distance_km_from_listing": distance_km}


def hard_filter(w: WorkerProfile, r: ListingRequirements) -> list[str]:
    """Reasons the employer cannot accept this worker (empty = acceptable). Stated requirements only."""
    why = []
    if r.vehicle_required == "yes" and w.has_vehicle is not True:
        why.append("listing requires a vehicle; worker has not stated owning one")
    if r.min_experience_months and (w.experience_months or 0) < r.min_experience_months:
        why.append(f"listing requires {r.min_experience_months} months experience; worker has {w.experience_months or 0}")
    return why


class _Item(BaseModel):
    id: int
    rationale: str = Field(description="1-2 sentences using only listing requirements and the applicant facts given")


class _Ranking(BaseModel):
    ranked: list[_Item]


@dataclass
class EmployerList:
    ranking: list[str]                  # worker ids, best first
    rationales: dict[str, str]
    rejected: dict[str, list[str]]      # worker id -> hard-requirement reasons
    appended: list[str]                 # ids the model omitted


def rank_applicants(listing_title: str, employer: str, req: ListingRequirements,
                    applicants: dict[str, tuple[WorkerProfile, float | None]]) -> EmployerList:
    rejected, ok = {}, {}
    for wid, (w, d) in sorted(applicants.items()):
        why = hard_filter(w, req)
        if why:
            rejected[wid] = why
        else:
            ok[wid] = (w, d)
    ids = sorted(ok)
    if not ids:
        return EmployerList([], {}, rejected, [])
    if len(ids) == 1:
        return EmployerList(ids, {ids[0]: "only applicant meeting the stated requirements"}, rejected, [])
    lines = [f"[{i}] {employer_view(ok[w][0], ok[w][1])}" for i, w in enumerate(ids)]
    res = invoke_structured(_Ranking, [
        SystemMessage("You are an employer's hiring assistant. Rank applicants from MOST to LEAST preferred using ONLY the listing's "
                      "stated requirements and the applicant facts shown. Prefer applicants who match the stated skills, have more relevant "
                      "experience, own required equipment/vehicle, and live closer. Unknown facts are a mild negative. You know nothing "
                      "about what applicants want. Return every id exactly once. Reply with JSON values, not the schema."),
        HumanMessage(f"LISTING: {listing_title} at {employer}\nREQUIREMENTS: {req.model_dump_json(exclude={'evidence'})}\n\nAPPLICANTS:\n" + "\n".join(lines)),
    ])
    seen, order, rat = set(), [], {}
    for it in res.ranked:
        if 0 <= it.id < len(ids) and it.id not in seen:
            seen.add(it.id)
            order.append(ids[it.id])
            rat[ids[it.id]] = it.rationale
    appended = [ids[i] for i in range(len(ids)) if i not in seen]
    for w in appended:
        rat[w] = "(not ranked by the model; appended in id order)"
    return EmployerList(order + appended, rat, rejected, appended)
