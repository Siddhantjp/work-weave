"""Core data models shared across the app: the worker profile and a listing's hiring requirements."""
from typing import Literal

from pydantic import BaseModel, Field

Tri = Literal["yes", "no", "unknown"]


class WorkerProfile(BaseModel):
    """Structured worker profile. Every field is either stated by the worker or null."""
    simulated: bool = Field(True, description="True for demo/evaluation workers; labelled everywhere")
    description: str = ""
    desired_trades: list[str] = []
    skills: list[str] = []
    experience_months: int | None = None
    home_locality: str | None = None
    has_vehicle: bool | None = None
    vehicle_type: str | None = None
    owns_tools: bool | None = None
    latest_shift_end_hour: int | None = Field(None, description="HARD: 24h clock, cannot work past this hour")
    avoid_night_shift: bool = False
    min_monthly_wage: int | None = None


class ListingRequirements(BaseModel):
    """Requirements extracted from listing text. 'unknown'/null whenever the text does not say so."""
    shift: Literal["day", "night", "rotational", "flexible", "unknown"]
    shift_start_hour: int | None
    shift_end_hour: int | None
    min_experience_months: int | None
    vehicle_required: Tri
    licence_required: Tri
    openings: int | None
    wage_min: int | None
    wage_max: int | None
    skills_required: list[str]
    evidence: str = Field(description="short verbatim quotes from the listing supporting shift/experience/vehicle")
