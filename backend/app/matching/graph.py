"""Supervisor + Matcher + Auditor as a LangGraph state machine.

  init -> round (one deferred-acceptance proposal round) --[any worker still has an
  unexhausted option]--> round ...  --[converged]--> finish (deterministic audit + unmatched explanations)

Each round is one graph superstep, checkpointed. No LLM is called anywhere in this graph:
the allocation and the audit are pure code (app.matching.core).
"""
from __future__ import annotations

import operator
from dataclasses import asdict
from typing import Annotated, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from . import core
from .core import Instance, MatchState


class State(TypedDict, total=False):
    instance: dict                         # JSON-able Instance
    ms: dict                               # JSON-able MatchState
    result: dict
    events: Annotated[list[dict], operator.add]


def inst_to_dict(i: Instance) -> dict:
    return {"worker_prefs": i.worker_prefs, "employer_prefs": i.employer_prefs, "capacity": i.capacity}


def ms_from_dict(d: dict) -> MatchState:
    return MatchState(**d)


def init_node(s: State) -> dict:
    inst = Instance(**s["instance"])
    return {"ms": asdict(core.init_state(inst)),
            "events": [{"node": "supervisor", "message": f"market opened: {len(inst.workers)} workers, {len(inst.employers)} listings, "
                                                          f"{sum(inst.capacity.values())} seats"}]}


def round_node(s: State) -> dict:
    inst, ms = Instance(**s["instance"]), ms_from_dict(s["ms"])
    n_before = len(ms.trace)
    core.step(inst, ms)
    t = ms.trace[-1] if len(ms.trace) > n_before else None
    msg = (f"round {t['round']}: {len(t['proposals'])} proposals, {len(t['rejections'])} rejections, "
           f"{sum(len(v) for v in t['holds'].values())} workers held") if t else "no worker had an option left"
    return {"ms": asdict(ms), "events": [{"node": "matcher", "message": msg}]}


def converged(s: State) -> str:
    """Supervisor's conditional edge: loop while any unmatched worker retains an unexhausted option."""
    return "finish" if s["ms"]["done"] else "round"


def finish_node(s: State) -> dict:
    inst, ms = Instance(**s["instance"]), ms_from_dict(s["ms"])
    res = core.result_from_state(inst, ms)
    rep = core.audit(inst, res.assignment)
    why = {}
    for w in rep.unmatched_workers:
        if not inst.worker_prefs[w]:
            why[w] = "no feasible listing: every candidate was removed by the worker's hard constraints or retrieval"
        else:
            rej = ms.rejected[w]
            outranked = sum(1 for t in res.trace for r in t["rejections"] if r["worker"] == w and r["reason"] == "over_capacity_or_outranked")
            unranked = len(rej) - outranked
            why[w] = (f"proposed to all {len(inst.worker_prefs[w])} acceptable listings and was turned down by each "
                      f"({outranked} filled by employer-preferred applicants, {unranked} did not accept this worker's profile)")
    stable = rep.is_stable
    return {"result": {"assignment": res.assignment, "rounds": res.rounds, "trace": res.trace,
                       "audit": {"pairs_examined": rep.pairs_examined,
                                 "blocking_pairs": [asdict(b) for b in rep.blocking_pairs],
                                 "capacity_violations": rep.capacity_violations,
                                 "unacceptable_assignments": rep.unacceptable_assignments,
                                 "is_stable": stable, "unfilled_seats": rep.unfilled_seats},
                       "unmatched_reasons": why},
            "events": [{"node": "auditor", "message": f"{rep.pairs_examined} pairs examined; {len(rep.blocking_pairs)} blocking pairs; "
                                                      f"stable={stable}; {len(rep.unmatched_workers)} workers unmatched"}]}


def build_graph():
    g = StateGraph(State)
    g.add_node("init", init_node)
    g.add_node("round", round_node)
    g.add_node("finish", finish_node)
    g.add_edge(START, "init")
    g.add_edge("init", "round")
    g.add_conditional_edges("round", converged, {"round": "round", "finish": "finish"})
    g.add_edge("finish", END)
    return g.compile(checkpointer=MemorySaver())


def run_matching(inst: Instance, thread_id: str = "match") -> dict:
    """Run the whole market; every proposal round is checkpointed under `thread_id`."""
    graph = build_graph()
    out = graph.invoke({"instance": inst_to_dict(inst), "events": []},
                       {"configurable": {"thread_id": thread_id}, "recursion_limit": 10_000})
    out["checkpoints"] = sum(1 for _ in graph.get_state_history({"configurable": {"thread_id": thread_id}}))
    return out
