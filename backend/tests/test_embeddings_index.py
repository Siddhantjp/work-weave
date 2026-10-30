"""Hosted embeddings (mocked HTTP) and the numpy vector index. No network, no API key, no model download."""
import math
import zlib

import httpx
import numpy as np
import pytest

from app import config, db
from app.search import embeddings, index


# ---------------------------------------------------------------- Gemini client ----
class FakeHttp:
    """Stands in for httpx.post: records requests, replays a queue of status codes, answers with simple vectors."""
    calls: list[dict] = []
    statuses: list[int] = []

    @classmethod
    def post(cls, url, json=None, headers=None, timeout=None):
        cls.calls.append({"url": url, "json": json, "headers": headers})
        status = cls.statuses.pop(0) if cls.statuses else 200
        if status != 200:
            return httpx.Response(status, json={"error": {"message": "nope"}}, request=httpx.Request("POST", url))
        vecs = [{"values": [3.0, 4.0] + [0.0] * (embeddings.DIM - 2)} for _ in json["requests"]]
        return httpx.Response(200, json={"embeddings": vecs}, request=httpx.Request("POST", url))


@pytest.fixture
def gemini(monkeypatch):
    FakeHttp.calls, FakeHttp.statuses = [], []
    monkeypatch.setattr(embeddings.httpx, "post", FakeHttp.post)
    monkeypatch.setattr(embeddings.time, "sleep", lambda s: None)
    monkeypatch.setattr(config, "GEMINI_API_KEY", "test-key")
    embeddings._query_vector.cache_clear()
    embeddings._sent.clear()


def test_documents_are_batched_normalised_and_sent_with_the_right_task(gemini):
    out = embeddings.GeminiEmbeddings().embed_documents([f"t{i}" for i in range(60)])
    assert len(out) == 60 and [len(c["json"]["requests"]) for c in FakeHttp.calls] == [25, 25, 10]
    assert math.isclose(sum(x * x for x in out[0]), 1.0) and out[0][:2] == pytest.approx([0.6, 0.8])      # (3,4) -> unit length
    req = FakeHttp.calls[0]
    assert req["headers"]["x-goog-api-key"] == "test-key" and "gemini-embedding-001" in req["url"]
    assert req["json"]["requests"][0]["taskType"] == "RETRIEVAL_DOCUMENT" and req["json"]["requests"][0]["outputDimensionality"] == 768


def test_the_same_query_is_embedded_only_once(gemini):
    e = embeddings.GeminiEmbeddings()
    assert e.embed_query("delivery job") == e.embed_query("delivery job")
    assert len(FakeHttp.calls) == 1 and FakeHttp.calls[0]["json"]["requests"][0]["taskType"] == "RETRIEVAL_QUERY"


def test_rate_limit_is_retried_then_succeeds(gemini):
    FakeHttp.statuses = [429, 503]
    assert embeddings.GeminiEmbeddings().embed_documents(["a"]) and len(FakeHttp.calls) == 3


def test_persistent_rate_limit_gives_a_friendly_error(gemini):
    FakeHttp.statuses = [429] * 10
    with pytest.raises(embeddings.EmbeddingError, match="busy"):
        embeddings.GeminiEmbeddings().embed_documents(["a"])
    assert len(FakeHttp.calls) == embeddings.RETRIES


def test_bad_key_is_not_retried_and_missing_key_is_explained(gemini, monkeypatch):
    FakeHttp.statuses = [403]
    with pytest.raises(embeddings.EmbeddingError, match="GEMINI_API_KEY"):
        embeddings.GeminiEmbeddings().embed_documents(["a"])
    assert len(FakeHttp.calls) == 1
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    with pytest.raises(embeddings.EmbeddingError, match="not set"):
        embeddings.GeminiEmbeddings().embed_documents(["a"])


# --------------------------------------------------------------------- the index ----
class BagOfWords:
    """Deterministic fake embedder: hashed bag of words, unit length. Similar words -> similar vectors."""
    calls = 0

    def vec(self, text):
        v = np.zeros(embeddings.DIM)
        for w in text.lower().replace(".", " ").split():
            v[zlib.crc32(w.encode()) % embeddings.DIM] += 1
        return (v / (np.linalg.norm(v) or 1)).tolist()

    def embed_documents(self, texts):
        BagOfWords.calls += len(texts)
        return [self.vec(t) for t in texts]

    def embed_query(self, text):
        return self.vec(text)


@pytest.fixture
def fake_index(temp_db, monkeypatch):
    BagOfWords.calls = 0
    monkeypatch.setattr(index, "embedder", BagOfWords())


def add(url, trade, title, employer, locality="Indiranagar", description=None):
    with db.connect() as con:
        db.upsert_card(con, {"url": url, "source": "apna", "source_id": url, "trade": trade, "title": title, "employer": employer,
                             "locality": locality, "salary_text": "₹15,000 a month", "salary_min": 15000, "salary_max": 15000, "tags": []})
        if description:
            con.execute("UPDATE listings SET description=? WHERE url=?", (description, url))


