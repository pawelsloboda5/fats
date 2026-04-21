"""FATS health check.

Runs a comprehensive self-test of every component the skill depends on:
imports, schemas, seed data, parsers, scoring, resume rendering, fabrication
detection, and the file system.

Invoked by `/fats-healthcheck` and recommended as the first command after
installing the skill, so users can confirm everything works in their
environment before they hand over a real resume.

Usage as a script:
    python3 -m scripts.healthcheck

Usage from the orchestrator:
    from scripts.healthcheck import run_healthcheck
    report = run_healthcheck()
    # report = {"summary": "ok"|"degraded"|"failed",
    #           "passed": int, "failed": int, "warnings": int,
    #           "checks": [{"id":..., "name":..., "status":..., "detail":...}, ...]}
"""

from __future__ import annotations

import json
import sys
import tempfile
import traceback
from pathlib import Path


# ---------------------------------------------------------------------------
# Check runner harness
# ---------------------------------------------------------------------------

class _Reporter:
    def __init__(self):
        self.checks = []

    def record(self, check_id, name, status, detail=""):
        # status: "pass" | "fail" | "warn"
        self.checks.append({
            "id": check_id, "name": name, "status": status, "detail": detail,
        })

    def summary(self):
        passed = sum(1 for c in self.checks if c["status"] == "pass")
        failed = sum(1 for c in self.checks if c["status"] == "fail")
        warned = sum(1 for c in self.checks if c["status"] == "warn")
        if failed:
            verdict = "failed"
        elif warned:
            verdict = "degraded"
        else:
            verdict = "ok"
        return {
            "summary": verdict,
            "passed": passed, "failed": failed, "warnings": warned,
            "checks": self.checks,
        }


def _check(reporter, check_id, name, fn):
    """Wrap a check function; capture exceptions as failures."""
    try:
        result = fn()
        if result is True or result is None:
            reporter.record(check_id, name, "pass")
        elif isinstance(result, tuple) and result[0] == "warn":
            reporter.record(check_id, name, "warn", detail=result[1])
        else:
            reporter.record(check_id, name, "pass", detail=str(result))
    except Exception as e:
        reporter.record(check_id, name, "fail", detail=f"{type(e).__name__}: {e}")


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def _check_imports():
    """All five script modules must import without error."""
    import importlib
    modules = ["scripts.profile", "scripts.ats_fetchers", "scripts.jobs",
               "scripts.resume", "scripts.company_seed"]
    for m in modules:
        importlib.import_module(m)
    return f"{len(modules)} modules imported"


def _check_schema_files():
    """Schema and settings JSON files must exist, parse, and have expected keys."""
    here = Path(__file__).parent.parent
    schema_path = here / "assets" / "profile_schema.json"
    settings_path = here / "assets" / "settings_defaults.json"
    seed_path = here / "assets" / "company_list_seed.json"

    for p in (schema_path, settings_path, seed_path):
        if not p.exists():
            raise FileNotFoundError(f"missing: {p}")
        json.loads(p.read_text())  # validates JSON

    schema = json.loads(schema_path.read_text())
    if "properties" not in schema or "name" not in schema["properties"]:
        raise ValueError("profile_schema.json missing expected structure")
    settings = json.loads(settings_path.read_text())
    for required in ("freshness_hours", "target_count", "boards_enabled"):
        if required not in settings:
            raise ValueError(f"settings_defaults.json missing {required}")
    return "3 asset files valid"


def _check_company_seed():
    """Seed list must have non-empty entries for each major ATS."""
    from scripts.company_seed import list_companies, all_known_slugs
    counts = {}
    for ats in ("greenhouse", "lever", "ashby", "workable", "smartrecruiters"):
        n = len(list_companies(ats))
        counts[ats] = n
        if n == 0:
            raise ValueError(f"seed list is empty for {ats}")
    total = sum(counts.values())
    return f"{total} companies across {len(counts)} ATSes ({counts})"


