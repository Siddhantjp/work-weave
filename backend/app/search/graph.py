"""Agentic RAG job search as ONE LangGraph, every step visible in LangSmith.

  understand -> check_source -> retrieve -> grade_documents -> augment -> grade_limits -> finish
     Groq #1      live apna.co    multi-query    corrective RAG:   Groq #2:     hard limits
  (profile +      scrape tool     MMR + RRF      off-topic and     read reqs,   enforced by
   query plan)                                   expired dropped   rank, explain code

Two decision points (after grade_documents and after grade_limits) loop back through `relax`, which adds
related trades and retrieves deeper. The worker's hard limits are never relaxed.
Two Groq calls per search (a third only if it relaxes after augmenting).
"""
from __future__ import annotations

import operator
import re
from datetime import date
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from .. import db
from ..models import ListingRequirements, WorkerProfile
from ..sources.apna import TRADE_KEYWORDS, TRADE_SLUGS
from ..sources.geo import distance_km
from .chains import augment_chain, plan_chain, understand_chain
from .extraction import verify_extraction
from .index import index_listings
from .limits import check_limits
from .retrieval import ListingRetriever, dedupe_near_dups, rrf_fuse
from .tools import fetch_details, scrape_apna
from .tracing import run_config

MIN_VIABLE = 3          # fewer suitable results than this triggers the relax loop
MAX_RELAX = 1           # relax at most once: bounds LLM calls and keeps the loop honest
RETRIEVE_K = 10         # documents per query per relax level
MAX_CANDIDATES = 10     # listings sent to the augment call (bounds tokens)


class State(TypedDict, total=False):
    request: str
    language: str                        # language the worker wrote in; explanations are written back in it
    profile: WorkerProfile
    given_profile: bool                  # True when a ready-made profile is supplied (simulations)
    force_refresh: bool
    queries: list[str]
    primary_trades: list[str]
    related_trades: list[str]
    relax_level: int
    candidates: list[dict]
    judged: list[dict]
    graded: list[dict]
    ranked: list[dict]
    refresh_failed: str | None
    discarded: list[str]
    kept_fields: int
    events: Annotated[list[dict], operator.add]


def ev(node: str, msg: str, **data) -> list[dict]:
    return [{"node": node, "message": msg, "data": data, "at": db.now()}]


def active_trades(s: State) -> list[str]:
    return s["primary_trades"] + (s["related_trades"] if s.get("relax_level", 0) >= 1 else [])


def can_relax(s: State) -> bool:
    return bool(s.get("related_trades")) and s.get("relax_level", 0) < MAX_RELAX


# ------------------------------ nodes ------------------------------------ #
def understand(s: State) -> dict:
    """Groq call #1: the worker's profile (quote-verified in code) and the retrieval plan."""
    if s.get("given_profile"):
        p = s["profile"]
        plan = plan_chain().invoke({"profile": p.model_dump_json(exclude={"simulated"})})
        return {"queries": plan.queries, "primary_trades": [t for t in p.desired_trades if t in TRADE_SLUGS],
                "related_trades": [t for t in plan.related_trades if t in TRADE_SLUGS and t not in p.desired_trades],
                "events": ev("understand", f"{len(plan.queries)} queries; trades {p.desired_trades}")}
    text = s["request"]
    x = understand_chain().invoke({"request": text})
    kept, dropped = verify_extraction(x, text)
    profile = WorkerProfile(simulated=False, description=text, **kept)
    return {"profile": profile, "language": x.language or "English", "queries": x.queries, "primary_trades": profile.desired_trades,
            "related_trades": [t for t in x.related_trades if t in TRADE_SLUGS and t not in profile.desired_trades],
            "discarded": dropped, "kept_fields": len(kept),
            "events": ev("understand", f"understood ({x.language or 'English'}): {sorted(kept)}; trades {profile.desired_trades}"
                         + (f"; ignored unsupported: {dropped}" if dropped else ""))}


