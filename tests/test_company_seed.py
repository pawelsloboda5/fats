"""Unit tests for scripts/company_seed.py."""

from __future__ import annotations

import pytest

from scripts.company_seed import (
    list_companies, filter_by_constraints, plan_hunt_companies,
    all_known_slugs,
)


# ---------------------------------------------------------------------------
# Loading and listing
# ---------------------------------------------------------------------------

def test_list_companies_greenhouse_nonempty():
    companies = list_companies("greenhouse")
    assert len(companies) > 50, "greenhouse seed should have many companies"


def test_list_companies_each_has_required_fields():
    for ats in ("greenhouse", "lever", "ashby", "workable", "smartrecruiters"):
        for c in list_companies(ats):
            for field in ("slug", "name", "size", "industry"):
                assert field in c, f"{ats}/{c.get('name','?')} missing {field}"


def test_list_companies_unknown_ats_returns_empty():
    assert list_companies("nonexistent_ats") == []


def test_all_known_slugs_returns_all_atses():
    slugs = all_known_slugs()
    assert "greenhouse" in slugs
    assert "lever" in slugs
    assert "ashby" in slugs
    assert "workable" in slugs
    assert "smartrecruiters" in slugs
    # No reserved keys leaked through
    assert "schema_version" not in slugs
    assert "notes" not in slugs


# ---------------------------------------------------------------------------
# filter_by_constraints
# ---------------------------------------------------------------------------

def test_filter_by_industry_b2b_saas():
    companies = list_companies("greenhouse")
    filtered = filter_by_constraints(companies, {"industries": ["b2b_saas"]})
    assert all("b2b_saas" in (c.get("industry") or "").lower() for c in filtered)
    assert len(filtered) > 0


def test_filter_by_industry_substring_match():
    companies = list_companies("greenhouse")
    filtered = filter_by_constraints(companies, {"industries": ["fintech"]})
    # Should match both 'fintech' and 'fintech_crypto'
    assert len(filtered) >= 2


def test_filter_by_size_max():
    companies = list_companies("greenhouse")
    filtered = filter_by_constraints(companies, {"company_size_max": 200})
    # All filtered companies should have size buckets ≤ 200
    for c in filtered:
        assert c["size"] in ("<50", "50-200", "unknown")


def test_filter_by_size_min():
    companies = list_companies("greenhouse")
    filtered = filter_by_constraints(companies, {"company_size_min": 1000})
    for c in filtered:
        assert c["size"] in ("1000-5000", "5000+", "unknown")


def test_filter_with_no_constraints_returns_all():
    companies = list_companies("greenhouse")
    assert filter_by_constraints(companies, None) == companies
    assert filter_by_constraints(companies, {}) == companies


# ---------------------------------------------------------------------------
# plan_hunt_companies
# ---------------------------------------------------------------------------

def test_plan_hunt_caps_per_ats():
    target_roles = [{"title": "X", "role_constraints": {}}]
    plan = plan_hunt_companies(target_roles, ["greenhouse"], max_per_ats=5)
    assert len(plan["greenhouse"]) <= 5


def test_plan_hunt_excludes_google_jobs():
    """google_jobs is not an ATS in this sense."""
    target_roles = [{"title": "X", "role_constraints": {}}]
    plan = plan_hunt_companies(target_roles, ["greenhouse", "google_jobs"], max_per_ats=10)
    assert "google_jobs" not in plan
    assert "greenhouse" in plan


def test_plan_hunt_prioritizes_constraint_matches():
    """Companies matching constraints should appear before non-matching fillers."""
    target_roles = [{"title": "X", "role_constraints": {"industries": ["b2b_saas"]}}]
    plan = plan_hunt_companies(target_roles, ["greenhouse"], max_per_ats=20)
    industries = [c.get("industry", "") for c in plan["greenhouse"]]
    # Of the picks, most should be b2b_saas-flavored if available
    saas_count = sum(1 for i in industries if "b2b_saas" in i)
    assert saas_count >= 5  # plenty of b2b_saas companies in seed


def test_plan_hunt_empty_target_roles_returns_top_n():
    plan = plan_hunt_companies([], ["lever"], max_per_ats=10)
    assert len(plan["lever"]) <= 10
    assert len(plan["lever"]) > 0


def test_plan_hunt_respects_enabled_list():
    plan = plan_hunt_companies([], ["lever", "ashby"], max_per_ats=5)
    assert set(plan.keys()) == {"lever", "ashby"}


def test_plan_hunt_dedupes_across_target_roles():
    """If two target roles match the same company, it should appear once."""
    target_roles = [
        {"title": "Marketing Manager", "role_constraints": {"industries": ["b2b_saas"]}},
        {"title": "Demand Gen Manager", "role_constraints": {"industries": ["b2b_saas"]}},
    ]
    plan = plan_hunt_companies(target_roles, ["greenhouse"], max_per_ats=10)
    slugs = [c["slug"] for c in plan["greenhouse"]]
    assert len(slugs) == len(set(slugs)), "duplicate slugs in plan"
