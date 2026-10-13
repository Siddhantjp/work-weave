"""Groq chat model (via LangChain) + a persistent LLM cache.

* get_llm()     - one shared ChatGroq: low reasoning effort and a token cap keep calls inside the free tier.
* structured()  - JSON-schema structured output (gpt-oss on Groq fails in the default tool-calling mode).
* SQLiteLLMCache- LangChain BaseCache backed by our SQLite file: identical prompts are never paid for twice,
                  across restarts. Cache hits still appear as runs in LangSmith.
"""
from __future__ import annotations

import hashlib
import sqlite3
from contextlib import contextmanager
from functools import lru_cache

import groq
from langchain_core.caches import RETURN_VAL_TYPE, BaseCache
from langchain_core.exceptions import OutputParserException
from langchain_core.globals import set_llm_cache
from langchain_core.load import dumps, loads
from langchain_groq import ChatGroq

from . import config, db

RETRY_ON = (OutputParserException, groq.BadRequestError, groq.RateLimitError)


@contextmanager
def _cache_db():
    """The LLM cache has its own SQLite file: it holds prompts (which contain what users typed), so it stays away from listings."""
    config.CACHE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(config.CACHE_DB_PATH, timeout=60)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE IF NOT EXISTS llm_generations (key TEXT PRIMARY KEY, value_json TEXT NOT NULL, created_at TEXT NOT NULL)")
    try:
        yield con
        con.commit()
    finally:
        con.close()


class SQLiteLLMCache(BaseCache):
    @staticmethod
    def _key(prompt: str, llm_string: str) -> str:
        return hashlib.sha256(f"{llm_string}\x00{prompt}".encode()).hexdigest()

    def lookup(self, prompt: str, llm_string: str) -> RETURN_VAL_TYPE | None:
        with _cache_db() as con:
            row = con.execute("SELECT value_json FROM llm_generations WHERE key=?", (self._key(prompt, llm_string),)).fetchone()
        if not row:
            return None
        try:
            return loads(row["value_json"], allowed_objects="core")
        except Exception:               # unreadable entry: behave as a miss, never break a search
            return None

    def update(self, prompt: str, llm_string: str, return_val: RETURN_VAL_TYPE) -> None:
        with _cache_db() as con:
            con.execute("INSERT OR REPLACE INTO llm_generations VALUES (?,?,?)",
                        (self._key(prompt, llm_string), dumps(list(return_val)), db.now()))

    def clear(self, **kwargs) -> None:
        with _cache_db() as con:
            con.execute("DELETE FROM llm_generations")


set_llm_cache(SQLiteLLMCache())


@lru_cache(maxsize=1)
def get_llm() -> ChatGroq:
    if not config.GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not set (see .env.example)")
    return ChatGroq(model=config.GROQ_MODEL, api_key=config.GROQ_API_KEY, temperature=0, max_retries=1,
                    reasoning_effort="low", max_tokens=3500)


def structured(schema):
    return get_llm().with_structured_output(schema, method="json_schema")


def invoke_structured(schema, messages):
    """One structured call with retries (bad JSON, rate limit). Used outside the main search graph."""
    return structured(schema).with_retry(retry_if_exception_type=RETRY_ON, stop_after_attempt=3,
                                         wait_exponential_jitter=True).invoke(messages)
