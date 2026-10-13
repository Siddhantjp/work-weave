"""Reproducible experiment on REAL cached listings with SIMULATED workers.
Writes data/experiments/exp_n{n}_seed{seed}.json. Every number in it is produced by the run."""
import json
import time
from pathlib import Path

from .. import config, db
from .elicitation import FIELDS, elicit_node
from .market import build_market, compare
from .simulation import generate


def extraction_pr(sims) -> dict:
    """Field-level precision/recall of the Elicitor on single-shot descriptions (no clarification)."""
    tp = fp = fn = 0
    per_field = {f: [0, 0, 0] for f in FIELDS}
    for wid, gt in sims:
        got = elicit_node({"description": gt.description, "answers": []})["draft"]
        for f in FIELDS:
            a, b = getattr(gt, f), getattr(got, f)
            a_set, b_set = a not in (None, [], False), b not in (None, [], False)
            if f == "skills" and a_set and b_set:
                ok = bool({t for s in a for t in s.lower().split()} & {t for s in b for t in s.lower().split()})
            elif isinstance(a, str) and isinstance(b, str):
                ok = a.lower() == b.lower()
            else:
                ok = a == b
            if a_set and b_set and ok:
                tp += 1; per_field[f][0] += 1
            else:
                if b_set:
                    fp += 1; per_field[f][1] += 1
                if a_set:
                    fn += 1; per_field[f][2] += 1
    p, r = tp / (tp + fp) if tp + fp else None, tp / (tp + fn) if tp + fn else None
    return {"workers": len(sims), "tp": tp, "fp": fp, "fn": fn, "precision": p, "recall": r,
            "per_field_tp_fp_fn": per_field, "note": "single-shot extraction vs generator ground truth (no clarification rounds)"}


def run_experiment(n: int, seed: int, baseline_seeds: int = 20, skip_extraction: bool = False, log=print) -> dict:
    t0 = time.time()
    sims = generate(n, seed)
    workers = dict(sims)
    with db.connect() as con:
        snap = dict(zip(("listings", "first_acquired", "last_acquired"),
                        con.execute("SELECT COUNT(*), MIN(acquired_at), MAX(acquired_at) FROM listings").fetchone()))
    log(f"[SIMULATED workers: {n}, seed {seed}] real listings in cache: {snap}")
    ex = None if skip_extraction else extraction_pr(sims)
    if ex:
        log(f"extraction precision={ex['precision']:.3f} recall={ex['recall']:.3f}")
    log("building preference lists (worker agents, employer agents)...")
    market = build_market(workers, log=log)
    inst = market["instance"]
    log(f"market: {len(inst.workers)} workers, {len(inst.employers)} listings, {sum(inst.capacity.values())} seats")
    cmp = compare(market, workers, baseline_seeds)
    out = {"config": {"n": n, "seed": seed, "model": config.GROQ_MODEL, "simulated_workers": True,
                      "worker_mix_note": "ASSUMED weights, not calibrated to a national survey"},
           "listing_snapshot": snap, "extraction": ex,
           "market": {"workers": len(inst.workers), "listings": len(inst.employers), "seats": sum(inst.capacity.values()),
                      "worker_list_lengths": {w: len(l) for w, l in inst.worker_prefs.items()}},
           "comparison": {k: v for k, v in cmp.items() if k != "da_result"}, "da_result": cmp["da_result"],
           "workers": {w: p.model_dump() for w, p in workers.items()},
           "listings": {u: {"title": r["title"], "employer": r["employer"], "locality": r["locality"], "salary_text": r["salary_text"]}
                        for u, r in market["rows"].items()},
           "worker_preferences": {w: [{"url": r["url"], "rank": r["rank"], "rationale": r["rationale"], "distance_km": r["distance_km"],
                                       "verdict": r["verdict"].status, "missing": r["verdict"].missing} for r in o["ranked"]]
                                  for w, o in market["worker_out"].items()},
           "employer_preferences": market["emp_meta"] | {},
           "employer_rankings": inst.employer_prefs, "capacity": inst.capacity,
           "seconds": round(time.time() - t0)}
    path = Path(config.ROOT) / "data" / "experiments"
    path.mkdir(parents=True, exist_ok=True)
    f = path / f"exp_n{n}_seed{seed}.json"
    f.write_text(json.dumps(out, indent=1, default=str), encoding="utf8")
    log(f"saved {f}")
    return out
