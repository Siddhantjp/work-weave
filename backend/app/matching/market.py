"""End-to-end market assembly + evaluation.

worker agents (Agentic RAG) -> worker lists ; employer agents -> employer lists ;
LangGraph deferred acceptance -> allocation ; deterministic audit ; keyword baseline.
"""
from __future__ import annotations

import statistics
from typing import Callable

from .. import db
from ..models import ListingRequirements, WorkerProfile
from ..search.graph import find_jobs
from ..search.limits import check_limits
from . import core
from .baseline import keyword_rankings, run_baseline
from .core import Instance
from .employer import rank_applicants
from .graph import run_matching
from .structuring import structure_listing


def build_market(workers: dict[str, WorkerProfile], log: Callable[[str], None] = print) -> dict:
    """Run both preference agents for every participant and assemble the matching instance."""
    wout, worker_lists, dists = {}, {}, {}
    for i, (wid, p) in enumerate(sorted(workers.items()), 1):
        out = find_jobs(p)
        wout[wid] = out
        worker_lists[wid] = [r["url"] for r in out["ranked"]]
        dists[wid] = {r["url"]: r["distance_km"] for r in out["ranked"]}
        log(f"  worker {wid} ({i}/{len(workers)}): {len(worker_lists[wid])} acceptable listings"
            + (f"  [REFRESH PROBLEM: {out['refresh_failed']}]" if out.get("refresh_failed") else ""))

    urls = sorted({u for l in worker_lists.values() for u in l})
    with db.connect() as con:
        rows = {u: con.execute("SELECT * FROM listings WHERE url=?", (u,)).fetchone() for u in urls}
    reqs: dict[str, ListingRequirements | None] = {}
    for u in urls:
        try:
            reqs[u] = structure_listing(rows[u])
        except Exception:
            reqs[u] = None

    emp_lists, emp_meta = {}, {}
    for j, u in enumerate(urls, 1):
        apps = {w: (workers[w], dists[w].get(u)) for w in workers if u in worker_lists[w]}
        r = reqs[u]
        if r is None:
            emp_lists[u] = sorted(apps)   # requirements unavailable: no basis to rank; deterministic id order
            emp_meta[u] = {"rejected": {}, "rationales": {}, "appended": sorted(apps), "note": "requirements unavailable"}
            continue
        el = rank_applicants(rows[u]["title"], rows[u]["employer"], r, apps)
        emp_lists[u] = el.ranking
        emp_meta[u] = {"rejected": el.rejected, "rationales": el.rationales, "appended": el.appended}
        if j % 10 == 0:
            log(f"  employer lists: {j}/{len(urls)}")

    capacity = {u: max(1, min(10, (reqs[u].openings if reqs[u] and reqs[u].openings else 1))) for u in urls}
    inst = Instance(worker_prefs=worker_lists, employer_prefs=emp_lists, capacity=capacity)
    return {"instance": inst, "worker_out": wout, "emp_meta": emp_meta, "requirements": reqs, "rows": rows}


def outcome_metrics(inst: Instance, assignment: dict, reqs: dict, workers: dict[str, WorkerProfile]) -> dict:
    rep = core.audit(inst, assignment)
    matched = [w for w, e in assignment.items() if e]
    ranks = [inst.worker_rank(w, assignment[w]) for w in matched if inst.worker_rank(w, assignment[w]) is not None]
    hard = sum(1 for w in matched if check_limits(workers[w], reqs.get(assignment[w])).status == "hard_conflict")
    return {"pairs_examined": rep.pairs_examined, "blocking_pairs": len(rep.blocking_pairs),
            "is_stable": rep.is_stable, "matched": len(matched), "unmatched": len(assignment) - len(matched),
            "placements_not_mutually_acceptable": len(rep.unacceptable_assignments),
            "placements_violating_worker_hard_constraints": hard,
            "mean_worker_rank_of_match": round(statistics.mean(ranks), 3) if ranks else None,
            "capacity_violations": len(rep.capacity_violations)}


def compare(market: dict, workers: dict[str, WorkerProfile], baseline_seeds: int = 20) -> dict:
    inst: Instance = market["instance"]
    reqs = market["requirements"]
    graph_out = run_matching(inst)
    da = graph_out["result"]
    da_metrics = outcome_metrics(inst, da["assignment"], reqs, workers)

    docs = {u: " ".join(filter(None, [r["title"], r["title"], r["title"], r["employer"], r["description"]])) for u, r in market["rows"].items()}
    queries = {w: " ".join([p.description] + p.skills + p.desired_trades) for w, p in workers.items()}
    kr = keyword_rankings(queries, docs)
    runs = [outcome_metrics(inst, run_baseline(kr, inst.capacity, s), reqs, workers) for s in range(baseline_seeds)]

    def agg(key):
        vals = [r[key] for r in runs if r[key] is not None]
        return {"mean": round(statistics.mean(vals), 2), "min": min(vals), "max": max(vals)} if vals else None

    keys = ["blocking_pairs", "matched", "unmatched", "placements_not_mutually_acceptable",
            "placements_violating_worker_hard_constraints", "mean_worker_rank_of_match"]
    ex_assign = run_baseline(kr, inst.capacity, 0)
    ex_rep = core.audit(inst, ex_assign)
    example = {"arrival_seed": 0, "assignment": ex_assign,
               "blocking_pairs": [{"worker": b.worker, "employer": b.employer, "worker_current": b.worker_current,
                                   "employer_displaced": b.employer_displaced} for b in ex_rep.blocking_pairs[:60]],
               "blocking_pair_total": len(ex_rep.blocking_pairs), "pairs_examined": ex_rep.pairs_examined}
    probes = [core.probe_strategyproofness(inst, w, seed=i) for i, w in enumerate(inst.workers) if inst.worker_prefs[w]]
    sp = {"workers_probed": len(probes), "misreports_tried": sum(p["misreports_tried"] for p in probes),
          "improvements": sum(p["improvements"] for p in probes),
          "scope": "algorithm only: fixed strict lists, workers propose; not the LLM pipeline, not employer misreports"}
    return {"strategyproofness": sp, "baseline_example": example, "deferred_acceptance": da_metrics, "baseline_over_seeds": {"n_arrival_orders": baseline_seeds, **{k: agg(k) for k in keys}},
            "baseline_runs": runs, "da_result": da, "events": graph_out["events"], "checkpoints": graph_out["checkpoints"]}
