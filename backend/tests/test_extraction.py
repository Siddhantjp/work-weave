from app.search.extraction import Evidence, Extraction, verify_extraction

TEXT = "I have 18 months of delivery experience, own a two-wheeler, live in Kammanahalli, and cannot work after 9 PM."


def ext(**kw):
    base = dict(desired_trades=[], skills=[], experience_months=None, home_locality=None, has_vehicle=None,
                vehicle_type=None, owns_tools=None, latest_shift_end_hour=None, avoid_night_shift=False, min_monthly_wage=None, evidence=[])
    return Extraction(**{**base, **kw})


def test_supported_fields_kept_and_invented_fields_dropped():
    x = ext(experience_months=18, home_locality="Kammanahalli", skills=["wiring"],
            evidence=[Evidence(field="experience_months", quote="18 months of delivery experience"),
                      Evidence(field="home_locality", quote="live in Kammanahalli"),
                      Evidence(field="skills", quote="expert wiring")])      # quote NOT in text
    kept, dropped = verify_extraction(x, TEXT)
    assert kept == {"experience_months": 18, "home_locality": "Kammanahalli"}
    assert len(dropped) == 1 and "skills" in dropped[0]


def test_field_without_any_evidence_is_dropped_and_quote_match_is_whitespace_case_insensitive():
    x = ext(has_vehicle=True, latest_shift_end_hour=21,
            evidence=[Evidence(field="latest_shift_end_hour", quote="CANNOT work   after 9 pm")])
    kept, dropped = verify_extraction(x, TEXT)
    assert kept == {"latest_shift_end_hour": 21} and "has_vehicle" in dropped[0]


def test_unknown_trades_filtered():
    x = ext(desired_trades=["delivery", "astronaut"], evidence=[Evidence(field="desired_trades", quote="delivery experience")])
    assert verify_extraction(x, TEXT)[0]["desired_trades"] == ["delivery"]
