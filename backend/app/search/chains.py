"""LCEL chains: prompt | structured Groq model | retry. Each has a run_name so it is readable in LangSmith.

All prompts live here, separate from graph logic. The chains are built lazily so importing the app
never requires the API key.
"""
from __future__ import annotations

from functools import lru_cache

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from ..llm import RETRY_ON, structured
from ..sources.apna import TRADE_SLUGS

UNDERSTAND_SYSTEM = (
    "You read a job-seeker's request (Bengaluru, informal work) and (1) extract their profile ONLY from what they wrote, "
    "(2) plan retrieval. The request may be in ANY language or script (English, Hindi, Kannada, Tamil, Telugu, or mixed like Hinglish): "
    "understand it in that language, set `language` to its English name, and write queries and profile values in English "
    "(spell place names in their common English form, e.g. Kammanahalli). "
    "For every non-empty profile field add an evidence item whose quote is copied EXACTLY, character for character, from the ORIGINAL text "
    "in its own script (never translate a quote). "
    "desired_trades must come from " + str(list(TRADE_SLUGS)).replace("{", "(").replace("}", ")") + " (map synonyms in any language: "
    "rider/delivery boy->delivery, maid/housekeeper->domestic worker, wiring->electrician, guard->security guard). Never invent skills, experience, licences or equipment. "
    "'cannot work after 9 PM' => latest_shift_end_hour=21, avoid_night_shift=true. Unknown => null/empty/false. "
    "queries: 3-4 short search queries (role synonyms, constraint phrasings, equipment). Reply with JSON values, never the schema.")

PLAN_SYSTEM = "Plan retrieval of Bengaluru job listings for this worker. Reply with JSON values, never the schema."

AUGMENT_SYSTEM = (
    "You are the augmentation step of a job-search RAG system. For each retrieved listing extract hiring requirements using ONLY "
    "the listing text (unknown/null if not stated; never guess). shift='night' only if the text says night or hours past ~22:00; "
    "give shift hours only if explicit. min_experience_months: years->months, freshers=0. vehicle_required='yes' only if a bike/vehicle is required. "
    "Then order ALL listings from most to least suitable for THIS worker (trade fit, skills, experience, distance, vehicle, pay vs. their minimum). "
    "Missing information is a mild negative. rationale: cite only given facts; for proximity use distance_km, NEVER your own knowledge of "
    "Bengaluru geography; do not refer to other listings. Write every rationale in the language named by LANGUAGE (keep job titles, "
    "employer names and numbers exactly as they appear). Reply with JSON values, never the schema.")


def _chain(system: str, human: str, schema, name: str, tags: list[str]) -> Runnable:
    prompt = ChatPromptTemplate.from_messages([("system", system.replace("{", "{{").replace("}", "}}")), ("human", human)])
    return ((prompt | structured(schema))
            .with_retry(retry_if_exception_type=RETRY_ON, stop_after_attempt=3, wait_exponential_jitter=True)
            .with_config(run_name=name, tags=["groq", "lcel", *tags]))


@lru_cache(maxsize=None)
def understand_chain() -> Runnable:
    from .schemas import Understood
    return _chain(UNDERSTAND_SYSTEM, "{request}", Understood, "understand_request", ["extraction", "planning"])


@lru_cache(maxsize=None)
def plan_chain() -> Runnable:
    from .schemas import Plan
    return _chain(PLAN_SYSTEM, "{profile}", Plan, "plan_retrieval", ["planning"])


@lru_cache(maxsize=None)
def augment_chain() -> Runnable:
    from .schemas import Augmented
    return _chain(AUGMENT_SYSTEM, "LANGUAGE: {language}\nWORKER: {worker}\nREQUEST: {request}\n\nLISTINGS:\n{listings}", Augmented,
                  "augment_and_rank", ["augmentation", "ranking"])
