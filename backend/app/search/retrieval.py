"""Retrieval layer: a real LangChain retriever + reciprocal-rank fusion.

* ListingRetriever   - BaseRetriever over the listing vectors. Filtered by trade, MMR for diversity
                       (so four reposts of one job do not crowd out other employers).
* rrf_fuse           - Reciprocal Rank Fusion across the multiple rewritten queries (Cormack et al., 2009).
* dedupe_near_dups   - collapses identical reposts (same title + employer + area).

Each retriever call is its own `retriever` run in LangSmith, showing the query and the documents returned.
"""
from __future__ import annotations

from collections import defaultdict

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import Field

from . import index


class ListingRetriever(BaseRetriever):
    trades: list[str] = Field(default_factory=list)
    k: int = 10
    lambda_mult: float = 0.6        # 1.0 = pure relevance, 0.0 = pure diversity

    def _get_relevant_documents(self, query: str, *, run_manager: CallbackManagerForRetrieverRun) -> list[Document]:
        return index.search(query, self.trades, k=self.k, fetch_k=self.k * 4, lambda_mult=self.lambda_mult)


def rrf_fuse(result_lists: list[list[Document]], c: int = 60) -> list[tuple[Document, float]]:
    """Fuse several ranked lists. A document ranked highly by many queries beats one ranked #1 by a single query."""
    score: dict[str, float] = defaultdict(float)
    doc: dict[str, Document] = {}
    for docs in result_lists:
        for rank, d in enumerate(docs):
            u = d.metadata["url"]
            score[u] += 1.0 / (c + rank + 1)
            doc.setdefault(u, d)
    return sorted(((doc[u], round(s, 5)) for u, s in score.items()), key=lambda x: -x[1])


def dedupe_near_dups(fused: list[tuple[Document, float]]) -> tuple[list[tuple[Document, float]], int]:
    seen, out = set(), []
    for d, s in fused:
        m = d.metadata
        key = (str(m.get("title", "")).lower(), str(m.get("employer", "")).lower(), str(m.get("locality", "")).lower())
        if key in seen:
            continue
        seen.add(key)
        out.append((d, s))
    return out, len(fused) - len(out)
