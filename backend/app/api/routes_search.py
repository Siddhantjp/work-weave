"""Search: start the agentic-RAG LangGraph, follow it step by step, read past searches."""
from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import auth, db, tasks
from ..accounts import store
from ..accounts.store import AuthUser
from ..search import tracing
from ..search.graph import build_graph

router = APIRouter(prefix="/api", tags=["search"])


class SearchIn(BaseModel):
    request: str
    force_refresh: bool = False


def _jsonable(o):
    if hasattr(o, "model_dump"):
        return o.model_dump()
    if hasattr(o, "__dataclass_fields__"):
        return {k: _jsonable(getattr(o, k)) for k in o.__dataclass_fields__}
    if isinstance(o, dict):
        return {k: _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, set)):
        return [_jsonable(v) for v in o]
    return o


def _build_result(final: dict) -> dict:
    """Shape the graph's final state for the UI (joins ranked listings with their stored fields)."""
    with db.connect() as con:
        rows = {r["url"]: dict(r) for r in con.execute("SELECT * FROM listings")}
    ranked = []
    for r in final.get("ranked", []):
        row = rows[r["url"]]
        ranked.append({"rank": r["rank"], "rationale": r["rationale"], "url": r["url"], "title": row["title"], "employer": row["employer"],
                       "locality": row["locality"], "salary_text": row["salary_text"], "acquired_at": row["acquired_at"],
                       "posted_at": row["posted_at"], "valid_through": row["valid_through"], "distance_km": r["distance_km"],
                       "verdict": _jsonable(r["verdict"]), "requirements": _jsonable(r["requirements"])})
    removed = [{"title": rows[g["url"]]["title"], "employer": rows[g["url"]]["employer"], "conflicts": g["verdict"].conflicts}
               for g in final.get("graded", []) if g["verdict"].status == "hard_conflict"]
    return {"profile": _jsonable(final.get("profile")), "language": final.get("language", "English"), "ranked": ranked, "removed_by_hard_limits": removed,
            "refresh_failed": final.get("refresh_failed"), "ignored_unsupported": final.get("discarded", [])}


@router.post("/search")
def start_search(body: SearchIn, user: AuthUser = Depends(auth.current_user)):
    text = body.request.strip()
    if len(text) < 5:
        raise HTTPException(422, "Tell us what job you want (a sentence is enough).")
    if tasks.is_running("search", user.id):
        raise HTTPException(409, "A search is already running for you. Wait for it to finish.")
    search_id = store.start_search(user.id, text)

    def run(emit):
        run_id, final = tracing.new_run_id(), {}
        try:
            for chunk in build_graph().stream({"request": text, "force_refresh": body.force_refresh, "events": []},
                                              tracing.run_config(user.id, run_id), stream_mode="updates"):
                for update in chunk.values():
                    for event in update.get("events", []):
                        emit(event)
                    final.update(update)
            result = _build_result(final)
            lsm = tracing.finalize(run_id, final)                  # flush trace, post evaluator scores, resolve link
            result["langsmith"] = {**lsm, "project": os.getenv("LANGSMITH_PROJECT"), "run_id": str(run_id)}
            emit({"node": "langsmith", "message": f"trace recorded; {len(lsm['feedback'])} evaluator scores posted"
                  if lsm["trace_url"] else f"tracing: {lsm['error'] or 'off'}"})
            store.finish_search(search_id, result={k: v for k, v in result.items() if k != "langsmith"})
            return result
        except Exception as e:
            store.finish_search(search_id, error=f"{type(e).__name__}: {e}")
            raise

    return {"task": tasks.start("search", run, owner=user.id)}


@router.get("/tasks/{task_id}")
def task_status(task_id: str, user: AuthUser = Depends(auth.current_user)):
    t = tasks.get(task_id, user.id)
    if not t:
        raise HTTPException(404, "That search is no longer available (the server may have restarted). Please search again.")
    return _jsonable({k: v for k, v in t.items() if k != "owner"})


@router.get("/searches")
def past_searches(user: AuthUser = Depends(auth.current_user)):
    return store.list_searches(user.id)


@router.delete("/searches")
def clear_history(user: AuthUser = Depends(auth.current_user)):
    return {"deleted": store.clear_searches(user.id)}