def test_only_the_requested_trades_are_embedded_and_unchanged_ones_are_not_redone(fake_index):
    add("u1", "delivery", "Delivery Executive", "Swiggy")
    add("u2", "delivery", "Food Delivery Partner", "Zomato")
    add("u3", "cook", "Cook", "Hotel Aroma")
    assert index.index_listings(["delivery"]) == 2 and BagOfWords.calls == 2           # the cook listing was not touched
    assert index.index_listings(["delivery"]) == 0 and BagOfWords.calls == 2           # nothing changed: no API calls
    add("u2", "delivery", "Food Delivery Partner", "Zomato", description="Bike required, day shift")
    assert index.index_listings(["delivery"]) == 1                                      # text changed: re-embedded
    assert index.index_listings() == 1                                                  # all trades: only the cook is new


def test_search_filters_by_trade_and_ranks_by_meaning(fake_index):
    add("u1", "delivery", "Delivery Executive", "Swiggy")
    add("u2", "security guard", "Security Guard", "Prestige")
    add("u3", "delivery", "Courier Rider", "Shadowfax")
    index.index_listings()
    docs = index.search("delivery executive swiggy", ["delivery"], k=5)
    assert [d.metadata["url"] for d in docs] == ["u1", "u3"]                              # guard excluded, best match first
    assert {d.metadata["url"] for d in index.search("anything", ["delivery", "security guard"], k=5)} == {"u1", "u2", "u3"}
    assert index.search("anything", ["plumber"], k=5) == []


def test_search_with_nothing_indexed_returns_empty(fake_index):
    assert index.search("delivery", ["delivery"]) == []


def test_mmr_prefers_variety_over_a_near_duplicate():
    vectors = np.array([[1.0, 0.0], [0.999, 0.045], [0.0, 1.0]])
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    relevance = np.array([0.95, 0.94, 0.70])
    assert index.mmr(vectors, relevance, k=2, lambda_mult=1.0) == [0, 1]                   # pure relevance takes the repost
    assert index.mmr(vectors, relevance, k=2, lambda_mult=0.5) == [0, 2]                   # diversity skips it
    assert index.mmr(vectors, relevance, k=10, lambda_mult=0.5) == [0, 2, 1]               # never returns more than exist


def test_waits_as_long_as_google_asks_but_gives_up_past_the_budget(gemini, monkeypatch):
    sleeps = []
    monkeypatch.setattr(embeddings.time, "sleep", sleeps.append)
    real = FakeHttp.post

    def limited(url, json=None, headers=None, timeout=None):
        FakeHttp.calls.append({"url": url})
        body = {"error": {"message": "quota", "details": [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "40s"}]}}
        return httpx.Response(429, json=body, request=httpx.Request("POST", url))
    monkeypatch.setattr(embeddings.httpx, "post", limited)
    with pytest.raises(embeddings.EmbeddingError, match="busy"):
        embeddings.GeminiEmbeddings().embed_documents(["a"])
    assert sleeps == [41.0, 41.0]                      # honours Google's 40 s, then stops: a third wait would pass the 90 s budget
    monkeypatch.setattr(embeddings.httpx, "post", real)


def test_retry_delay_is_read_from_the_header_or_the_error_body():
    req = httpx.Request("POST", "http://x")
    assert embeddings._retry_delay(httpx.Response(429, headers={"retry-after": "12"}, json={}, request=req)) == 12.0
    body = {"error": {"details": [{"retryDelay": "28.5s"}]}}
    assert embeddings._retry_delay(httpx.Response(429, json=body, request=req)) == 28.5
    assert embeddings._retry_delay(httpx.Response(429, text="not json", request=req)) == 0.0


def test_embedding_is_paced_so_a_burst_never_exceeds_the_per_minute_limit(gemini, monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(embeddings.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(embeddings.time, "sleep", lambda s: clock.__setitem__(0, clock[0] + s))
    sent_at = []
    real = FakeHttp.post

    def stamped(url, json=None, headers=None, timeout=None):
        sent_at.append((clock[0], len(json["requests"])))
        return real(url, json=json, headers=headers, timeout=timeout)
    monkeypatch.setattr(embeddings.httpx, "post", stamped)
    embeddings.GeminiEmbeddings().embed_documents([f"t{i}" for i in range(200)])      # 8 batches of 25
    assert sum(n for _, n in sent_at) == 200
    for t, _ in sent_at:                                                                # in every rolling minute, at most 80 texts
        assert sum(n for u, n in sent_at if t - 60 < u <= t) <= embeddings.ITEMS_PER_MINUTE
    assert sent_at[-1][0] - sent_at[0][0] >= 120                                        # it really did spread out
    monkeypatch.setattr(embeddings.httpx, "post", real)


def test_one_search_embeds_at_most_a_minutes_worth_and_the_next_search_finishes_the_job(fake_index, monkeypatch):
    monkeypatch.setattr(index, "MAX_NEW_PER_SEARCH", 30)
    for i in range(50):
        add(f"u{i}", "driver", f"Driver {i}", f"Company {i}")
    assert index.index_listings(["driver"]) == 30
    assert index.index_listings(["driver"]) == 20
    assert index.index_listings(["driver"]) == 0