def _check_profile_lifecycle():
    """new_profile → fill → validate → save → load round-trip."""
    from scripts.profile import (
        new_profile, validate_profile, save_profile, load_profile,
        compute_years_experience, infer_seniority, propose_roles,
        add_source_doc, add_evidence, has_evidence,
    )
    p = new_profile("Test User")
    p["contact"]["email"] = "test@example.com"
    p["contact"]["city"] = "Washington"
    p["experience"] = [
        {"title": "Senior Software Engineer", "company": "Acme",
         "start": "2019-01", "end": None, "current": True,
         "bullets": ["Wrote production Python."],
         "technologies": ["Python", "PostgreSQL"]},
    ]
    doc_id = add_source_doc(p, "resume_pdf", "/fake/r.pdf", "content")
    add_evidence(p, "skills_evidence", "Python", doc_id, "bullet-1")

    if not has_evidence(p, "Python"):
        raise ValueError("has_evidence failed to find Python")
    if has_evidence(p, "Rust"):
        raise ValueError("has_evidence falsely matched Rust")

    p["years_experience_total"] = compute_years_experience(p["experience"])
    p["inferred_seniority"] = infer_seniority(p)

    errors = validate_profile(p, None)
    if errors:
        raise ValueError(f"validate_profile errors: {errors}")

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = Path(f.name)
    save_profile(p, path)
    loaded = load_profile(path)
    if loaded["name"] != "Test User":
        raise ValueError("round-trip failed")
    path.unlink(missing_ok=True)

    roles = propose_roles(p)
    if len(roles["focused"]) == 0:
        raise ValueError("propose_roles returned no focused roles")
    return f"profile lifecycle ok (seniority={p['inferred_seniority']}, years={p['years_experience_total']})"


def _check_ats_parsers():
    """All 5 parsers handle their own mock JSON shapes."""
    from scripts.ats_fetchers import (
        parse_greenhouse, parse_lever, parse_ashby,
        parse_workable, parse_smartrecruiters, build_feed_url,
    )

    # Greenhouse
    gh = {"jobs": [{"id": 1, "title": "SWE", "location": {"name": "Remote - US"},
                     "absolute_url": "https://x/1", "updated_at": "2026-04-19T20:00:00Z",
                     "content": "<p>Job</p>"}]}
    out = parse_greenhouse(gh, "acme")
    assert len(out) == 1 and out[0]["title"] == "SWE", "greenhouse failed"
    assert out[0]["location_normalized"]["is_remote"] is True

    # Lever
    lever = [{"id": "a", "text": "Designer",
              "categories": {"location": "NYC", "commitment": "Full-time"},
              "hostedUrl": "https://x", "createdAt": 1745126400000,
              "descriptionPlain": "Design role"}]
    out = parse_lever(lever, "acme")
    assert out[0]["employment_type"] == "full-time"

    # Ashby (with comp)
    ashby = {"jobs": [{"id": "z", "title": "PM", "location": "SF",
                       "publishedDate": "2026-04-20T00:00:00Z",
                       "jobUrl": "https://x", "employmentType": "FULL_TIME",
                       "compensation": {"summaryComponents": [
                           {"compensationType": "Salary", "minValue": 150000,
                            "maxValue": 180000, "currencyCode": "USD"}
                       ]},
                       "descriptionPlain": "PM role"}]}
    out = parse_ashby(ashby, "acme")
    assert out[0]["salary_listed"]["min"] == 150000

    # Workable
    wk = {"results": [{"id": "1", "title": "Eng",
                       "location": {"city": "Berlin", "country": "Germany"},
                       "url": "https://x", "created_at": "2026-04-20T00:00:00Z",
                       "description": "<p>Eng</p>"}]}
    out = parse_workable(wk, "acme")
    assert out[0]["location_normalized"]["city"] == "Berlin"

    # SmartRecruiters
    sr = {"content": [{"id": "p1", "name": "Sales",
                       "location": {"city": "London", "country": "UK"},
                       "releasedDate": "2026-04-20T00:00:00Z",
                       "applyUrl": "https://x",
                       "jobAd": {"sections": {"jobDescription": {"text": "<p>Sales role</p>"}}}}]}
    out = parse_smartrecruiters(sr, "acme")
    assert out[0]["title"] == "Sales"

    # URL builder
    for ats in ("greenhouse", "lever", "ashby", "workable", "smartrecruiters"):
        url = build_feed_url(ats, "demo")
        assert url.startswith("http"), f"bad url for {ats}: {url}"

    return "5 ATS parsers + URL builder ok"


