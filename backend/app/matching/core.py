"""Deterministic two-sided matching core: Gale-Shapley deferred acceptance (workers
propose, employers hold up to capacity) plus an exhaustive blocking-pair auditor.

No LLM is used anywhere in this module. Preference lists are inputs.

Model assumptions (stated so the guarantees are not over-claimed):
  * Each side supplies a strict ranking over the counterparts it finds acceptable.
    Lists may be incomplete; anything absent from a list is unacceptable.
  * A pair (w, e) is *mutually acceptable* iff w lists e AND e lists w.
  * Employers have responsive preferences over sets (they rank individuals) and
    a fixed integer capacity (many-to-one market, Roth & Sotomayor 1990).
"""
from __future__ import annotations

import itertools
import random
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Instance:
    worker_prefs: dict[str, list[str]]
    employer_prefs: dict[str, list[str]]
    capacity: dict[str, int]

    def __post_init__(self) -> None:
        for e, cap in self.capacity.items():
            if not isinstance(cap, int) or cap < 1:
                raise ValueError(f"capacity of {e!r} must be a positive int, got {cap!r}")
        if set(self.capacity) != set(self.employer_prefs):
            raise ValueError("capacity and employer_prefs must cover the same employers")
        for side, prefs, other in (
            ("worker", self.worker_prefs, self.employer_prefs),
            ("employer", self.employer_prefs, self.worker_prefs),
        ):
            for who, lst in prefs.items():
                if len(set(lst)) != len(lst):
                    raise ValueError(f"{side} {who!r} has duplicate entries (ranking must be strict)")
                unknown = [x for x in lst if x not in other]
                if unknown:
                    raise ValueError(f"{side} {who!r} ranks unknown ids {unknown}")

    @property
    def workers(self) -> list[str]:
        return sorted(self.worker_prefs)

    @property
    def employers(self) -> list[str]:
        return sorted(self.employer_prefs)

    def worker_rank(self, w: str, e: str) -> int | None:
        lst = self.worker_prefs[w]
        return lst.index(e) if e in lst else None

    def employer_rank(self, e: str, w: str) -> int | None:
        lst = self.employer_prefs[e]
        return lst.index(w) if w in lst else None

    def mutually_acceptable(self, w: str, e: str) -> bool:
        return self.worker_rank(w, e) is not None and self.employer_rank(e, w) is not None


# --------------------------------------------------------------------------- #
# Deferred acceptance, expressed as a single-round step function so that a
# LangGraph node can call it once per proposal round.
# --------------------------------------------------------------------------- #
@dataclass
class MatchState:
    next_idx: dict[str, int]                 # index of next list entry each worker will propose to
    held: dict[str, list[str]]               # employer -> tentatively held workers
    rejected: dict[str, list[str]]           # worker -> employers that rejected them
    round: int = 0
    done: bool = False
    trace: list[dict] = field(default_factory=list)


def init_state(inst: Instance) -> MatchState:
    return MatchState(
        next_idx={w: 0 for w in inst.workers},
        held={e: [] for e in inst.employers},
        rejected={w: [] for w in inst.workers},
    )


def _free_workers(inst: Instance, st: MatchState) -> list[str]:
    held_now = {w for ws in st.held.values() for w in ws}
    return [w for w in inst.workers if w not in held_now and st.next_idx[w] < len(inst.worker_prefs[w])]


