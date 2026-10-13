from app.models import ListingRequirements, WorkerProfile
from app.search.limits import check_limits


def req(**kw):
    base = dict(shift="unknown", shift_start_hour=None, shift_end_hour=None, min_experience_months=None,
                vehicle_required="unknown", licence_required="unknown", openings=None, wage_min=None,
                wage_max=None, skills_required=[], evidence="")
    return ListingRequirements(**{**base, **kw})


W = WorkerProfile(latest_shift_end_hour=21, avoid_night_shift=True)   # constraint fixture, not a real person


def test_night_shift_is_hard_conflict():
    assert check_limits(W, req(shift="night")).status == "hard_conflict"


def test_explicit_hours_past_limit_or_overnight_conflict():
    assert check_limits(W, req(shift="day", shift_start_hour=14, shift_end_hour=23)).status == "hard_conflict"
    assert check_limits(W, req(shift_start_hour=22, shift_end_hour=6)).status == "hard_conflict"


def test_compatible_hours_feasible_and_unknown_needs_clarification():
    assert check_limits(W, req(shift="day", shift_start_hour=9, shift_end_hour=18)).status == "feasible"
    v = check_limits(W, req())
    assert v.status == "needs_clarification" and v.missing


def test_unconstrained_worker_has_no_shift_conflict():
    assert check_limits(WorkerProfile(), req(shift="night")).status == "feasible"


def test_missing_requirements_never_assumed_feasible():
    assert check_limits(W, None).status == "needs_clarification"