def _check_dedupe_and_scoring():
    """Build a small mock pipeline: dedupe → score → CSV."""
    from scripts.profile import new_profile, add_source_doc, add_evidence
    from scripts.jobs import dedupe, score_fit, ghost_risk, passes_filters, write_csv

    profile = new_profile("Tester")
    profile["inferred_seniority"] = "senior"
    profile["job_preferences"]["locations"] = ["Washington, DC"]
    profile["job_preferences"]["remote_preference"] = "hybrid_or_remote"
    profile["experience"] = [
        {"title": "Senior Marketing Manager", "company": "X",
         "current": True, "start": "2018-01",
         "bullets": ["Used HubSpot for demand gen."],
         "technologies": ["HubSpot"]},
    ]
    doc_id = add_source_doc(profile, "resume_pdf", "/r.pdf", "content")
    add_evidence(profile, "skills_evidence", "HubSpot", doc_id, "bullet-1")

    jobs = [
        {"source_board": "greenhouse", "source_url": "https://gh/1",
         "ats_type": "greenhouse", "title": "Senior Marketing Manager",
         "company": "Segment", "company_size": "1000-5000",
         "company_industry": "b2b_saas_martech", "location": "Washington, DC",
         "location_normalized": {"city": "Washington", "state": "DC", "is_remote": False},
         "posted_date": "2026-04-19T20:00Z", "hours_since_posted": 16,
         "employment_type": "full-time",
         "salary_listed": {"min": 160000, "max": 195000, "currency": "USD", "period": "year"},
         "jd_text": "Need HubSpot, demand gen, leadership.", "apply_url": "https://gh/1"},
        {"source_board": "lever", "source_url": "https://lv/1",
         "ats_type": "lever", "title": "Sr. Marketing Manager",
         "company": "Segment", "company_size": "1000-5000",
         "company_industry": "b2b_saas_martech", "location": "Washington, DC",
         "location_normalized": {"city": "Washington", "state": "DC", "is_remote": False},
         "posted_date": "2026-04-19T20:00Z", "hours_since_posted": 16,
         "employment_type": "full-time", "salary_listed": None,
         "jd_text": "Same role.", "apply_url": "https://lv/1"},
    ]

    deduped = dedupe(jobs)
    if len(deduped) != 1:
        raise ValueError(f"dedupe should have collapsed 2 jobs to 1, got {len(deduped)}")
    if deduped[0]["primary_url"] != "https://gh/1":
        raise ValueError("dedupe should have picked greenhouse over lever")

    settings = {"freshness_hours": 24, "salary_floor": 100000,
                "exclude_companies": [], "exclude_keywords": []}
    if not passes_filters(deduped[0], profile, settings):
        raise ValueError("filter rejected a valid job")

    fit = score_fit(deduped[0], profile, settings,
                    jd_keywords=["HubSpot", "demand gen", "leadership"],
                    industries=["b2b_saas_martech"])
    deduped[0]["fit"] = fit
    deduped[0]["ghost"] = ghost_risk(deduped[0])
    if fit["total"] < 50:
        raise ValueError(f"unexpectedly low fit: {fit}")

    with tempfile.TemporaryDirectory() as d:
        csv_path = Path(d) / "out.csv"
        write_csv(deduped, csv_path)
        if csv_path.stat().st_size == 0:
            raise ValueError("CSV is empty")
        # Verify column count
        first_line = csv_path.read_text().splitlines()[0]
        cols = first_line.count(",") + 1
        if cols != 33:
            raise ValueError(f"CSV has {cols} columns, expected 33")

    return f"dedupe→score→CSV ok (fit={fit['total']}, ghost={deduped[0]['ghost']['risk']})"


def _check_ghost_detection():
    """Synthetic ghost-y job should classify high; clean job should classify low."""
    from scripts.jobs import ghost_risk
    ghost = ghost_risk({
        "jd_text": "Join our talent network. We're always hiring.",
        "company": "Acme Recruiters", "title": "Director",
        "hours_since_posted": 24 * 60,
        "salary_listed": None, "source_board": "google_jobs",
        "duplicate_urls": [], "location_normalized": None,
    })
    if ghost["risk"] != "high":
        raise ValueError(f"ghost detector missed obvious ghost (got {ghost['risk']})")

    clean = ghost_risk({
        "jd_text": "We need 5+ years of Python experience for our backend platform "
                   "team. You'll own the lead routing project end-to-end. " * 3,
        "company": "Stripe", "title": "Senior SWE", "hours_since_posted": 4,
        "salary_listed": {"min": 180000, "max": 220000, "currency": "USD", "period": "year"},
        "source_board": "greenhouse", "duplicate_urls": ["https://x/1", "https://x/2"],
        "location_normalized": None,
    })
    if clean["risk"] != "low":
        raise ValueError(f"ghost detector flagged a clean job: {clean}")

    return "ghost detection: high-risk and low-risk classified correctly"


