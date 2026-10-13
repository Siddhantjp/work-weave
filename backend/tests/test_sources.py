"""Parser/failure-path tests. The HTML snippets are minimal markup fixtures for the
PARSER only (tag structure copied from the live page); they are never stored or shown as listings."""
import pytest

from app.sources.apna import ScrapeParseError, _salary, parse_cards, parse_detail
from app.sources.geo import haversine_km


def test_salary_range_and_single_and_missing():
    assert _salary("₹60,000 - ₹85,000") == (60000, 85000)
    assert _salary("₹15,000") == (15000, 15000)
    assert _salary("") == (None, None)


def test_parse_cards_extracts_fields_and_skips_non_job_links():
    html = ('<a data-testid="job-card" href="/job/bengaluru-bangalore/x-123"><p>T</p><p>Emp</p>'
            '<p>Kadugodi, Bengaluru/Bangalore</p><p>₹1,000 - ₹2,000</p><p>Full Time</p></a>'
            '<a data-testid="job-card" href="/other">n</a>')
    (c,) = parse_cards(html, "delivery")
    assert (c["title"], c["employer"], c["locality"], c["salary_min"], c["salary_max"], c["tags"]) == \
        ("T", "Emp", "Kadugodi, Bengaluru/Bangalore", 1000, 2000, ["Full Time"])
    assert c["url"] == "https://apna.co/job/bengaluru-bangalore/x-123" and c["source_id"] == "123"


def test_empty_page_yields_no_cards_and_bad_detail_raises():
    assert parse_cards("<html></html>", "delivery") == []
    with pytest.raises(ScrapeParseError):
        parse_detail("<html></html>")


def test_haversine_known_distance():
    # Bengaluru centre to Electronic City is roughly 17-19 km straight line
    assert 15 < haversine_km((12.9716, 77.5946), (12.8452, 77.6602)) < 20
