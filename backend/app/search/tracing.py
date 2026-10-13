"""LangSmith: run configuration, plus deterministic evaluator scores posted as feedback on a run.

Everything that talks to LangSmith here is best-effort: a tracing problem must never break a user's search.
"""
from __future__ import annotations

import os
import time
import uuid

from .. import config
from ..models import WorkerProfile
from .limits import check_limits


def tracing_on() -> bool:
    return os.getenv("LANGSMITH_TRACING", "false").lower() == "true" and bool(os.getenv("LANGSMITH_API_KEY"))


def new_run_id() -> uuid.UUID:
    return uuid.uuid4()


def run_config(user: str | None = None, run_id: uuid.UUID | None = None) -> dict:
    """One named, tagged, attributed root run per search; every node and LLM call nests under it."""
    cfg = {"run_name": "job_search_agentic_rag", "tags": ["agentic-rag", "apna.co", "groq", "langgraph"],
           "metadata": {"user": user or "anonymous", "session_id": user or "anonymous", "llm": config.GROQ_MODEL,
                        "source": "apna.co", "app": "workweave"}}
    if run_id is not None:
        cfg["run_id"] = run_id
    return cfg


def evaluate(final: dict) -> dict[str, tuple[float, str]]:
    """Code-based evaluators (no LLM). Each returns (score 0..1, explanation)."""
    out: dict[str, tuple[float, str]] = {}
    ranked, profile = final.get("ranked", []), final.get("profile")
    if isinstance(profile, WorkerProfile):
        violations = sum(1 for r in ranked if check_limits(profile, r["requirements"]).status == "hard_conflict")
        out["hard_limit_violations"] = (1.0 if violations == 0 else 0.0,
                                        f"{violations} of {len(ranked)} ranked jobs break the worker's hard limits (must be 0)")
    kept, dropped = final.get("kept_fields", 0), len(final.get("discarded", []))
    if kept + dropped:
        out["profile_grounding"] = (kept / (kept + dropped),
                                    f"{kept} profile fields verified in the worker's own words, {dropped} discarded as unsupported")
    out["source_fresh_or_live"] = (0.0 if final.get("refresh_failed") else 1.0,
                                   final.get("refresh_failed") or "apna.co checked live or cache still fresh")
    out["results_found"] = (min(1.0, len(ranked) / 3), f"{len(ranked)} suitable jobs returned")
    return out


def finalize(run_id: uuid.UUID, final: dict) -> dict:
    """Flush traces, post evaluator feedback to the root run, resolve its dashboard URL."""
    res: dict = {"trace_url": None, "feedback": [], "error": None}
    if not tracing_on():
        return res
    try:
        from langchain_core.tracers.langchain import wait_for_all_tracers
        from langsmith import Client
        wait_for_all_tracers()
        client, run = Client(), None
        for _ in range(8):                       # the run is ingested asynchronously
            try:
                run = client.read_run(run_id)
                break
            except Exception:
                time.sleep(2)
        if run is None:
            res["error"] = "trace not yet visible in LangSmith (it may appear shortly)"
            return res
        res["trace_url"] = client.get_run_url(run=run, project_name=os.getenv("LANGSMITH_PROJECT"))
        for key, (score, comment) in evaluate(final).items():
            client.create_feedback(run_id=run_id, key=key, score=score, comment=comment)
            res["feedback"].append({"key": key, "score": round(score, 3), "comment": comment})
    except Exception as e:
        res["error"] = f"{type(e).__name__}: {str(e)[:200]}"
    return res