_SAMPLE_TAILORED = {
    "name": "Test User",
    "contact_line": "DC | t@x.com | (555) 555-5555",
    "summary": "8 years of relevant experience.",
    "skills": {"core_competencies": ["Skill A"], "tools_platforms": ["Tool A"], "additional": []},
    "experience": [{"title": "Engineer", "company": "Acme",
                    "location": "DC", "start": "2019-01", "end": None,
                    "current": True, "bullets": ["Built things.", "Shipped them."]}],
    "education": [{"degree": "BS", "major": "CS", "school": "U", "year": 2019, "honors": None}],
    "certifications": [],
}


def _check_resume_rendering():
    """All 3 templates render non-empty .docx."""
    from scripts.profile import new_profile
    from scripts.resume import build_resume

    profile = new_profile("Test User")
    profile["years_experience_total"] = 8
    with tempfile.TemporaryDirectory() as d:
        for tpl in ("clean_modern", "harvard", "mirror_user"):
            out = Path(d) / f"r_{tpl}.docx"
            build_resume(tpl, profile, _SAMPLE_TAILORED, out, source_docx_path=None)
            if not out.exists() or out.stat().st_size < 5000:
                raise ValueError(f"{tpl} produced suspicious docx (size={out.stat().st_size})")
    return "3 templates rendered ok"


def _check_pdf_rendering():
    """All 3 templates render a valid .pdf directly via reportlab."""
    from scripts.profile import new_profile
    from scripts.resume import build_resume

    profile = new_profile("PDF Tester")
    profile["years_experience_total"] = 3
    with tempfile.TemporaryDirectory() as d:
        for tpl in ("clean_modern", "harvard", "mirror_user"):
            pdf = Path(d) / f"r_{tpl}.pdf"
            build_resume(tpl, profile, _SAMPLE_TAILORED, pdf, source_docx_path=None)
            if not pdf.exists() or pdf.stat().st_size < 2000:
                raise ValueError(f"{tpl} produced suspicious pdf (size={pdf.stat().st_size})")
            if pdf.read_bytes()[:5] != b"%PDF-":
                raise ValueError(f"{tpl} output is not a valid PDF")
    return "3 templates rendered as PDF ok"


def _check_bundled_fonts():
    """Bundled OFL TTFs must exist and be valid."""
    fonts_dir = Path(__file__).parent.parent / "assets" / "fonts"
    required = ("EBGaramond-Regular.ttf", "EBGaramond-Bold.ttf",
                "Carlito-Regular.ttf", "Carlito-Bold.ttf")
    missing = [f for f in required if not (fonts_dir / f).exists()]
    if missing:
        return ("warn", f"missing bundled fonts: {missing} — templates will "
                        f"fall back to built-in Helvetica/Times")
    for name in required:
        head = (fonts_dir / name).read_bytes()[:4]
        if head not in (b"\x00\x01\x00\x00", b"OTTO", b"true"):
            raise ValueError(f"{name} has bad TTF header: {head.hex()}")
    return f"4 bundled fonts ok ({', '.join(required)})"


def _check_fabrication_check():
    """Clean content passes; tainted content gets flagged on every category."""
    from scripts.profile import new_profile, add_source_doc, add_evidence
    from scripts.resume import fabrication_check

    profile = new_profile("Honest Hannah")
    profile["years_experience_total"] = 8
    profile["experience"] = [
        {"title": "Marketing Mgr", "company": "X",
         "current": True, "start": "2018-01",
         "bullets": ["Cut lead time 70%.", "Managed 4 reports."],
         "technologies": ["HubSpot", "Salesforce"]}
    ]
    profile["education"] = [{"degree": "BS", "major": "Mkt", "school": "U", "year": 2016}]
    doc_id = add_source_doc(profile, "resume_pdf", "/r.pdf", "content")
    add_evidence(profile, "skills_evidence", "HubSpot", doc_id, "bullet-1")
    add_evidence(profile, "skills_evidence", "Salesforce", doc_id, "bullet-1")

    clean = {
        "name": "Honest Hannah",
        "summary": "8 years in marketing. Cut lead time 70% at X. Managed team of 4.",
        "skills": {"core_competencies": ["HubSpot"], "tools_platforms": ["Salesforce"], "additional": []},
        "experience": [{"company": "X", "bullets": ["Cut lead time 70%."]}],
        "education": [{"degree": "BS", "major": "Mkt", "school": "U", "year": 2016}],
        "certifications": [],
    }
    findings = fabrication_check(clean, profile)
    if findings:
        raise ValueError(f"clean content flagged falsely: {findings}")

    tainted = {**clean,
        "summary": "10 years experience. Cut time 95%. Managed team of 12.",
        "skills": {"core_competencies": ["Kubernetes"],
                   "tools_platforms": ["Marketo"], "additional": []},
        "education": [{"degree": "MBA", "major": "Bus", "school": "Stanford", "year": 2020}],
    }
    findings = fabrication_check(tainted, profile)
    if len(findings) < 4:
        raise ValueError(f"tainted content under-flagged: only {len(findings)} findings: {findings}")

    return f"fabrication check: clean=0, tainted={len(findings)} findings"