def check_source(s: State) -> dict:
    """Tool call: look at apna.co live (skipped per trade while the cache is fresh)."""
    trades = active_trades(s)
    if not trades:
        return {"events": ev("check_source", "no recognised trade in the request; nothing to look up")}
    r = scrape_apna.invoke({"trades": trades, "force": s.get("force_refresh", False) and s.get("relax_level", 0) == 0})
    n = sum(x["listings_seen"] for x in r["scraped"])
    msg = f"apna.co checked live for {[x['trade'] for x in r['scraped']]} ({n} listings)" if r["scraped"] else ""
    if r["skipped_fresh"]:
        msg += ("; " if msg else "") + f"cache still fresh for {r['skipped_fresh']}"
    update = {"events": ev("check_source", msg or "no new scrape", result=r)}
    if r["failed"]:
        update["refresh_failed"] = "; ".join(f"{f['trade']}: {f['error']}" for f in r["failed"])
        update["events"] += ev("check_source", f"apna.co problem — using previously cached listings: {update['refresh_failed']}")
    return update


def retrieve(s: State) -> dict:
    """Multi-query dense retrieval (MMR, trade-filtered), Reciprocal Rank Fusion, near-duplicate collapse."""
    trades = active_trades(s)
    if not trades:
        return {"candidates": [], "events": ev("retrieve", "no trades to search")}
    index_listings()
    retriever = ListingRetriever(trades=trades, k=RETRIEVE_K * (1 + s.get("relax_level", 0)))
    lists = [retriever.invoke(q, config={"tags": ["dense", "mmr"], "metadata": {"query": q, "trades": trades}}) for q in s["queries"]]
    fused = rrf_fuse(lists)
    unique, dups = dedupe_near_dups(fused)
    cands = [{"url": d.metadata["url"], "score": sc, "title": d.metadata.get("title", "")} for d, sc in unique]
    return {"candidates": cands, "events": ev("retrieve", f"{len(s['queries'])} queries -> {len(fused)} fused hits (RRF), "
                                              f"{dups} repost duplicates collapsed -> {len(cands)} candidates")}


def grade_documents(s: State) -> dict:
    """Corrective-RAG step in plain code, before any LLM tokens are spent: apna pads sparse categories with
    neighbouring trades, and old listings linger in the index, so drop off-topic and expired documents."""
    patterns = [TRADE_KEYWORDS[t] for t in active_trades(s) if t in TRADE_KEYWORDS]
    cands = s.get("candidates", [])
    with db.connect() as con:
        valid_through = {c["url"]: (con.execute("SELECT valid_through FROM listings WHERE url=?", (c["url"],)).fetchone() or [None])[0]
                         for c in cands}
    today = date.today().isoformat()
    keep, off_topic, expired = [], 0, 0
    for c in cands:
        if not any(re.search(p, c["title"], re.I) for p in patterns):
            off_topic += 1
        elif valid_through[c["url"]] and valid_through[c["url"]] < today:
            expired += 1
        else:
            keep.append(c)
    return {"candidates": keep[:MAX_CANDIDATES],
            "events": ev("grade_documents", f"{len(keep)} kept; {off_topic} off-topic and {expired} expired dropped (no LLM used)")}


def route_after_documents(s: State) -> str:
    return "relax" if len(s.get("candidates", [])) < MIN_VIABLE and can_relax(s) else "augment"


