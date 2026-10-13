"""Stable two-sided matching (Gale-Shapley deferred acceptance) and its audit.

An extension of the job-search app: not wired into the web UI yet. `core` is pure Python (no LLM);
the other modules build preference lists with agents, run the LangGraph matching loop and compare
against a keyword-ranking baseline.
"""
from .core import (AuditReport, BlockingPair, Instance, MatchResult, MatchState, audit, deferred_acceptance,
                   init_state, keyword_baseline, probe_strategyproofness, result_from_state, step)

__all__ = ["AuditReport", "BlockingPair", "Instance", "MatchResult", "MatchState", "audit", "deferred_acceptance",
           "init_state", "keyword_baseline", "probe_strategyproofness", "result_from_state", "step"]
