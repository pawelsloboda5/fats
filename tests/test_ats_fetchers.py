"""Unit tests for scripts/ats_fetchers.py."""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

from scripts.ats_fetchers import (
    parse_greenhouse, parse_lever, parse_ashby,
    parse_workable, parse_smartrecruiters,
    build_feed_url, _strip_html, _detect_remote, _parse_location,
    _parse_salary_from_text, _compute_hours_since, PARSERS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def test_strip_html_removes_tags_preserves_text():
    out = _strip_html("<p>Hello <b>world</b></p>")
    assert "Hello" in out and "world" in out
    assert "<" not in out and ">" not in out


def test_strip_html_handles_entities():
    out = _strip_html("Caf&eacute; &amp; bar")
    assert "Café" in out
    assert "&" in out


def test_strip_html_drops_scripts():
    out = _strip_html("<p>Visible</p><script>evil()</script>")
    assert "Visible" in out
    assert "evil()" not in out


def test_detect_remote_us():
    is_remote, region = _detect_remote("Remote - United States")
    assert is_remote is True
    assert region == "Remote - US"


def test_detect_remote_global():
    is_remote, region = _detect_remote("Remote - Worldwide")
    assert is_remote is True
    assert "Global" in region


def test_detect_remote_eu():
    is_remote, region = _detect_remote("Remote - Europe")
    assert is_remote is True
    assert region == "Remote - EU"


def test_detect_remote_negative():
    is_remote, region = _detect_remote("Washington, DC")
    assert is_remote is False
    assert region is None


def test_parse_location_basic():
    loc = _parse_location("Washington, DC, USA")
    assert loc["city"] == "Washington"
    assert loc["state"] == "DC"
    assert loc["country"] == "USA"
    assert loc["is_remote"] is False


def test_parse_location_remote_with_country():
    loc = _parse_location("Remote - United States")
    assert loc["is_remote"] is True
    assert loc["remote_region"] == "Remote - US"


def test_parse_salary_from_text_dollar_range():
    out = _parse_salary_from_text("Salary: $150,000 - $180,000 per year")
    assert out is not None
    assert out["min"] == 150000
    assert out["max"] == 180000


def test_parse_salary_from_text_short_form():
    out = _parse_salary_from_text("Range $120000 to $160000")
    assert out is not None
    assert out["min"] == 120000
    assert out["max"] == 160000


def test_parse_salary_from_text_rejects_bogus():
    """Phone numbers and short numbers should not be misread as salary."""
    out = _parse_salary_from_text("Call us at 555-1234 or 800-555-9999")
    assert out is None


def test_parse_salary_from_text_no_match():
    assert _parse_salary_from_text("No salary mentioned here.") is None


def test_compute_hours_since_recent():
    """A timestamp from 5 hours ago should yield ~5."""
    five_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
    hrs = _compute_hours_since(five_hours_ago)
    assert hrs is not None and 4 <= hrs <= 6


def test_compute_hours_since_handles_z_suffix():
    """ISO with Z suffix (UTC) should parse cleanly."""
    hrs = _compute_hours_since("2026-04-19T20:00:00Z",
                                now=datetime(2026, 4, 20, 12, 0, tzinfo=timezone.utc))
    assert hrs == 16


def test_compute_hours_since_returns_none_for_garbage():
    assert _compute_hours_since("not-a-date") is None
    assert _compute_hours_since(None) is None


# ---------------------------------------------------------------------------
# Greenhouse parser
# ---------------------------------------------------------------------------

def test_parse_greenhouse_extracts_basic_fields():
    feed = {"jobs": [{
        "id": 12345, "title": "Senior Software Engineer",
        "location": {"name": "Remote - US"},
        "absolute_url": "https://boards.greenhouse.io/acme/jobs/12345",
        "updated_at": "2026-04-19T20:00:00-04:00",
        "content": "<p>5+ years experience required.</p>",
    }]}
    out = parse_greenhouse(feed, "acme",
                           {"name": "Acme", "size": "200-1000", "industry": "b2b_saas"})
    assert len(out) == 1
    job = out[0]
    assert job["title"] == "Senior Software Engineer"
    assert job["company"] == "Acme"
    assert job["company_size"] == "200-1000"
    assert job["source_board"] == "greenhouse"
    assert job["job_id"] == "12345"
    assert "5+ years" in job["jd_text"]
    assert job["location_normalized"]["is_remote"] is True


def test_parse_greenhouse_handles_empty():
    assert parse_greenhouse({"jobs": []}, "acme") == []
    assert parse_greenhouse({}, "acme") == []


def test_parse_greenhouse_extracts_salary_from_jd():
    feed = {"jobs": [{
        "id": 1, "title": "Eng", "location": {"name": "DC"},
        "absolute_url": "https://x", "updated_at": "2026-04-20T00:00:00Z",
        "content": "<p>Salary: $130,000 - $170,000</p>"
    }]}
    out = parse_greenhouse(feed, "acme")
    assert out[0]["salary_listed"] is not None
    assert out[0]["salary_listed"]["min"] == 130000


# ---------------------------------------------------------------------------
# Lever parser
# ---------------------------------------------------------------------------

def test_parse_lever_extracts_basic_fields():
    feed = [{
        "id": "abc", "text": "Designer",
        "categories": {"location": "Brooklyn, NY", "team": "Design",
                        "commitment": "Full-time"},
        "hostedUrl": "https://jobs.lever.co/acme/abc",
        "createdAt": 1745126400000,
        "descriptionPlain": "Design role for a mid-level designer.",
        "lists": [{"text": "Requirements", "content": "<li>3+ yrs</li>"}],
    }]
    out = parse_lever(feed, "acme",
                       {"name": "Acme", "size": "50-200", "industry": "b2b_saas"})
    assert out[0]["title"] == "Designer"
    assert out[0]["employment_type"] == "full-time"
    assert "Requirements" in out[0]["jd_text"]
    assert "3+ yrs" in out[0]["jd_text"]


def test_parse_lever_handles_contract_type():
    feed = [{"id": "1", "text": "X",
             "categories": {"commitment": "Contract"},
             "hostedUrl": "https://x", "createdAt": 1745126400000,
             "descriptionPlain": "X"}]
    out = parse_lever(feed, "acme")
    assert out[0]["employment_type"] == "contract"


def test_parse_lever_handles_intern_type():
    feed = [{"id": "1", "text": "X",
             "categories": {"commitment": "Internship"},
             "hostedUrl": "https://x", "createdAt": 1745126400000,
             "descriptionPlain": "X"}]
    out = parse_lever(feed, "acme")
    assert out[0]["employment_type"] == "internship"


def test_parse_lever_handles_non_list_input():
    assert parse_lever({}, "acme") == []
    assert parse_lever(None, "acme") == []


# ---------------------------------------------------------------------------
# Ashby parser
# ---------------------------------------------------------------------------

def test_parse_ashby_extracts_compensation():
    feed = {"jobs": [{
        "id": "x", "title": "Senior PM", "location": "SF",
        "publishedDate": "2026-04-20T00:00:00Z",
        "jobUrl": "https://jobs.ashbyhq.com/acme/x",
        "employmentType": "FULL_TIME",
        "compensation": {"summaryComponents": [
            {"compensationType": "Salary", "interval": "1 YEAR",
             "minValue": 170000, "maxValue": 210000, "currencyCode": "USD"},
        ]},
        "descriptionPlain": "PM role.",
    }]}
    out = parse_ashby(feed, "acme")
    assert out[0]["salary_listed"]["min"] == 170000
    assert out[0]["salary_listed"]["max"] == 210000
    assert out[0]["employment_type"] == "full-time"


def test_parse_ashby_falls_back_to_jd_salary():
    feed = {"jobs": [{
        "id": "x", "title": "PM", "location": "NY",
        "publishedDate": "2026-04-20T00:00:00Z",
        "jobUrl": "https://x", "employmentType": "FULL_TIME",
        "descriptionPlain": "Pay: $200,000 - $250,000.",
    }]}
    out = parse_ashby(feed, "acme")
    assert out[0]["salary_listed"] is not None
    assert out[0]["salary_listed"]["min"] == 200000


# ---------------------------------------------------------------------------
# Workable parser
# ---------------------------------------------------------------------------

def test_parse_workable_results_shape():
    feed = {"results": [{
        "id": "1", "title": "Eng",
        "location": {"city": "Berlin", "country": "Germany"},
        "url": "https://x", "created_at": "2026-04-20T00:00:00Z",
        "description": "<p>Eng role</p>",
        "requirements": "<p>5 yrs Python</p>",
    }]}
    out = parse_workable(feed, "acme")
    assert out[0]["title"] == "Eng"
    assert "Berlin" in out[0]["location"]
    assert "Python" in out[0]["jd_text"]


def test_parse_workable_telecommuting_flag():
    feed = {"results": [{
        "id": "1", "title": "X",
        "location": {"telecommuting": True, "country": "USA"},
        "url": "https://x", "created_at": "2026-04-20T00:00:00Z",
        "description": "X"}]}
    out = parse_workable(feed, "acme")
    assert "Remote" in out[0]["location"]


# ---------------------------------------------------------------------------
# SmartRecruiters parser
# ---------------------------------------------------------------------------

def test_parse_smartrecruiters_basic():
    feed = {"content": [{
        "id": "p1", "name": "Sales Rep",
        "location": {"city": "London", "country": "UK"},
        "releasedDate": "2026-04-20T00:00:00Z",
        "applyUrl": "https://x",
        "jobAd": {"sections": {"jobDescription": {"text": "<p>Sales role</p>"}}},
    }]}
    out = parse_smartrecruiters(feed, "acme")
    assert out[0]["title"] == "Sales Rep"
    assert "London" in out[0]["location"]
    assert "Sales role" in out[0]["jd_text"]


# ---------------------------------------------------------------------------
# URL builder
# ---------------------------------------------------------------------------

def test_build_feed_url_all_supported():
    for ats in ("greenhouse", "lever", "ashby", "workable", "smartrecruiters"):
        url = build_feed_url(ats, "demo")
        assert url.startswith("https://"), f"bad URL for {ats}: {url}"
        assert "demo" in url


def test_build_feed_url_unknown_raises():
    with pytest.raises(ValueError):
        build_feed_url("indeed", "demo")


def test_parsers_dict_complete():
    assert set(PARSERS.keys()) == {
        "greenhouse", "lever", "ashby", "workable", "smartrecruiters"
    }