def step(inst: Instance, st: MatchState) -> MatchState:
    """Run exactly one proposal round. Mutates and returns `st`."""
    proposers = _free_workers(inst, st)
    if not proposers:
        st.done = True
        return st
    st.round += 1
    proposals: list[tuple[str, str]] = []
    for w in proposers:
        e = inst.worker_prefs[w][st.next_idx[w]]
        st.next_idx[w] += 1
        proposals.append((w, e))

    by_emp: dict[str, list[str]] = {}
    for w, e in proposals:
        by_emp.setdefault(e, []).append(w)

    rejections: list[dict] = []
    for e in sorted(by_emp):
        pool = st.held[e] + by_emp[e]
        acceptable = [w for w in pool if inst.employer_rank(e, w) is not None]
        for w in pool:
            if w not in acceptable:
                rejections.append({"worker": w, "employer": e, "reason": "not_ranked_by_employer"})
                st.rejected[w].append(e)
        acceptable.sort(key=lambda w: inst.employer_rank(e, w))
        keep, drop = acceptable[: inst.capacity[e]], acceptable[inst.capacity[e]:]
        for w in drop:
            rejections.append({"worker": w, "employer": e, "reason": "over_capacity_or_outranked"})
            st.rejected[w].append(e)
        st.held[e] = keep

    st.trace.append({
        "round": st.round,
        "proposals": [{"worker": w, "employer": e} for w, e in proposals],
        "rejections": rejections,
        "holds": {e: list(ws) for e, ws in st.held.items() if ws},
    })
    st.done = not _free_workers(inst, st)
    return st


@dataclass(frozen=True)
class MatchResult:
    assignment: dict[str, str | None]        # worker -> employer or None
    rounds: int
    trace: list[dict]


def result_from_state(inst: Instance, st: MatchState) -> MatchResult:
    assignment: dict[str, str | None] = {w: None for w in inst.workers}
    for e, ws in st.held.items():
        for w in ws:
            assignment[w] = e
    return MatchResult(assignment, st.round, st.trace)


def deferred_acceptance(inst: Instance) -> MatchResult:
    st = init_state(inst)
    # Each worker proposes at most once per list entry, so total rounds are bounded.
    bound = sum(len(v) for v in inst.worker_prefs.values()) + 1
    while not st.done:
        step(inst, st)
        if st.round > bound:  # defensive: provably unreachable
            raise RuntimeError("deferred acceptance exceeded its termination bound")
    return result_from_state(inst, st)


# --------------------------------------------------------------------------- #
# Auditor: exhaustive enumeration of all worker x employer pairs.
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class BlockingPair:
    worker: str
    employer: str
    worker_current: str | None
    employer_displaced: str | None  # worker the employer would drop, or None if a seat is free


@dataclass(frozen=True)
class AuditReport:
    pairs_examined: int
    blocking_pairs: list[BlockingPair]
    capacity_violations: list[str]
    unacceptable_assignments: list[tuple[str, str]]   # matched pairs not mutually acceptable
    unmatched_workers: list[str]
    unfilled_seats: dict[str, int]

    @property
    def is_stable(self) -> bool:
        return not (self.blocking_pairs or self.capacity_violations or self.unacceptable_assignments)


def audit(inst: Instance, assignment: dict[str, str | None]) -> AuditReport:
    by_emp: dict[str, list[str]] = {e: [] for e in inst.employers}
    unacceptable: list[tuple[str, str]] = []
    for w, e in assignment.items():
        if e is None:
            continue
        by_emp[e].append(w)
        if not inst.mutually_acceptable(w, e):
            unacceptable.append((w, e))
    cap_viol = [e for e, ws in by_emp.items() if len(ws) > inst.capacity[e]]

    blocking: list[BlockingPair] = []
    examined = 0
    for w in inst.workers:
        cur = assignment.get(w)
        cur_rank = inst.worker_rank(w, cur) if cur is not None else None
        for e in inst.employers:
            examined += 1
            if e == cur or not inst.mutually_acceptable(w, e):
                continue
            w_rank = inst.worker_rank(w, e)
            if cur is not None and cur_rank is not None and w_rank >= cur_rank:
                continue  # worker does not prefer e
            # Worker prefers e (or is unmatched / sits in an unacceptable match).
            assigned = by_emp[e]
            if len(assigned) < inst.capacity[e]:
                blocking.append(BlockingPair(w, e, cur, None))
                continue
            worst = max(assigned, key=lambda x: inst.employer_rank(e, x) if inst.employer_rank(e, x) is not None else 10**9)
            worst_rank = inst.employer_rank(e, worst)
            if worst_rank is None or inst.employer_rank(e, w) < worst_rank:
                blocking.append(BlockingPair(w, e, cur, worst))

    return AuditReport(
        pairs_examined=examined,
        blocking_pairs=blocking,
        capacity_violations=cap_viol,
        unacceptable_assignments=unacceptable,
        unmatched_workers=[w for w in inst.workers if assignment.get(w) is None],
        unfilled_seats={e: inst.capacity[e] - len(by_emp[e]) for e in inst.employers if len(by_emp[e]) < inst.capacity[e]},
    )


