"""Elicitor + Clarifier as a LangGraph with human-in-the-loop interrupts.

  elicit (ReWOO-style structured extraction, evidence-checked)
    -> clarify (Reflection: critiques the draft, asks targeted questions)
    -> [interrupt: worker answers] -> elicit ...        (bounded rounds)
    -> [interrupt: worker reviews / edits / confirms] -> END

Anti-invention guard: the Elicitor must quote the worker's own words for every field it
fills. Quotes are verified by string matching in code; a field without a verifiable quote
is discarded (and reported). Fields edited by the worker at the confirm step are trusted.
"""
from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from pydantic import BaseModel, Field

from ..llm import invoke_structured
from ..models import WorkerProfile
from ..search.extraction import FIELDS, Extraction, normalize, verify_extraction  # noqa: F401

MAX_CLARIFY_ROUNDS = 2
class Clarification(BaseModel):
    questions: list[str] = Field(description="at most 3 short, specific questions; empty if the profile is sufficient")


class State(TypedDict, total=False):
    description: str
    answers: Annotated[list[dict], operator.add]     # {question, answer}
    draft: WorkerProfile
    questions: list[str]
    rounds: int
    asked: Annotated[list[str], operator.add]       # every question ever posed (answered or not)
    discarded: list[str]
    confirmed: WorkerProfile | None
    status: str                                      # awaiting_answers | awaiting_confirmation | confirmed | rejected
    events: Annotated[list[dict], operator.add]


def worker_text(s: State) -> str:
    return "\n".join([s["description"]] + [f"Q: {a['question']}\nA: {a['answer']}" for a in s.get("answers", [])])


def elicit_node(s: State) -> dict:
    text = worker_text(s)
    x = invoke_structured(Extraction, [
        SystemMessage(
            "You are the Elicitor. Extract a job-seeker profile from their own words (Bengaluru, informal work). "
            "Fill a field ONLY if the text states it. For every non-empty field add an evidence item whose quote is copied "
            "EXACTLY from the text. Never invent skills, experience, licences or equipment. 'cannot work after 9 PM' => "
            "latest_shift_end_hour=21 and avoid_night_shift=true. Convert years to months. Unknown => null/empty/false. "
            "Reply with JSON values, never the schema."),
        HumanMessage(text)])
    kept, dropped = verify_extraction(x, text)
    draft = WorkerProfile(simulated=s.get("draft").simulated if s.get("draft") else True, description=s["description"], **kept)
    ev = [{"node": "elicit", "message": f"extracted {sorted(kept)}" + (f"; DISCARDED unsupported: {dropped}" if dropped else "")}]
    return {"draft": draft, "discarded": dropped, "events": ev}


def clarify_node(s: State) -> dict:
    d = s["draft"]
    forced = []
    if not d.desired_trades:
        forced.append("What kind of work are you looking for (for example delivery, driver, electrician, security guard, housekeeping, cook, plumber)?")
    if not d.home_locality:
        forced.append("Which area of Bengaluru do you live in?")
    llm_q: list[str] = []
    if s.get("rounds", 0) < MAX_CLARIFY_ROUNDS:
        c = invoke_structured(Clarification, [
            SystemMessage(
                "You are the Clarifier (critic). Given a worker's words and the draft profile, challenge gaps and ambiguity that "
                "affect job matching: working-hour limits, vehicle/licence/tool ownership, experience, type of work (e.g. does 'wiring' mean "
                "house or industrial?). Do NOT ask about anything already stated or already asked. The system separately asks about "
                "missing work type and home area, so never ask those. Ask at most 3 short questions, or none if sufficient. "
                "Reply with JSON values, never the schema."),
            HumanMessage(f"WORKER WORDS:\n{worker_text(s)}\n\nALREADY ASKED: {s.get('asked', [])}\n\nDRAFT PROFILE:\n{d.model_dump_json(exclude={'simulated', 'description'})}")])
        llm_q = c.questions
    asked = set(s.get("asked", []))
    qs = [q for q in (forced + llm_q) if q not in asked][:3]
    return {"questions": qs, "asked": qs, "events": [{"node": "clarify", "message": f"{len(qs)} question(s): {qs}" if qs else "profile sufficient; no questions"}]}


def route_after_clarify(s: State) -> str:
    return "ask" if s["questions"] else "confirm"


def ask_node(s: State) -> dict:
    """Human-in-the-loop: pause until the worker answers (resume value: list of answer strings)."""
    reply = interrupt({"type": "questions", "questions": s["questions"], "draft": s["draft"].model_dump()})
    pairs = [{"question": q, "answer": a} for q, a in zip(s["questions"], reply) if a and a.strip()]
    return {"answers": pairs, "rounds": s.get("rounds", 0) + 1, "status": "awaiting_answers",
            "events": [{"node": "ask", "message": f"worker answered {len(pairs)}/{len(s['questions'])}"}]}


def confirm_node(s: State) -> dict:
    """Mandatory confirmation: nothing downstream runs without it."""
    reply = interrupt({"type": "confirm", "draft": s["draft"].model_dump(), "discarded": s.get("discarded", [])})
    if reply.get("action") != "confirm":
        return {"confirmed": None, "status": "rejected", "events": [{"node": "confirm", "message": "worker rejected the profile"}]}
    final = WorkerProfile.model_validate({**s["draft"].model_dump(), **reply.get("profile", {})})
    return {"confirmed": final, "status": "confirmed",
            "events": [{"node": "confirm", "message": "worker confirmed profile" + (" with edits" if reply.get("profile") else "")}]}


def build_graph(checkpointer=None):
    g = StateGraph(State)
    g.add_node("elicit", elicit_node)
    g.add_node("clarify", clarify_node)
    g.add_node("ask", ask_node)
    g.add_node("confirm", confirm_node)
    g.add_edge(START, "elicit")
    g.add_edge("elicit", "clarify")
    g.add_conditional_edges("clarify", route_after_clarify, {"ask": "ask", "confirm": "confirm"})
    g.add_edge("ask", "elicit")          # cycle: answers feed back into extraction
    g.add_edge("confirm", END)
    saver = MemorySaver(serde=JsonPlusSerializer(allowed_msgpack_modules=[("app.schemas", "WorkerProfile")]))
    return g.compile(checkpointer=checkpointer or saver)


# --- thin session API used by the web layer and scripts ---------------------- #
def start(graph, thread_id: str, description: str, simulated: bool = True) -> dict:
    cfg = {"configurable": {"thread_id": thread_id}}
    seed = WorkerProfile(simulated=simulated, description=description)
    graph.invoke({"description": description, "draft": seed, "answers": [], "asked": [], "rounds": 0, "events": []}, cfg)
    return snapshot(graph, thread_id)


def resume(graph, thread_id: str, value) -> dict:
    cfg = {"configurable": {"thread_id": thread_id}}
    graph.invoke(Command(resume=value), cfg)
    return snapshot(graph, thread_id)


def snapshot(graph, thread_id: str) -> dict:
    st = graph.get_state({"configurable": {"thread_id": thread_id}})
    pending = st.tasks[0].interrupts[0].value if st.tasks and st.tasks[0].interrupts else None
    v = st.values
    return {"pending": pending, "confirmed": v.get("confirmed"), "status": v.get("status", "started"),
            "draft": v.get("draft"), "events": v.get("events", [])}
