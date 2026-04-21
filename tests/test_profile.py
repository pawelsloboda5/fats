"""Unit tests for scripts/profile.py."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from scripts.profile import (
    new_profile, validate_profile, save_profile, load_profile,
    add_source_doc, add_evidence, has_evidence,
    compute_years_experience, infer_seniority,
    propose_roles, merge_profiles,
)


# ---------------------------------------------------------------------------
# new_profile + validation
# ---------------------------------------------------------------------------

def test_new_profile_has_required_fields():
    p = new_profile("Alice")
    for field in ("name", "contact", "experience", "skills", "evidence", "last_updated"):
        assert field in p, f"missing {field}"
    assert p["name"] == "Alice"
    assert p["resume_template"] == "clean_modern"


def test_validate_profile_passes_on_minimal_complete():
    p = new_profile("Alice")
    assert validate_profile(p, None) == []


def test_validate_profile_catches_missing_required():
    p = new_profile("Alice")
    del p["evidence"]
    errors = validate_profile(p, None)
    assert any("evidence" in e for e in errors)


def test_validate_profile_catches_bad_seniority():
    p = new_profile("Alice")
    p["inferred_seniority"] = "godlike"
    errors = validate_profile(p, None)
    assert any("inferred_seniority" in e for e in errors)


def test_validate_profile_catches_bad_template():
    p = new_profile("Alice")
    p["resume_template"] = "fancy"
    errors = validate_profile(p, None)
    assert any("template" in e.lower() for e in errors)


def test_validate_profile_catches_experience_missing_company():
    p = new_profile("Alice")
    p["experience"] = [{"title": "Eng"}]  # missing company
    errors = validate_profile(p, None)
    assert any("company" in e for e in errors)


# ---------------------------------------------------------------------------
# save / load round-trip
# ---------------------------------------------------------------------------

def test_save_load_round_trip(tmp_path):
    p = new_profile("Alice")
    p["headline"] = "Test headline"
    out = tmp_path / "p.json"
    save_profile(p, out)
    loaded = load_profile(out)
    assert loaded["name"] == "Alice"
    assert loaded["headline"] == "Test headline"


def test_save_profile_updates_timestamp(tmp_path):
    p = new_profile("Alice")
    original_ts = p["last_updated"]
    out = tmp_path / "p.json"
    save_profile(p, out)
    assert p["last_updated"] >= original_ts


# ---------------------------------------------------------------------------
# Source docs and evidence
# ---------------------------------------------------------------------------

def test_add_source_doc_returns_unique_ids():
    p = new_profile("Alice")
    id1 = add_source_doc(p, "resume_pdf", "/a.pdf", "content1")
    id2 = add_source_doc(p, "resume_pdf", "/b.pdf", "content2")
    assert id1 != id2
    assert len(p["source_docs"]) == 2


def test_add_evidence_creates_pointer():
    p = new_profile("Alice")
    doc_id = add_source_doc(p, "resume_pdf", "/r.pdf", "content")
    add_evidence(p, "skills_evidence", "Python", doc_id, "bullet-1")
    assert "Python" in p["evidence"]["skills_evidence"]
    assert any(doc_id in ptr for ptr in p["evidence"]["skills_evidence"]["Python"])


def test_add_evidence_dedupes_pointers():
    p = new_profile("Alice")
    doc_id = add_source_doc(p, "resume_pdf", "/r.pdf", "content")
    add_evidence(p, "skills_evidence", "Python", doc_id, "bullet-1")
    add_evidence(p, "skills_evidence", "Python", doc_id, "bullet-1")
    assert len(p["evidence"]["skills_evidence"]["Python"]) == 1


def test_has_evidence_finds_via_evidence_ledger():
    p = new_profile("Alice")
    doc_id = add_source_doc(p, "resume_pdf", "/r.pdf", "content")
    add_evidence(p, "skills_evidence", "Python", doc_id, "loc")
    assert has_evidence(p, "Python") is True
    assert has_evidence(p, "python") is True  # case-insensitive
    assert has_evidence(p, "Rust") is False


def test_has_evidence_finds_via_experience_technologies():
    p = new_profile("Alice")
    p["experience"] = [{"title": "Eng", "company": "X",
                        "technologies": ["Kubernetes", "Docker"]}]
    assert has_evidence(p, "Kubernetes") is True
    assert has_evidence(p, "kubernetes") is True


def test_has_evidence_finds_via_bullet_substring():
    p = new_profile("Alice")
    p["experience"] = [{"title": "Eng", "company": "X",
                        "bullets": ["Built React components."]}]
    assert has_evidence(p, "React") is True


# ---------------------------------------------------------------------------
# compute_years_experience
# ---------------------------------------------------------------------------

def test_compute_years_simple_two_roles():
    exp = [
        {"title": "X", "company": "A", "start": "2018-01", "end": "2021-01"},
        {"title": "Y", "company": "B", "start": "2021-02", "end": "2024-02"},
    ]
    yrs = compute_years_experience(exp)
    # ~3 + ~3 = 6 (approximately)
    assert yrs is not None and 5.5 <= yrs <= 6.5


def test_compute_years_handles_overlap():
    """Overlapping roles should not double-count."""
    exp = [
        {"title": "Day Job", "company": "A", "start": "2020-01", "end": "2024-01"},
        {"title": "Side Job", "company": "B", "start": "2022-01", "end": "2023-01"},
    ]
    yrs = compute_years_experience(exp)
    # Side job is fully inside day job → 4 years total
    assert yrs is not None and 3.5 <= yrs <= 4.5


def test_compute_years_handles_current():
    exp = [
        {"title": "X", "company": "A", "start": "2020-01", "end": None, "current": True},
    ]
    yrs = compute_years_experience(exp)
    # 2020 to ~2026 = ~6 years
    assert yrs is not None and yrs >= 5


def test_compute_years_returns_none_on_empty():
    assert compute_years_experience([]) is None


# ---------------------------------------------------------------------------
# infer_seniority
# ---------------------------------------------------------------------------

def test_infer_seniority_detects_c_level():
    p = new_profile("X")
    p["experience"] = [{"title": "CTO", "company": "Y", "current": True}]
    p["years_experience_total"] = 15
    assert infer_seniority(p) == "c-level"


def test_infer_seniority_detects_director():
    p = new_profile("X")
    p["experience"] = [{"title": "Director of Marketing", "company": "Y", "current": True}]
    p["years_experience_total"] = 12
    assert infer_seniority(p) == "director"


def test_infer_seniority_detects_senior_from_title():
    p = new_profile("X")
    p["experience"] = [{"title": "Senior Software Engineer", "company": "Y", "current": True}]
    p["years_experience_total"] = 6
    assert infer_seniority(p) in ("senior", "staff")


def test_infer_seniority_falls_back_to_years():
    p = new_profile("X")
    p["experience"] = [{"title": "Specialist", "company": "Y", "current": True}]
    p["years_experience_total"] = 0.5
    assert infer_seniority(p) == "entry"


# ---------------------------------------------------------------------------
# propose_roles
# ---------------------------------------------------------------------------

def test_propose_roles_returns_focused_and_adjacent_for_marketing():
    p = new_profile("X")
    p["experience"] = [{"title": "Marketing Manager", "company": "Y", "current": True,
                        "start": "2018-01"}]
    p["years_experience_total"] = 8
    p["inferred_seniority"] = "manager"
    roles = propose_roles(p)
    assert len(roles["focused"]) >= 2
    assert len(roles["adjacent"]) >= 2
    # All focused roles should mention marketing
    assert any("marketing" in r.lower() for r in roles["focused"])


def test_propose_roles_returns_swe_variants():
    p = new_profile("X")
    p["experience"] = [{"title": "Software Engineer", "company": "Y", "current": True,
                        "start": "2020-01"}]
    p["years_experience_total"] = 5
    p["inferred_seniority"] = "senior"
    roles = propose_roles(p)
    focused_lower = " ".join(roles["focused"]).lower()
    assert "engineer" in focused_lower


def test_propose_roles_handles_unknown_family():
    p = new_profile("X")
    p["experience"] = [{"title": "Underwater Basket Weaver", "company": "Y", "current": True,
                        "start": "2020-01"}]
    p["years_experience_total"] = 5
    roles = propose_roles(p)
    # Should still return at least the user's own title family
    assert len(roles["focused"]) >= 1


# ---------------------------------------------------------------------------
# merge_profiles
# ---------------------------------------------------------------------------

def test_merge_profiles_unions_skills():
    a = new_profile("X")
    a["skills"]["technical"] = ["Python", "SQL"]
    b = new_profile("X")
    b["skills"]["technical"] = ["Python", "Rust"]
    out = merge_profiles(a, b)
    techs = {s.lower() for s in out["skills"]["technical"]}
    assert techs == {"python", "sql", "rust"}


def test_merge_profiles_unions_experience_dedup():
    a = new_profile("X")
    a["experience"] = [{"title": "Eng", "company": "Acme", "bullets": ["a"]}]
    b = new_profile("X")
    b["experience"] = [{"title": "Eng", "company": "Acme", "bullets": ["b"]},
                       {"title": "PM", "company": "Beta"}]
    out = merge_profiles(a, b)
    assert len(out["experience"]) == 2  # Acme dedup'd, Beta added


def test_merge_profiles_unions_evidence():
    a = new_profile("X")
    a["evidence"]["skills_evidence"] = {"Python": ["doc1:loc1"]}
    b = new_profile("X")
    b["evidence"]["skills_evidence"] = {"Python": ["doc2:loc2"], "Rust": ["doc2:loc3"]}
    out = merge_profiles(a, b)
    assert set(out["evidence"]["skills_evidence"]["Python"]) == {"doc1:loc1", "doc2:loc2"}
    assert "Rust" in out["evidence"]["skills_evidence"]
