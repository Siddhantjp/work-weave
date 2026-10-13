"""In-process background tasks, so a long LangGraph run can stream its steps to the UI.

Named `tasks` (not "jobs") to keep it distinct from job *listings*.
"""
from __future__ import annotations

import threading
import traceback
import uuid
from typing import Any, Callable

MAX_KEPT = 100
TASKS: dict[str, dict] = {}


def start(kind: str, fn: Callable[[Callable[[dict], None]], Any], owner: str | None = None) -> str:
    """Run fn(emit) in a thread. emit(event) appends a progress event; fn's return value becomes the result."""
    tid = uuid.uuid4().hex[:12]
    task = {"id": tid, "kind": kind, "owner": owner, "status": "running", "events": [], "result": None, "error": None}
    TASKS[tid] = task
    for old in list(TASKS)[:-MAX_KEPT]:                      # bounded memory
        if TASKS[old]["status"] != "running":
            del TASKS[old]

    def run() -> None:
        try:
            task["result"] = fn(task["events"].append)
            task["status"] = "done"
        except Exception as e:                               # surfaced to the UI, never swallowed
            task["status"] = "failed"
            task["error"] = f"{type(e).__name__}: {e}"
            task["trace"] = traceback.format_exc()[-1500:]

    threading.Thread(target=run, daemon=True).start()
    return tid


def get(tid: str, owner: str) -> dict | None:
    t = TASKS.get(tid)
    return t if t and t["owner"] == owner else None


def is_running(kind: str, owner: str) -> bool:
    return any(t["kind"] == kind and t["owner"] == owner and t["status"] == "running" for t in TASKS.values())
