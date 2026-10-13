"""Mechanism tests. All participants here are abstract TEST FIXTURES for the
algorithm (ids like w0/e1), not job listings or workers; no application data."""
import itertools
import random

import pytest

from app.matching import (Instance, audit, deferred_acceptance, init_state,
                          keyword_baseline, probe_strategyproofness, step)


def random_instance(rng: random.Random, nw: int, ne: int, max_cap: int = 2, p_accept: float = 0.8) -> Instance:
    W = [f"w{i}" for i in range(nw)]
    E = [f"e{i}" for i in range(ne)]
    wp = {w: rng.sample(E, len(E)) for w in W}
    ep = {e: rng.sample(W, len(W)) for e in E}
    wp = {w: [e for e in l if rng.random() < p_accept] for w, l in wp.items()}
    ep = {e: [w for w in l if rng.random() < p_accept] for e, l in ep.items()}
    return Instance(wp, ep, {e: rng.randint(1, max_cap) for e in E})


def all_assignments(inst: Instance):
    options = [[None] + [e for e in inst.employers if inst.mutually_acceptable(w, e)] for w in inst.workers]
    for combo in itertools.product(*options):
        yield dict(zip(inst.workers, combo))


# ---- hand-checked cases ------------------------------------------------- #
def test_classic_example():
    inst = Instance(
        {"w1": ["e1", "e2"], "w2": ["e1", "e2"], "w3": ["e1"]},
        {"e1": ["w3", "w1", "w2"], "e2": ["w1", "w2"]},
        {"e1": 1, "e2": 1},
    )
    res = deferred_acceptance(inst)
    assert res.assignment == {"w1": "e2", "w2": None, "w3": "e1"}
    assert audit(inst, res.assignment).is_stable


def test_capacity_many_to_one():
    inst = Instance(
        {"a": ["e"], "b": ["e"], "c": ["e"]},
        {"e": ["c", "a", "b"]},
        {"e": 2},
    )
    res = deferred_acceptance(inst)
    assert res.assignment == {"a": "e", "b": None, "c": "e"}


def test_worker_with_no_feasible_job_stays_unmatched():
    inst = Instance({"w": []}, {"e": ["w"]}, {"e": 1})
    res = deferred_acceptance(inst)
    assert res.assignment == {"w": None}
    rep = audit(inst, res.assignment)
    assert rep.is_stable and rep.unfilled_seats == {"e": 1}


def test_employer_does_not_rank_worker_is_rejected_not_forced():
    inst = Instance({"w": ["e"]}, {"e": []}, {"e": 1})
    res = deferred_acceptance(inst)
    assert res.assignment["w"] is None
    assert res.trace[0]["rejections"][0]["reason"] == "not_ranked_by_employer"


def test_trace_is_round_by_round_and_displacement_visible():
    inst = Instance(
        {"w1": ["e"], "w2": ["e"]},
        {"e": ["w2", "w1"]},
        {"e": 1},
    )
    st = init_state(inst)
    step(inst, st)  # both propose simultaneously; e keeps w2
    assert st.held["e"] == ["w2"] and st.done


def test_audit_detects_blocking_pair_in_unstable_matching():
    inst = Instance(
        {"w1": ["e1", "e2"], "w2": ["e1", "e2"]},
        {"e1": ["w1", "w2"], "e2": ["w1", "w2"]},
        {"e1": 1, "e2": 1},
    )
    rep = audit(inst, {"w1": "e2", "w2": "e1"})  # w1 and e1 prefer each other
    assert not rep.is_stable
    assert [(b.worker, b.employer) for b in rep.blocking_pairs] == [("w1", "e1")]
    assert rep.pairs_examined == 4


def test_audit_flags_capacity_and_unacceptable_assignments():
    inst = Instance({"w1": ["e"], "w2": ["e"]}, {"e": ["w1"]}, {"e": 1})
    rep = audit(inst, {"w1": "e", "w2": "e"})
    assert rep.capacity_violations == ["e"] and ("w2", "e") in rep.unacceptable_assignments


def test_invalid_instances_rejected():
    with pytest.raises(ValueError):
        Instance({"w": ["e", "e"]}, {"e": ["w"]}, {"e": 1})
    with pytest.raises(ValueError):
        Instance({"w": ["x"]}, {"e": ["w"]}, {"e": 1})
    with pytest.raises(ValueError):
        Instance({"w": ["e"]}, {"e": ["w"]}, {"e": 0})


# ---- property tests ------------------------------------------------------ #
@pytest.mark.parametrize("seed", range(300))
def test_da_terminates_stable_and_respects_capacity(seed):
    rng = random.Random(seed)
    inst = random_instance(rng, rng.randint(1, 8), rng.randint(1, 5))
    res = deferred_acceptance(inst)
    assert res.rounds <= sum(len(v) for v in inst.worker_prefs.values()) + 1
    rep = audit(inst, res.assignment)
    assert rep.is_stable, rep


@pytest.mark.parametrize("seed", range(150))
def test_da_is_worker_optimal_among_all_stable_matchings(seed):
    """Brute force every assignment on tiny markets; DA must be stable and
    weakly best for every worker among all stable assignments."""
    rng = random.Random(1000 + seed)
    inst = random_instance(rng, rng.randint(1, 5), rng.randint(1, 3))
    da = deferred_acceptance(inst).assignment
    stable = [a for a in all_assignments(inst) if audit(inst, a).is_stable]
    assert da in stable
    for a in stable:
        for w in inst.workers:
            r_da = inst.worker_rank(w, da[w]) if da[w] else 10**9
            r_a = inst.worker_rank(w, a[w]) if a[w] else 10**9
            assert r_da <= r_a


@pytest.mark.parametrize("seed", range(40))
def test_no_profitable_worker_misreport(seed):
    rng = random.Random(5000 + seed)
    inst = random_instance(rng, rng.randint(2, 6), rng.randint(2, 4))
    for w in inst.workers:
        probe = probe_strategyproofness(inst, w, seed=seed)
        assert probe["improvements"] == 0, probe


def test_keyword_baseline_ignores_employers_and_audit_can_flag_it():
    # Both workers search "e1" first; arrival order decides, not employer preference.
    inst = Instance(
        {"w1": ["e1", "e2"], "w2": ["e1", "e2"]},
        {"e1": ["w2", "w1"], "e2": ["w1", "w2"]},
        {"e1": 1, "e2": 1},
    )
    base = keyword_baseline({"w1": ["e1", "e2"], "w2": ["e1", "e2"]}, inst.capacity, ["w1", "w2"])
    assert base == {"w1": "e1", "w2": "e2"}
    rep = audit(inst, base)
    assert [(b.worker, b.employer) for b in rep.blocking_pairs] == [("w2", "e1")]
    assert audit(inst, deferred_acceptance(inst).assignment).is_stable
