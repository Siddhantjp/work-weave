"""python -m scripts.run_experiment --n 20 --seed 7 [--skip-extraction]"""
import argparse
import json

from app.matching.experiment import run_experiment

ap = argparse.ArgumentParser()
ap.add_argument("--n", type=int, default=20)
ap.add_argument("--seed", type=int, default=7)
ap.add_argument("--baseline-seeds", type=int, default=20)
ap.add_argument("--skip-extraction", action="store_true")
a = ap.parse_args()
out = run_experiment(a.n, a.seed, a.baseline_seeds, a.skip_extraction)
c = out["comparison"]
print("\n== Deferred acceptance (LangGraph) ==", json.dumps(c["deferred_acceptance"]))
print("== Keyword baseline ==")
for k, v in c["baseline_over_seeds"].items():
    print("  ", k, v)