def augment(s: State) -> dict:
    """Groq call #2 (RAG augmentation): read each retrieved listing's requirements and rank them for this worker."""
    cands = s.get("candidates", [])[:MAX_CANDIDATES]
    if not cands:
        return {"judged": [], "events": ev("augment", "nothing retrieved to augment")}
    urls = [c["url"] for c in cands]
    details = fetch_details(urls)
    with db.connect() as con:
        rows = {u: con.execute("SELECT * FROM listings WHERE url=?", (u,)).fetchone() for u in urls}
    p = s["profile"]
    dist = {u: distance_km(p.home_locality, rows[u]["locality"]) for u in urls}
    lines = [f"[{i}] {rows[u]['title']} | {rows[u]['employer']} | {rows[u]['locality']} | "
             f"distance_km={'unknown' if dist[u] is None else dist[u]} | {rows[u]['salary_text'] or 'pay not stated'} | "
             f"tags={rows[u]['tags_json']} | description: {(rows[u]['description'] or 'not fetched')[:380]}" for i, u in enumerate(urls)]
    res = augment_chain().invoke({"worker": p.model_dump_json(exclude={"simulated", "description"}), "request": p.description,
                                  "listings": "\n".join(lines), "language": s.get("language", "English")})
    seen, order = set(), []
    for it in res.items:
        if 0 <= it.id < len(urls) and it.id not in seen:
            seen.add(it.id)
            order.append(it)
    omitted = [i for i in range(len(urls)) if i not in seen]
    judged = [{"url": urls[it.id], "rationale": it.rationale, "distance_km": dist[urls[it.id]],
               "requirements": ListingRequirements(shift=it.shift, shift_start_hour=it.shift_start_hour, shift_end_hour=it.shift_end_hour,
                                                   min_experience_months=it.min_experience_months, vehicle_required=it.vehicle_required,
                                                   licence_required="unknown", openings=it.openings, wage_min=it.wage_min,
                                                   wage_max=it.wage_max, skills_required=[], evidence="")} for it in order]
    judged += [{"url": urls[i], "rationale": "(not ranked by the model; appended in retrieval order)",
                "distance_km": dist[urls[i]], "requirements": None} for i in omitted]
    note = f"fetched {details['fetched']} full descriptions; " if details.get("fetched") else ""
    return {"judged": judged, "events": ev("augment", f"{note}Groq read requirements and ranked {len(order)} listings"
                                           + (f" ({len(omitted)} omitted by the model were appended)" if omitted else ""))}


def grade_limits(s: State) -> dict:
    """The worker's hard limits, enforced by code (never by the LLM)."""
    out = [{**j, "verdict": check_limits(s["profile"], j["requirements"])} for j in s.get("judged", [])]
    counts = {k: sum(1 for g in out if g["verdict"].status == k) for k in ("feasible", "needs_clarification", "hard_conflict")}
    return {"graded": out, "events": ev("grade_limits", f"hard limits checked by code: {counts}", counts=counts)}


def route_after_limits(s: State) -> str:
    viable = [g for g in s.get("graded", []) if g["verdict"].status != "hard_conflict"]
    return "relax" if len(viable) < MIN_VIABLE and can_relax(s) else "finish"


def relax(s: State) -> dict:
    return {"relax_level": s.get("relax_level", 0) + 1,
            "events": ev("relax", f"too few suitable listings — also searching related trades {s['related_trades']} and retrieving deeper "
                                  "(your hard limits are never relaxed)")}


def finish(s: State) -> dict:
    scores = {c["url"]: c["score"] for c in s.get("candidates", [])}
    ranked = []
    for g in s.get("graded", []):
        if g["verdict"].status != "hard_conflict":
            ranked.append({"url": g["url"], "rank": len(ranked) + 1, "rationale": g["rationale"], "verdict": g["verdict"],
                           "requirements": g["requirements"], "distance_km": g["distance_km"], "retrieval_score": scores.get(g["url"])})
    removed = sum(1 for g in s.get("graded", []) if g["verdict"].status == "hard_conflict")
    return {"ranked": ranked, "events": ev("finish", f"{len(ranked)} suitable listings" + (f"; {removed} removed by your hard limits" if removed else ""))}


def build_graph():
    g = StateGraph(State)
    for fn in (understand, check_source, retrieve, grade_documents, augment, grade_limits, relax, finish):
        g.add_node(fn.__name__, fn)
    g.add_edge(START, "understand")
    g.add_edge("understand", "check_source")
    g.add_edge("check_source", "retrieve")
    g.add_edge("retrieve", "grade_documents")
    g.add_conditional_edges("grade_documents", route_after_documents, {"relax": "relax", "augment": "augment"})
    g.add_edge("augment", "grade_limits")
    g.add_conditional_edges("grade_limits", route_after_limits, {"relax": "relax", "finish": "finish"})
    g.add_edge("relax", "check_source")          # the agentic loop
    g.add_edge("finish", END)
    return g.compile(name="job_search_agentic_rag")


def find_jobs(profile: WorkerProfile, force_refresh: bool = False) -> State:
    """Run the graph for a ready-made profile (used by the stable-matching simulations)."""
    return build_graph().invoke({"profile": profile, "given_profile": True, "force_refresh": force_refresh, "events": []},
                                run_config("simulation"))
