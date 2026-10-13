"""Listing -> structured hiring requirements (used by the stable-matching extension's employer side).
The main search graph does this inside its single `augment_and_rank` call instead."""
from __future__ import annotations

import hashlib

from langchain_core.messages import HumanMessage, SystemMessage

from .. import config, db
from ..llm import invoke_structured
from ..models import ListingRequirements

SYSTEM = (
    "You extract hiring requirements from a job listing in Bengaluru. Use ONLY what the text states. "
    "If something is not stated, answer 'unknown' or null. Never guess or infer typical values. "
    "Shift: 'night' only if the text says night shift or hours extending past ~22:00 / before ~06:00; "
    "give shift_start_hour/shift_end_hour (24h) only if explicit hours are written. "
    "min_experience_months: convert years to months; 'freshers' means 0. "
    "vehicle_required: 'yes' only if a bike/two-wheeler/vehicle is required (e.g. 'Bike (compulsory)'). "
    "wage_min/wage_max are monthly INR. evidence: short verbatim quotes. "
    "Reply with a JSON OBJECT of values for these fields, never with the schema itself."
)


def structure_listing(row) -> ListingRequirements:
    text = (f"Title: {row['title']}\nEmployer: {row['employer']}\nLocation: {row['locality']}\n"
            f"Salary tag: {row['salary_text']}\nTags: {row['tags_json']}\nDescription: {row['description'] or '(not fetched)'}")
    h = hashlib.sha1(text.encode()).hexdigest()
    with db.connect() as con:
        c = con.execute("SELECT content_hash, requirements_json FROM listing_requirements WHERE url=?", (row["url"],)).fetchone()
    if c and c["content_hash"] == h:
        return ListingRequirements.model_validate_json(c["requirements_json"])
    req = invoke_structured(ListingRequirements, [SystemMessage(SYSTEM), HumanMessage(text)])
    with db.connect() as con:
        con.execute("INSERT OR REPLACE INTO listing_requirements VALUES (?,?,?,?,?)",
                    (row["url"], h, req.model_dump_json(), config.GROQ_MODEL, db.now()))
    return req
