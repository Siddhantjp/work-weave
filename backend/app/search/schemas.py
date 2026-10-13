"""Pydantic schemas for the agentic RAG graph's LLM outputs."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ..sources.apna import TRADE_SLUGS
from .extraction import Extraction


class Understood(Extraction):
    """One Groq call: the worker's profile (quote-verified in code) plus the retrieval plan."""
    language: str = Field(description="English name of the language the worker wrote in, e.g. English, Hindi, Kannada, Tamil")
    queries: list[str] = Field(description="3-4 search queries IN ENGLISH: role synonyms, constraint phrasings, equipment ownership")
    related_trades: list[str] = Field(description=f"adjacent trades usable if too few results, only from {list(TRADE_SLUGS)}")


class Plan(BaseModel):          # used when a ready-made profile is supplied (simulations)
    queries: list[str]
    related_trades: list[str]


class Judged(BaseModel):
    id: int
    shift: Literal["day", "night", "rotational", "flexible", "unknown"]
    shift_start_hour: int | None
    shift_end_hour: int | None
    min_experience_months: int | None
    vehicle_required: Literal["yes", "no", "unknown"]
    openings: int | None
    wage_min: int | None
    wage_max: int | None
    rationale: str = Field(description="1-2 sentences: why this suits THIS worker, only facts given")


class Augmented(BaseModel):
    items: list[Judged] = Field(description="every listing exactly once, MOST preferred first")