# --------------------------------------------------------------------------- #
# Conventional one-sided baseline: each worker is served by their own keyword
# ranking; employers play no part in choosing (first come, first served).
# --------------------------------------------------------------------------- #
def keyword_baseline(
    worker_keyword_rank: dict[str, list[str]],
    capacity: dict[str, int],
    arrival_order: list[str],
) -> dict[str, str | None]:
    """Workers arrive in `arrival_order`; each takes their highest keyword-ranked
    listing that still has a free seat. Employer preferences are never consulted.
    This ranking is NOT filtered by feasibility: it models search-and-rank.
    """
    left = dict(capacity)
    out: dict[str, str | None] = {w: None for w in worker_keyword_rank}
    for w in arrival_order:
        for e in worker_keyword_rank.get(w, []):
            if left.get(e, 0) > 0:
                left[e] -= 1
                out[w] = e
                break
    return out


# --------------------------------------------------------------------------- #
# Strategyproofness probe (worker-proposing DA; Dubins & Freedman 1981).
# Holds for the algorithm given fixed, strict inputs. Says nothing about the
# LLM pipeline that produces those inputs, nor about employer-side misreports.
# --------------------------------------------------------------------------- #
def candidate_misreports(true_list: list[str], all_employers: list[str], rng: random.Random,
                         max_samples: int = 200) -> list[list[str]]:
    """Reports to try: every ordering/subset of the true list when small, plus
    reports that add employers the worker does not actually list."""
    pool = list(dict.fromkeys(true_list + all_employers))
    cands: list[list[str]] = []
    if len(true_list) <= 4:
        for r in range(0, len(true_list) + 1):
            cands.extend(list(p) for p in itertools.permutations(true_list, r))
    for _ in range(max_samples):
        k = rng.randint(0, len(pool))
        cands.append(rng.sample(pool, k))
    seen, uniq = set(), []
    for c in cands:
        t = tuple(c)
        if t not in seen and t != tuple(true_list):
            seen.add(t)
            uniq.append(c)
    return uniq


def probe_strategyproofness(inst: Instance, worker: str, seed: int = 0) -> dict:
    """Try misreports for `worker`; return how many give a strictly better outcome
    under the worker's TRUE preferences."""
    rng = random.Random(seed)
    truthful = deferred_acceptance(inst).assignment[worker]

    def utility(e: str | None) -> float:
        if e is None:
            return float("inf")  # worse than any acceptable listing
        r = inst.worker_rank(worker, e)
        return float("inf") if r is None else r  # outside true list = unacceptable = worst

    base = utility(truthful)
    tried = improvements = 0
    examples: list[dict] = []
    for report in candidate_misreports(inst.worker_prefs[worker], inst.employers, rng):
        prefs = dict(inst.worker_prefs)
        prefs[worker] = report
        res = deferred_acceptance(Instance(prefs, inst.employer_prefs, inst.capacity)).assignment[worker]
        tried += 1
        if utility(res) < base:
            improvements += 1
            if len(examples) < 3:
                examples.append({"report": report, "outcome": res})
    return {"worker": worker, "truthful_outcome": truthful, "misreports_tried": tried,
            "improvements": improvements, "examples": examples}