def _check_filesystem():
    """We can write to the user-data outputs dir (or fall back to /tmp)."""
    candidates = [Path("/mnt/user-data/outputs"), Path("/tmp")]
    for c in candidates:
        try:
            c.mkdir(parents=True, exist_ok=True)
            test_file = c / ".fats_healthcheck"
            test_file.write_text("ok")
            test_file.unlink()
            return f"writable: {c}"
        except Exception:
            continue
    raise RuntimeError("no writable filesystem location found")


def _check_role_proposal_families():
    """propose_roles produces output for known title families."""
    from scripts.profile import new_profile, propose_roles

    test_cases = [
        ("Senior Software Engineer", 8, "senior"),
        ("Marketing Manager", 6, "manager"),
        ("Product Manager", 5, "senior"),
        ("Data Scientist", 4, "mid"),
    ]
    for title, years, expected_seniority in test_cases:
        p = new_profile("X")
        p["experience"] = [{"title": title, "company": "Y", "current": True,
                            "start": "2019-01"}]
        p["years_experience_total"] = years
        p["inferred_seniority"] = expected_seniority
        roles = propose_roles(p)
        if not roles.get("focused"):
            raise ValueError(f"no focused roles for {title}")
    return f"role proposal ok across {len(test_cases)} title families"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

CHECKS = [
    ("imports", "Module imports", _check_imports),
    ("schemas", "Schema and asset files", _check_schema_files),
    ("seed", "Company seed list", _check_company_seed),
    ("filesystem", "File system writable", _check_filesystem),
    ("profile", "Profile lifecycle (build → validate → save → load)", _check_profile_lifecycle),
    ("ats_parsers", "ATS feed parsers (5 ATSes)", _check_ats_parsers),
    ("dedupe_score", "Dedupe → score → CSV pipeline", _check_dedupe_and_scoring),
    ("ghost", "Ghost-job detection", _check_ghost_detection),
    ("role_proposal", "Role proposal across job families", _check_role_proposal_families),
    ("fonts", "Bundled OFL fonts (EB Garamond, Carlito)", _check_bundled_fonts),
    ("resume_render", "Resume rendering — .docx (3 templates)", _check_resume_rendering),
    ("pdf", "Resume rendering — .pdf (3 templates, reportlab)", _check_pdf_rendering),
    ("fabrication", "Fabrication check (clean + tainted)", _check_fabrication_check),
]


def run_healthcheck() -> dict:
    """Run all checks and return a structured report."""
    reporter = _Reporter()
    for check_id, name, fn in CHECKS:
        _check(reporter, check_id, name, fn)
    return reporter.summary()


def format_report(report: dict) -> str:
    """Render a report as a human-readable string for chat output."""
    icon = {"pass": "✓", "fail": "✗", "warn": "!"}
    verdict_line = {
        "ok": "✅ All systems go. FATS is ready.",
        "degraded": "⚠️ Mostly green — see the warnings below. Safe to proceed.",
        "failed": "❌ Something's broken. Check the failed items before running a hunt.",
    }[report["summary"]]
    lines = [
        "**FATS health check**",
        "",
        verdict_line,
        f"Passed: {report['passed']}  ·  Failed: {report['failed']}  ·  Warnings: {report['warnings']}",
        "",
    ]
    for c in report["checks"]:
        line = f"  {icon[c['status']]} {c['name']}"
        if c.get("detail"):
            line += f" — {c['detail']}"
        lines.append(line)
    return "\n".join(lines)


if __name__ == "__main__":
    # Make the script runnable from anywhere by ensuring scripts/ is importable
    here = Path(__file__).parent.parent
    if str(here) not in sys.path:
        sys.path.insert(0, str(here))
    report = run_healthcheck()
    print(format_report(report))
    sys.exit(0 if report["summary"] != "failed" else 1)
