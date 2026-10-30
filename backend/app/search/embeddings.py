"""Hosted text embeddings (Google Gemini): one small HTTPS call instead of a local model.

The previous local ONNX model + ChromaDB needed more than the 512 MB a free host has. Vectors are 768 numbers,
L2-normalised, so cosine similarity is a plain dot product.
"""
from __future__ import annotations

import math
import re
import time
from functools import lru_cache

import httpx
from langchain_core.embeddings import Embeddings

from .. import config

URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:batchEmbedContents"
DIM = 768
BATCH = 25                 # texts per request: keeps each call well inside the free tier's tokens-per-minute limit
RETRIES = 4
MAX_WAIT_S = 90            # total time we are willing to wait out a rate limit before telling the user


class EmbeddingError(RuntimeError):
    """Raised with a message that is safe to show the user."""


def _unit(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def _explain(r: httpx.Response) -> str:
    try:
        detail = r.json()["error"]["message"]
    except Exception:
        detail = r.text[:200]
    if r.status_code == 429:
        return "The search service is busy right now (free-tier limit). Please wait a minute and try again."
    if r.status_code in (400, 401, 403):
        return f"The embedding service rejected the request (check GEMINI_API_KEY). Google said: {detail}"
    return f"The embedding service failed ({r.status_code}): {detail}"


def _retry_delay(r: httpx.Response) -> float:
    """How long Google says to wait (Retry-After header, or the RetryInfo detail in the error body); 0 if it does not say."""
    try:
        if r.headers.get("retry-after"):
            return float(r.headers["retry-after"])
        for d in r.json()["error"].get("details", []):
            m = re.fullmatch(r"(\d+(?:\.\d+)?)s", str(d.get("retryDelay", "")))
            if m:
                return float(m.group(1))
    except Exception:
        pass
    return 0.0


def _post(body: dict) -> dict:
    last, waited = "no response", 0.0
    for attempt in range(RETRIES):
        hint = 0.0
        try:
            r = httpx.post(URL.format(model=config.GEMINI_EMBED_MODEL), json=body, timeout=30,
                           headers={"x-goog-api-key": config.GEMINI_API_KEY})
        except httpx.HTTPError as e:
            last = f"could not reach the embedding service ({type(e).__name__})"
        else:
            if r.status_code == 200:
                return r.json()
            if r.status_code not in (429, 500, 502, 503, 504):
                raise EmbeddingError(_explain(r))
            last, hint = _explain(r), _retry_delay(r)
        if attempt < RETRIES - 1:
            wait = max(min(2 ** (attempt + 1), 15), hint) + 1      # a per-minute limit needs the full wait
            if waited + wait > MAX_WAIT_S:
                break
            time.sleep(wait); waited += wait
    raise EmbeddingError(last[0].upper() + last[1:])


def _embed(texts: list[str], task: str) -> list[list[float]]:
    if not config.GEMINI_API_KEY:
        raise EmbeddingError("Search is not configured: GEMINI_API_KEY is not set (see .env.example).")
    out: list[list[float]] = []
    for i in range(0, len(texts), BATCH):
        chunk = texts[i:i + BATCH]
        data = _post({"requests": [{"model": f"models/{config.GEMINI_EMBED_MODEL}", "content": {"parts": [{"text": t}]},
                                    "taskType": task, "outputDimensionality": DIM} for t in chunk]})
        vecs = [e["values"] for e in data.get("embeddings", [])]
        if len(vecs) != len(chunk):
            raise EmbeddingError("The embedding service returned an incomplete answer. Please try again.")
        out += [_unit(v) for v in vecs]
    return out


@lru_cache(maxsize=512)
def _query_vector(text: str, model: str) -> tuple[float, ...]:
    return tuple(_embed([text], "RETRIEVAL_QUERY")[0])


class GeminiEmbeddings(Embeddings):
    """LangChain Embeddings interface. Documents and queries use different task types, which Gemini tunes for."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return _embed(texts, "RETRIEVAL_DOCUMENT") if texts else []

    def embed_query(self, text: str) -> list[float]:
        return list(_query_vector(text, config.GEMINI_EMBED_MODEL))      # repeated queries never hit the API twice
