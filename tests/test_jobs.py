"""Unit tests for scripts/jobs.py."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from scripts.profile import new_profile, add_source_doc, add_evidence
from scripts.jobs import (
    dedupe, score_skills, score_experience_level, score_industry,
    score_location_comp, score_fit, ghost_risk, passes_filters,
    write_csv, write_summary_md, role_aliases, title_matches_targets,
    SOURCE_PRIORITY, CSV_FIELDS, _normalize_company, _normalize_title,
)


# ---------------------------------------------------------------------------
# Normalizers
# ---------------------------------------------------------------------------

def test_normalize_company_aliases():
    assert _normalize_company("Meta") == _normalize_company("Facebook")
    assert _normalize_company("Block") == _normalize_company("Square")
    assert _normalize_company("Alphabet") == _normalize_company("Google")


def test_normalize_company_case_insensitive():
    assert _normalize_company("ACME CORP") == _normalize_company("acme corp")


def test_normalize_title_strips_seniority():
    a = _normalize_title("Senior Software Engineer")
    b = _normalize_title("Sr. Software Engineer")
    c = _normalize_title("Software Engineer")
    assert a == b == c


# ---------------------------------------------------------------------------
# Dedupe
# ---------------------------------------------------------------------------

def _job(source_board, title="Eng", company="X", url=None, **kwargs):
    base = {
        "source_board": source_board,
        "source_url": url or f"https://{source_board}/x",
        "ats_type": source_board if source_board in SOURCE_PRIORITY else "unknown",
        "title": title, "company": company,
        "company_size": "unknown", "company_industry": "unknown",
        "location": "DC", "location_normalized": {"city": "DC", "is_remote": False},
        "posted_date": "2026-04-19T20:00Z", "hours_since_posted": 16,
        "employment_type": "full-time", "salary_listed": None,
        "jd_text": "Some text", "apply_url": url or f"https://{source_board}/x",
    }
    base.update(kwargs)
    return base


def test_dedupe_collapses_cross_posted():
    jobs = [_job("greenhouse"), _job("lever"), _job("google_jobs")]
    out = dedupe(jobs)
    assert len(out) == 1
    assert out[0]["primary_url"] == "https://greenhouse/x"
    assert len(out[0]["duplicate_urls"]) == 2


def test_dedupe_preserves_distinct_jobs():
    jobs = [_job("greenhouse", title="SWE", company="A"),
            _job("greenhouse", title="PM", company="A"),
            _job("greenhouse", title="SWE", company="B")]
    out = dedupe(jobs)
    assert len(out) == 3


def test_dedupe_ignores_seniority_decorators():
    """'Senior X' and 'Sr. X' at same company are duplicates."""
    jobs = [_job("greenhouse", title="Senior Engineer"),
            _job("lever", title="Sr. Engineer")]
    out = dedupe(jobs)
    assert len(out) == 1


def test_dedupe_picks_longest_jd():
    short = _job("lever", url="https://lev/1")
    short["jd_text"] = "short"
    long_ = _job("greenhouse", url="https://gh/1")
    long_["jd_text"] = "much longer description with more details"
    out = dedupe([short, long_])
    assert out[0]["jd_text"] == long_["jd_text"]


def test_dedupe_merges_salary_widest():
    a = _job("greenhouse", url="https://gh/1")
    a["salary_listed"] = {"min": 100000, "max": 150000, "currency": "USD", "period": "year"}
    b = _job("lever", url="https://lev/1")
    b["salary_listed"] = {"min": 90000, "max": 160000, "currency": "USD", "period": "year"}
    out = dedupe([a, b])
    assert out[0]["salary_listed"]["min"] == 90000
    assert out[0]["salary_listed"]["max"] == 160000


# ---------------------------------------------------------------------------
# Skills scoring
# ---------------------------------------------------------------------------

def _profile_with_skills(skills):
    p = new_profile("X")
    doc_id = add_source_doc(p, "resume_pdf", "/r.pdf", "content")
    for s in skills:
        add_evidence(p, "skills_evidence", s, doc_id, "loc")
    return p


def test_score_skills_perfect_match():
    p = _profile_with_skills(["Python", "SQL", "Go"])
    score, matched, missing = score_skills(["Python", "SQL", "Go"], p)
    assert score == 100
    assert set(matched) == {"Python", "SQL", "Go"}
    assert missing == []


def test_score_skills_partial_match():
    p = _profile_with_skills(["Python", "SQL"])
    score, matched, missing = score_skills(["Python", "SQL", "Go", "Rust"], p)
    assert score == 50  # 2 of 4
    assert "Go" in missing and "Rust" in missing


def test_score_skills_no_match():
    p = _profile_with_skills(["A"])
    score, matched, missing = score_skills(["B", "C"], p)
    assert score == 0
    assert matched == []


def test_score_skills_empty_jd_returns_neutral():
    p = _profile_with_skills(["A"])
    score, _, _ = score_skills([], p)
    assert score == 75


# ---------------------------------------------------------------------------
# Experience level scoring
# ---------------------------------------------------------------------------

def test_score_experience_exact_match():
    assert score_experience_level("senior", "senior") == 100


def test_score_experience_one_off():
    assert score_experience_level("staff", "senior") == 80


def test_score_experience_two_off():
    assert score_experience_level("staff", "mid") == 50


def test_score_experience_unknown_returns_neutral():
    assert score_experience_level("godlike", "senior") == 75


# ---------------------------------------------------------------------------
# Industry scoring
# ---------------------------------------------------------------------------

def test_score_industry_exact_match():
    assert score_industry("b2b_saas", ["b2b_saas"]) == 100


def test_score_industry_adjacent():
    score = score_industry("b2b_saas_devtools", ["b2b_saas_martech"])
    assert score >= 65  # adjacent SaaS family


def test_score_industry_distant():
    score = score_industry("manufacturing", ["b2b_saas"])
    assert score <= 65


def test_score_industry_no_user_history():
    assert score_industry("anything", []) == 60


# ---------------------------------------------------------------------------
# Location/comp scoring
# ---------------------------------------------------------------------------

def test_score_location_comp_remote_match():
    p = new_profile("X")
    p["job_preferences"]["locations"] = ["Washington, DC"]
    p["job_preferences"]["remote_preference"] = "hybrid_or_remote"
    job = {"location_normalized": {"is_remote": True, "remote_region": "Remote - US"}}
    score = score_location_comp(job, p, {"salary_floor": None})
    assert score >= 80


def test_score_location_comp_onsite_in_user_city():
    p = new_profile("X")
    p["job_preferences"]["locations"] = ["Washington"]
    p["job_preferences"]["remote_preference"] = "hybrid_or_remote"
    job = {"location_normalized": {"city": "Washington", "is_remote": False}}
    score = score_location_comp(job, p, {"salary_floor": None})
    assert score >= 80


def test_score_location_comp_salary_below_floor():
    p = new_profile("X")
    p["job_preferences"]["locations"] = ["DC"]
    job = {
        "location_normalized": {"city": "DC", "is_remote": False},
        "salary_listed": {"min": 50000, "max": 60000, "currency": "USD", "period": "year"},
    }
    score = score_location_comp(job, p, {"salary_floor": 200000})
    assert score < 70  # comp pulls average down


# ---------------------------------------------------------------------------
# Total fit score
# ---------------------------------------------------------------------------

def test_score_fit_total_in_range():
    p = _profile_with_skills(["Python"])
    p["inferred_seniority"] = "senior"
    p["job_preferences"]["locations"] = ["DC"]
    job = _job("greenhouse")
    job["company_industry"] = "b2b_saas"
    job["jd_text"] = "Senior role needing Python."
    settings = {"salary_floor": None}
    fit = score_fit(job, p, settings, ["Python"], ["b2b_saas"])
    assert 0 <= fit["total"] <= 100
    assert "skills" in fit and "experience" in fit


# ---------------------------------------------------------------------------
# Ghost detection
# ---------------------------------------------------------------------------

def test_ghost_detect_obvious_high():
    out = ghost_risk({
        "jd_text": "Always hiring. Join our talent network.",
        "company": "Acme Recruiters", "title": "X",
        "hours_since_posted": 24 * 60,
        "salary_listed": None, "source_board": "google_jobs",
        "duplicate_urls": [], "location_normalized": None,
    })
    assert out["risk"] == "high"
    assert out["points"] >= 6


def test_ghost_detect_clean_low():
    out = ghost_risk({
        "jd_text": "We need a Senior Python engineer with 5+ years experience to "
                    "own our payments team. You'll work on our checkout product. " * 3,
        "company": "Stripe", "title": "Senior Engineer",
        "hours_since_posted": 4,
        "salary_listed": {"min": 180000, "max": 220000, "currency": "USD", "period": "year"},
        "source_board": "greenhouse",
        "duplicate_urls": ["https://x", "https://y"],
        "location_normalized": None,
    })
    assert out["risk"] == "low"


def test_ghost_detect_staffing_agency_flagged():
    out = ghost_risk({
        "jd_text": "Generic job posting with some text and 5+ years required.",
        "company": "Premier Staffing Partners", "title": "X",
        "hours_since_posted": 100, "salary_listed": None,
        "source_board": "google_jobs", "duplicate_urls": [],
        "location_normalized": None,
    })
    # Should at least mention staffing
    assert "staffing" in out["reason"]


def test_ghost_detect_old_post_flagged():
    out = ghost_risk({
        "jd_text": "Job text with 5+ years required, team and product mentioned.",
        "company": "X", "title": "Y",
        "hours_since_posted": 24 * 50,  # 50 days
        "salary_listed": None, "source_board": "greenhouse",
        "duplicate_urls": [], "location_normalized": None,
    })
    assert "days ago" in out["reason"]


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

def test_passes_filters_freshness():
    p = new_profile("X")
    p["job_preferences"]["remote_preference"] = "any"
    job = _job("greenhouse", hours_since_posted=72)
    job["location_normalized"]["is_remote"] = True
    assert passes_filters(job, p, {"freshness_hours": 24}) is False
    assert passes_filters(job, p, {"freshness_hours": 96}) is True


def test_passes_filters_excluded_company():
    p = new_profile("X")
    p["job_preferences"]["remote_preference"] = "any"
    job = _job("greenhouse", company="Amazon")
    job["location_normalized"]["is_remote"] = True
    settings = {"exclude_companies": ["Amazon"]}
    assert passes_filters(job, p, settings) is False


def test_passes_filters_excluded_keyword():
    p = new_profile("X")
    p["job_preferences"]["remote_preference"] = "any"
    job = _job("greenhouse")
    job["location_normalized"]["is_remote"] = True
    job["jd_text"] = "Requires active Top Secret clearance"
    settings = {"exclude_keywords": ["clearance"]}
    assert passes_filters(job, p, settings) is False


def test_passes_filters_salary_floor_drops_listed_below():
    p = new_profile("X")
    p["job_preferences"]["remote_preference"] = "any"
    job = _job("greenhouse")
    job["location_normalized"]["is_remote"] = True
    job["salary_listed"] = {"min": 50000, "max": 60000, "currency": "USD", "period": "year"}
    assert passes_filters(job, p, {"salary_floor": 100000}) is False


def test_passes_filters_salary_floor_keeps_unlisted():
    """A job with no listed salary should NOT be dropped by floor."""
    p = new_profile("X")
    p["job_preferences"]["remote_preference"] = "any"
    job = _job("greenhouse")
    job["location_normalized"]["is_remote"] = True
    job["salary_listed"] = None
    assert passes_filters(job, p, {"salary_floor": 200000}) is True


def test_passes_filters_remote_only_drops_onsite():
    p = new_profile("X")
    p["job_preferences"]["remote_preference"] = "remote_only"
    job = _job("greenhouse")
    job["location_normalized"] = {"city": "DC", "is_remote": False}
    assert passes_filters(job, p, {}) is False


# ---------------------------------------------------------------------------
# CSV writing
# ---------------------------------------------------------------------------

def test_write_csv_has_33_columns(tmp_path):
    p = _profile_with_skills(["X"])
    p["job_preferences"]["remote_preference"] = "any"
    job = _job("greenhouse")
    job["location_normalized"]["is_remote"] = True
    job["fit"] = score_fit(job, p, {}, ["X"], [])
    job["ghost"] = ghost_risk(job)
    out_path = tmp_path / "out.csv"
    write_csv([job], out_path)
    rows = list(csv.DictReader(out_path.open()))
    assert len(rows) == 1
    assert len(rows[0]) == 33
    assert set(rows[0].keys()) == set(CSV_FIELDS)


def test_write_csv_ranks_by_fit_desc(tmp_path):
    p = new_profile("X")
    p["job_preferences"]["remote_preference"] = "any"
    a = _job("greenhouse", title="A")
    a["location_normalized"]["is_remote"] = True
    b = _job("greenhouse", title="B")
    b["location_normalized"]["is_remote"] = True
    a["fit"] = {"total": 50, "skills": 0, "experience": 0, "industry": 0,
                "location_comp": 0, "matched_keywords": [], "missing_keywords": [],
                "detected_role_seniority": "mid"}
    b["fit"] = {"total": 90, "skills": 0, "experience": 0, "industry": 0,
                "location_comp": 0, "matched_keywords": [], "missing_keywords": [],
                "detected_role_seniority": "mid"}
    a["ghost"] = ghost_risk(a)
    b["ghost"] = ghost_risk(b)
    out_path = tmp_path / "out.csv"
    write_csv([a, b], out_path)
    rows = list(csv.DictReader(out_path.open()))
    assert rows[0]["job_title"] == "B"  # higher fit ranked first
    assert rows[0]["rank"] == "1"


def test_write_csv_handles_jd_with_commas_and_newlines(tmp_path):
    p = new_profile("X")
    p["job_preferences"]["remote_preference"] = "any"
    job = _job("greenhouse")
    job["location_normalized"]["is_remote"] = True
    job["jd_text"] = "Long, comma-laden,\ndescription with newlines.\n\nMultiple paragraphs."
    job["fit"] = score_fit(job, p, {}, [], [])
    job["ghost"] = ghost_risk(job)
    out_path = tmp_path / "out.csv"
    write_csv([job], out_path)
    rows = list(csv.DictReader(out_path.open()))
    assert len(rows) == 1
    assert "comma-laden" in rows[0]["full_jd"]


def test_write_summary_md_has_top_n_rows(tmp_path):
    p = new_profile("X")
    p["job_preferences"]["remote_preference"] = "any"
    jobs = []
    for i in range(15):
        j = _job("greenhouse", title=f"Role {i}")
        j["location_normalized"]["is_remote"] = True
        j["fit"] = {"total": 100 - i, "skills": 0, "experience": 0,
                    "industry": 0, "location_comp": 0,
                    "matched_keywords": [], "missing_keywords": [],
                    "detected_role_seniority": "mid"}
        j["ghost"] = ghost_risk(j)
        jobs.append(j)
    out_path = tmp_path / "summary.md"
    write_summary_md(jobs, out_path, top_n=10)
    text = out_path.read_text()
    # Should include top 10 rows
    assert "Role 0" in text
    assert "Role 9" in text
    assert "Role 14" not in text  # outside top 10


# ---------------------------------------------------------------------------
# Role aliases
# ---------------------------------------------------------------------------

def test_role_aliases_includes_seniority_variants():
    aliases = role_aliases("Senior Software Engineer")
    assert any("sr." in a.lower() or "sr " in a.lower() for a in aliases)


def test_title_matches_targets_substring():
    targets = [{"title": "Software Engineer"}]
    assert title_matches_targets("Senior Software Engineer", targets) is True
    assert title_matches_targets("Software Engineer II", targets) is True
    assert title_matches_targets("Marketing Manager", targets) is False
