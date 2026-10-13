"""Tests for assembly pieces that need no network/LLM. Ids are abstract fixtures."""
import random

from app.matching.baseline import keyword_rankings, run_baseline
from app.matching.core import Instance, deferred_acceptance
from app.matching.employer import employer_view, hard_filter
from app.matching.graph import run_matching
from app.models import ListingRequirements, WorkerProfile
from tests.test_matching_core import random_instance


def req(**kw):
    base = dict(shift="unknown", shift_start_hour=None, shift_end_hour=None, min_experience_months=None,
                vehicle_required="unknown", licence_required="unknown", openings=None, wage_min=None,
                wage_max=None, skills_required=[], evidence="")
    return ListingRequirements(**{**base, **kw})


def test_langgraph_matching_equals_direct_algorithm_and_checkpoints_every_round():
    for seed in range(25):
        inst = random_instance(random.Random(seed), 7, 4)
        out = run_matching(inst, thread_id=f"t{seed}")
        direct = deferred_acceptance(inst)
        assert out["result"]["assignment"] == direct.assignment
        assert out["result"]["rounds"] == direct.rounds
        assert out["result"]["audit"]["is_stable"]
        assert out["checkpoints"] >= direct.rounds       # at least one checkpoint per round


def test_unmatched_worker_gets_an_explanation():
    inst = Instance({"a": ["e"], "b": [], "c": ["e"]}, {"e": ["a"]}, {"e": 1})
    why = run_matching(inst)["result"]["unmatched_reasons"]
    assert set(why) == {"b", "c"} and "no feasible listing" in why["b"]


def test_employer_view_hides_worker_side_preferences():
    w = WorkerProfile(min_monthly_wage=50000, latest_shift_end_hour=20, desired_trades=["driver"], experience_months=12)
    v = employer_view(w, 3.2)
    assert "min_monthly_wage" not in v and "latest_shift_end_hour" not in v and "desired_trades" not in v
    assert v["experience_months"] == 12


def test_employer_hard_filter_uses_only_stated_requirements():
    w = WorkerProfile(experience_months=6)
    assert hard_filter(w, req()) == []                                    # nothing stated -> nothing to reject on
    assert len(hard_filter(w, req(vehicle_required="yes", min_experience_months=12))) == 2
    assert hard_filter(WorkerProfile(has_vehicle=True, experience_months=24), req(vehicle_required="yes", min_experience_months=12)) == []


def test_keyword_ranking_and_baseline_capacity():
    docs = {"d1": "delivery boy biker swiggy", "d2": "security guard night", "d3": "delivery driver"}
    kr = keyword_rankings({"w1": "delivery bike", "w2": "delivery", "w3": "cook"}, docs)
    assert kr["w1"][0] == "d1" and kr["w3"] == []
    a = run_baseline(kr, {"d1": 1, "d2": 1, "d3": 1}, seed=0)
    assert list(a.values()).count("d1") <= 1
    assert a["w3"] is None
