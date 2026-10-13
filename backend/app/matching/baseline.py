"""Conventional keyword-relevance baseline: TF-IDF overlap between the worker's own words and
listing text. One-sided by construction: it never consults employer preferences and does not
know the worker's hard constraints (a plain search box does not either)."""
from __future__ import annotations

import math
import random
import re
from collections import Counter

from .core import keyword_baseline

STOP = set("i a an the and or of to in at for with my me is am are have has do can not cannot work working live from on as by it be".split())


def tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOP and len(t) > 1]


def keyword_rankings(queries: dict[str, str], docs: dict[str, str]) -> dict[str, list[str]]:
    """worker id -> listing ids by descending TF-IDF score (score>0 only; ties by id)."""
    dtoks = {d: Counter(tokens(t)) for d, t in docs.items()}
    n = len(docs)
    df = Counter(tok for c in dtoks.values() for tok in c)
    idf = {tok: math.log((1 + n) / (1 + k)) + 1 for tok, k in df.items()}
    out = {}
    for w, q in queries.items():
        qt = set(tokens(q))
        scored = []
        for d, c in dtoks.items():
            sc = sum((1 + math.log(c[t])) * idf[t] for t in qt if c.get(t))
            if sc > 0:
                scored.append((-sc, d))
        out[w] = [d for _, d in sorted(scored)]
    return out


def run_baseline(rankings: dict[str, list[str]], capacity: dict[str, int], seed: int) -> dict[str, str | None]:
    order = sorted(rankings)
    random.Random(seed).shuffle(order)           # arrival order is arbitrary; we vary it across seeds
    return keyword_baseline(rankings, capacity, order)
