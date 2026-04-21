"""End-to-end integration test.

Walks the entire FATS pipeline using mock data to make sure the
modules connect properly. If any stage handoff breaks, this test fails
loudly.

Stages exercised:
  Stage 1 — profile build
  Stage 2 — role proposal
  Stage 3 — company plan
  Stage 4 — ATS parsing (with mock JSON)
  Stage 5 — dedupe → score → CSV → summary
  Stage 6 — resume tailoring (3 templates) → fabrication check
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts.profile import (
    new_profile, add_source_doc, add_evidence,
    compute_years_experience, infer_seniority, propose_roles,
    save_profile, load_profile, validate_profile,
)
from scripts.company_seed import plan_hunt_companies
from scripts.ats_fetchers import (
    parse_greenhouse, parse_lever, parse_ashby, build_feed_url,
)
from scripts.jobs import (
    dedupe, score_fit, ghost_risk, passes_filters,
    write_csv, write_summary_md, CSV_FIELDS,
)
from scripts.resume import build_resume, fabrication_check


def test_full_pipeline_marketing_user(tmp_path):
    """The canonical 'senior marketing manager looking for a new role' flow."""

    # --- Stage 1: build profile --------------------------------------------
    profile = new_profile("Jane Doe")
    profile["contact"].update({
        "email": "jane@example.com", "phone": "555-555-5555",
        "city": "Washington", "state_region": "DC",
        "linkedin_url": "https://linkedin.com/in/janedoe",
    })
    profile["headline"] = "Senior marketing leader"
    profile["summary"] = "Demand gen + ops veteran in B2B SaaS."
    profile["experience"] = [
        {
            "title": "Senior Marketing Manager", "company": "TechCorp",
            "location": "Washington, DC",
            "start": "2019-01", "end": None, "current": True,
            "bullets": [
                "Built marketing ops with HubSpot and Salesforce, cut lead routing time 70%.",
                "Managed 4 direct reports across demand gen and content.",
                "Scaled pipeline from $5M to $18M in 3 years.",
            ],
            "technologies": ["HubSpot", "Salesforce", "Marketo", "SQL"],
        },
        {
            "title": "Marketing Manager", "company": "StartupCo",
            "location": "Washington, DC",
            "start": "2016-06", "end": "2018-12", "current": False,
            "bullets": ["Led content strategy.", "Grew blog 300%."],
            "technologies": ["WordPress", "SEMrush"],
        },
    ]
    profile["education"] = [{"degree": "BS", "major": "Marketing",
                              "school": "University of Maryland", "year": 2016}]
    profile["skills"]["technical"] = ["SQL", "HubSpot", "Salesforce"]
    profile["skills"]["domains"] = ["Demand Gen", "Marketing Ops"]

    doc_id = add_source_doc(profile, "resume_pdf", "/r.pdf", "content")
    for s in ("HubSpot", "Salesforce", "Marketo", "SQL", "Demand Gen"):
        add_evidence(profile, "skills_evidence", s, doc_id, "loc")
    add_evidence(profile, "claims_evidence", "70%", doc_id, "loc")

    profile["years_experience_total"] = compute_years_experience(profile["experience"])
    profile["inferred_seniority"] = infer_seniority(profile)
    profile["job_preferences"]["locations"] = ["Washington, DC"]
    profile["job_preferences"]["remote_preference"] = "hybrid_or_remote"

    assert validate_profile(profile, None) == []
    assert profile["years_experience_total"] >= 5

    # Save + reload to confirm round-trip
    save_path = tmp_path / "profile.json"
    save_profile(profile, save_path)
    profile = load_profile(save_path)

    # --- Stage 2: propose roles --------------------------------------------
    roles = propose_roles(profile)
    assert roles["focused"], "no focused roles proposed"
    assert roles["adjacent"], "no adjacent roles proposed"
    target_roles = [
        {"title": t, "category": "focused",
         "role_constraints": {"industries": ["b2b_saas_martech"]}}
        for t in roles["focused"][:2]
    ]

    # --- Stage 3: company plan ---------------------------------------------
    plan = plan_hunt_companies(target_roles, ["greenhouse", "lever", "ashby"],
                               max_per_ats=10)
    assert len(plan["greenhouse"]) > 0
    # URL builder works
    for ats, companies in plan.items():
        for c in companies[:1]:
            url = build_feed_url(ats, c["slug"])
            assert url.startswith("http")

    # --- Stage 4: parse mock ATS responses ---------------------------------
    gh_mock = {"jobs": [{
        "id": 1, "title": "Senior Marketing Manager",
        "location": {"name": "Washington, DC"},
        "absolute_url": "https://boards.greenhouse.io/segment/jobs/1",
        "updated_at": "2026-04-19T20:00:00Z",
        "content": "<p>5+ years experience. HubSpot and Salesforce required. "
                   "Demand gen leadership. Salary: $160,000 - $195,000.</p>",
    }]}
    lever_mock = [{
        "id": "abc", "text": "Senior Growth Marketing Manager",
        "categories": {"location": "Remote - US", "commitment": "Full-time"},
        "hostedUrl": "https://jobs.lever.co/ramp/abc",
        "createdAt": 1745126400000,
        "descriptionPlain": "Lead growth marketing. SQL, HubSpot.",
    }]
    ashby_mock = {"jobs": [{
        "id": "x", "title": "Senior Product Marketing Manager",
        "location": "New York, NY",
        "publishedDate": "2026-04-20T08:00:00Z",
        "jobUrl": "https://jobs.ashbyhq.com/notion/x",
        "employmentType": "FULL_TIME",
        "compensation": {"summaryComponents": [
            {"compensationType": "Salary", "interval": "1 YEAR",
             "minValue": 170000, "maxValue": 210000, "currencyCode": "USD"},
        ]},
        "descriptionPlain": "PMM at Notion.",
    }]}

    raw_jobs = []
    raw_jobs += parse_greenhouse(gh_mock, "segment",
                                  {"name": "Segment", "size": "1000-5000",
                                   "industry": "b2b_saas_martech"})
    raw_jobs += parse_lever(lever_mock, "ramp",
                             {"name": "Ramp", "size": "200-1000",
                              "industry": "fintech"})
    raw_jobs += parse_ashby(ashby_mock, "notion",
                             {"name": "Notion", "size": "200-1000",
                              "industry": "b2b_saas"})
    assert len(raw_jobs) == 3

    # --- Stage 5: filter, dedupe, score, write CSV -------------------------
    settings = {
        "freshness_hours": 24 * 30,  # generous for the test
        "salary_floor": None, "exclude_companies": [], "exclude_keywords": [],
    }
    filtered = [j for j in raw_jobs if passes_filters(j, profile, settings)]
    assert len(filtered) >= 1, "all jobs filtered out unexpectedly"

    deduped = dedupe(filtered)

    for job in deduped:
        job["fit"] = score_fit(job, profile, settings,
                               jd_keywords=["HubSpot", "Salesforce", "Demand Gen"],
                               industries=["b2b_saas_martech"])
        job["ghost"] = ghost_risk(job)
        job["why_it_matches"] = "You've used the requested tools. "

    csv_path = tmp_path / "jobs.csv"
    write_csv(deduped, csv_path)
    rows = list(csv.DictReader(csv_path.open()))
    assert len(rows) == len(deduped)
    assert len(rows[0]) == 33

    summary_path = tmp_path / "summary.md"
    write_summary_md(deduped, summary_path)
    assert "FATS" in summary_path.read_text()

    # --- Stage 6: tailor a resume + fabrication check ----------------------
    top_job = deduped[0]
    tailored = {
        "name": profile["name"],
        "contact_line": "Washington, DC | jane@example.com | (555) 555-5555 | linkedin.com/in/janedoe",
        "summary": (f"{int(profile['years_experience_total'])} years driving "
                    "demand generation for B2B SaaS. Built marketing ops stack "
                    "that cut lead routing time 70%. Managed team of 4."),
        "skills": {
            "core_competencies": ["Demand Gen"],
            "tools_platforms": ["HubSpot", "Salesforce", "Marketo", "SQL"],
            "additional": [],
        },
        "experience": [
            {"title": "Senior Marketing Manager", "company": "TechCorp",
             "location": "Washington, DC", "start": "Jan 2019", "current": True,
             "bullets": ["Built marketing ops stack with HubSpot and Salesforce, cut lead routing time 70%.",
                         "Managed 4 direct reports across demand gen and content."]},
        ],
        "education": [{"degree": "BS", "major": "Marketing",
                       "school": "University of Maryland", "year": 2016, "honors": None}],
        "certifications": [],
    }

    # Build all 3 templates — both .docx (python-docx) and .pdf (reportlab)
    for tpl in ("clean_modern", "harvard", "mirror_user"):
        docx = tmp_path / f"resume_{tpl}.docx"
        build_resume(tpl, profile, tailored, docx, source_docx_path=None)
        assert docx.exists() and docx.stat().st_size > 5000

        pdf = tmp_path / f"resume_{tpl}.pdf"
        build_resume(tpl, profile, tailored, pdf, source_docx_path=None)
        assert pdf.exists() and pdf.stat().st_size > 2000
        assert pdf.read_bytes()[:5] == b"%PDF-"

    # Fabrication check should pass (we constructed tailored from real evidence)
    findings = fabrication_check(tailored, profile)
    assert findings == [], f"fabrication check unexpectedly flagged: {findings}"


def test_full_pipeline_catches_fabrications(tmp_path):
    """Same flow, but with a tainted resume — fabrication_check must catch it."""
    profile = new_profile("Jane Doe")
    profile["years_experience_total"] = 8
    profile["experience"] = [{"title": "X", "company": "Y", "current": True,
                              "bullets": ["did stuff"], "technologies": ["HubSpot"]}]
    profile["education"] = [{"degree": "BS", "major": "Mkt", "school": "UMD", "year": 2016}]
    doc_id = add_source_doc(profile, "resume_pdf", "/r.pdf", "x")
    add_evidence(profile, "skills_evidence", "HubSpot", doc_id, "loc")

    tainted = {
        "name": "Jane",
        "contact_line": "DC | x@x.com",
        "summary": "20 years experience. Cut time 99%. Managed team of 50.",
        "skills": {"core_competencies": ["Kubernetes"],
                   "tools_platforms": ["Marketo"], "additional": []},
        "experience": [{"company": "Y", "bullets": ["Grew revenue 1000%."]}],
        "education": [{"degree": "MBA", "major": "Bus", "school": "Harvard", "year": 2020}],
        "certifications": [{"name": "PMP", "issuer": "PMI", "year": 2022}],
    }
    findings = fabrication_check(tainted, profile)

    # Should catch: 20, 99%, team of 50, 50, 1000%, Kubernetes, Marketo,
    # MBA from Harvard, PMP cert.
    flagged_claims = [f["claim"].lower() for f in findings]
    assert any("20" == c or "20.0" == c for c in flagged_claims), f"didn't flag '20' year claim: {findings}"
    assert any("99" in c for c in flagged_claims), "didn't flag 99%"
    assert any("team of 50" in c for c in flagged_claims), "didn't flag team-of-50"
    assert any("kubernetes" in c for c in flagged_claims), "didn't flag Kubernetes"
    assert any("harvard" in c or "mba" in c for c in flagged_claims), "didn't flag Harvard/MBA"
    assert any("pmp" in c for c in flagged_claims), "didn't flag PMP"
