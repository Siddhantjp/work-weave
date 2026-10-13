"""Vector index of scraped listings (Chroma + local ONNX MiniLM embeddings: no API key, no network)."""
from __future__ import annotations

import hashlib
import json

from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
from langchain_chroma import Chroma
from langchain_core.embeddings import Embeddings

from .. import config, db

INDEX_VERSION = "v2"     # bump to force a full re-index when the indexed text/metadata layout changes


class LocalEmbeddings(Embeddings):
    def __init__(self) -> None:
        self._ef = DefaultEmbeddingFunction()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [list(map(float, v)) for v in self._ef(texts)]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


_store: Chroma | None = None


def vector_store() -> Chroma:
    global _store
    if _store is None:
        config.CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        _store = Chroma("listings", LocalEmbeddings(), persist_directory=str(config.CHROMA_DIR),
                        collection_metadata={"hnsw:space": "cosine"})
    return _store


def trade_flag(trade: str) -> str:
    """Metadata key used to filter retrieval by trade, e.g. 'security guard' -> 'trade_security_guard'."""
    return "trade_" + trade.replace(" ", "_")


def listing_text(row) -> str:
    """What gets embedded: card fields, plus the start of the description once it has been fetched."""
    tags = ", ".join(json.loads(row["tags_json"] or "[]"))
    text = (f"{row['title']} at {row['employer']}. Location: {row['locality'] or 'unspecified'}. "
            f"Salary: {row['salary_text'] or 'not stated'}. {tags}.")
    return text + (f" {row['description'][:700]}" if row["description"] else "")


def index_listings(urls: list[str] | None = None) -> int:
    """(Re)index listings whose indexed text is missing or changed. Returns the number upserted."""
    with db.connect() as con:
        rows = con.execute("SELECT * FROM listings" if urls is None else
                           f"SELECT * FROM listings WHERE url IN ({','.join('?' * len(urls))})", urls or []).fetchall()
    if not rows:
        return 0
    vs = vector_store()
    existing = vs.get(ids=[r["url"] for r in rows], include=["metadatas"])
    indexed_hash = {i: m.get("h") for i, m in zip(existing["ids"], existing["metadatas"])}
    todo = []
    for r in rows:
        text = listing_text(r)
        h = hashlib.sha1(f"{text}|{INDEX_VERSION}".encode()).hexdigest()[:12]
        if indexed_hash.get(r["url"]) != h:
            todo.append((r, text, h))
    for i in range(0, len(todo), 64):
        chunk = todo[i:i + 64]
        vs.add_texts(
            [t for _, t, _ in chunk],
            metadatas=[{"url": r["url"], "trades": r["trades"], "h": h, "title": r["title"], "employer": r["employer"] or "",
                        "locality": r["locality"] or "", **{trade_flag(t): True for t in r["trades"].split(",")}}
                       for r, _, h in chunk],
            ids=[r["url"] for r, _, _ in chunk])
    return len(todo)
