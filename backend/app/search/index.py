"""Vector index of scraped listings, kept in the listings SQLite database (table listing_vectors).

Embeddings come from a hosted API (see embeddings.py); search is numpy: cosine similarity (a dot product,
the vectors are unit length) followed by Maximal Marginal Relevance. A few hundred 768-number vectors is
about a megabyte, so no vector database is needed, and nothing heavy is loaded into memory.
"""
from __future__ import annotations

import hashlib
import json

import numpy as np
from langchain_core.documents import Document

from .. import db
from .embeddings import DIM, GeminiEmbeddings

INDEX_VERSION = "v3-gemini"     # bump to force a full re-index when the indexed text or the embedding model changes
embedder = GeminiEmbeddings()


def listing_text(row) -> str:
    """What gets embedded: card fields, plus the start of the description once it has been fetched."""
    tags = ", ".join(json.loads(row["tags_json"] or "[]"))
    text = (f"{row['title']} at {row['employer']}. Location: {row['locality'] or 'unspecified'}. "
            f"Salary: {row['salary_text'] or 'not stated'}. {tags}.")
    return text + (f" {row['description'][:400]}" if row["description"] else "")


def _trade_clause(trades: list[str] | None, column: str = "trades") -> tuple[str, list[str]]:
    if not trades:
        return "1=1", []
    return "(" + " OR ".join(f"(','||{column}||',') LIKE ?" for _ in trades) + ")", [f"%,{t},%" for t in trades]


def index_listings(trades: list[str] | None = None) -> int:
    """Embed listings (of the given trades, or all) whose indexed text is missing or changed. Returns how many were embedded.
    Nothing is held open across the network call."""
    where, args = _trade_clause(trades)
    with db.connect() as con:
        rows = con.execute(f"SELECT * FROM listings WHERE {where}", args).fetchall()
        have = {r["url"]: r["content_hash"] for r in con.execute("SELECT url, content_hash FROM listing_vectors")}
    todo = []
    for r in rows:
        text = listing_text(r)
        h = hashlib.sha1(f"{text}|{INDEX_VERSION}".encode()).hexdigest()[:12]
        if have.get(r["url"]) != h:
            todo.append((r["url"], text, h))
    if not todo:
        return 0
    vectors = embedder.embed_documents([t for _, t, _ in todo])
    with db.connect() as con:
        con.executemany("INSERT OR REPLACE INTO listing_vectors (url, content_hash, vec) VALUES (?,?,?)",
                        [(u, h, np.asarray(v, dtype=np.float32).tobytes()) for (u, _, h), v in zip(todo, vectors)])
    return len(todo)


def mmr(vectors: np.ndarray, relevance: np.ndarray, k: int, lambda_mult: float) -> list[int]:
    """Maximal Marginal Relevance: repeatedly pick the item that is most relevant to the query and least similar
    to what was already picked, so reposts of one job do not crowd out other employers."""
    chosen = [int(np.argmax(relevance))]
    while len(chosen) < min(k, len(relevance)):
        rest = [i for i in range(len(relevance)) if i not in chosen]
        redundancy = (vectors[rest] @ vectors[chosen].T).max(axis=1)
        chosen.append(rest[int(np.argmax(lambda_mult * relevance[rest] - (1 - lambda_mult) * redundancy))])
    return chosen


def search(query: str, trades: list[str], k: int = 10, fetch_k: int = 40, lambda_mult: float = 0.6) -> list[Document]:
    """Top-k listings of the given trades for a query: cosine relevance, re-ranked with MMR."""
    q = np.asarray(embedder.embed_query(query), dtype=np.float32)
    where, args = _trade_clause(trades, "l.trades")
    with db.connect() as con:
        rows = con.execute(f"SELECT l.url, l.trades, l.title, l.employer, l.locality, v.vec FROM listing_vectors v "
                           f"JOIN listings l ON l.url = v.url WHERE {where}", args).fetchall()
    rows = [r for r in rows if len(r["vec"]) == DIM * 4]               # ignore vectors from a different model
    if not rows:
        return []
    matrix = np.vstack([np.frombuffer(r["vec"], dtype=np.float32) for r in rows])
    sims = matrix @ q
    pool = np.argsort(-sims)[:fetch_k]
    picked = [int(pool[i]) for i in mmr(matrix[pool], sims[pool], k, lambda_mult)]
    return [Document(page_content=f"{rows[i]['title']} at {rows[i]['employer']}",
                     metadata={"url": rows[i]["url"], "trades": rows[i]["trades"], "title": rows[i]["title"],
                               "employer": rows[i]["employer"] or "", "locality": rows[i]["locality"] or "",
                               "relevance": round(float(sims[i]), 4)}) for i in picked]
