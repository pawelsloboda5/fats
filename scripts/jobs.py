"""Job ranking, deduplication, ghost-job flagging, salary inference, and CSV output.

Stage 5 uses this to turn raw hunt results (from Stage 4) into the ranked
CSV the user actually works from.

The LLM handles the genuinely-judgmental parts (keyword extraction, fit
rationale, salary inference) while this module handles the deterministic
scaffolding (merging duplicates, computing scores from inputs, writing
well-formed CSVs).
"""

from __future__ import annotations

import csv
import re
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants and small helpers
# ---------------------------------------------------------------------------

SENIORITY_ORDER = ["entry", "junior", "mid", "senior", "staff", "principal",
                   "manager", "director", "vp", "c-level"]

_SENIORITY_WORDS = {
    "entry": ["entry", "entry-level", "associate i"],
    "junior": ["junior", "jr.", "jr ", " i ", " ii "],
    "mid": [" iii ", "mid-level"],
    "senior": ["senior", "sr.", "sr "],
    "staff": ["staff"],
    "principal": ["principal"],
    "manager": ["manager", "head of", "lead "],
    "director": ["director", "head of "],
    "vp": ["vp", "vice president"],
    "c-level": ["chief", "cto", "cfo", "ceo", "coo", "cmo"],
}

_STRIP_SENIORITY = re.compile(
    r"\b(senior|sr\.?|junior|jr\.?|staff|principal|lead|head of|associate)\b",
    flags=re.I,
)

_COMPANY_ALIASES = {
    "meta": ["facebook", "meta platforms"],
    "alphabet": ["google"],
    "x": ["twitter"],
    "block": ["square"],
}


def _normalize_company(name: str) -> str:
    s = (name or "").strip().lower()
    s = re.sub(r"[^a-z0-9\s]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    for canonical, aliases in _COMPANY_ALIASES.items():
        if s == canonical or s in aliases:
            return canonical
    return s


def _normalize_title(title: str) -> str:
    s = (title or "").strip().lower()
    s = _STRIP_SENIORITY.sub("", s)
    s = re.sub(r"[^a-z0-9\s]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _normalize_city(loc_norm: dict | None) -> str:
    if not loc_norm:
        return ""
    if loc_norm.get("is_remote"):
        return f"remote:{(loc_norm.get('remote_region') or '').lower()}"
    return (loc_norm.get("city") or "").strip().lower()


def _detect_role_seniority(title: str, jd: str) -> str:
    t = (title or "").lower() + " " + (jd or "")[:500].lower()
    # Search in reverse seniority order so "senior manager" doesn't match "manager"
    # before matching "senior"
    for level in ["c-level", "vp", "director", "principal", "staff", "senior",
                  "manager", "mid", "junior", "entry"]:
        for w in _SENIORITY_WORDS[level]:
            if w.strip() and w in t:
                return level
    return "mid"


# ---------------------------------------------------------------------------
# Dedupe
# ---------------------------------------------------------------------------

SOURCE_PRIORITY = ["user_list", "greenhouse", "lever", "ashby", "workable",
                   "smartrecruiters", "google_jobs"]


def dedupe(raw_jobs: list[dict]) -> list[dict]:
    """Collapse duplicate postings. Returns a new list of merged records.

    Each merged record has:
      primary_url: the URL from the highest-priority source
      duplicate_urls: list of all other URLs
    """
    buckets: dict[str, list[dict]] = {}
    for job in raw_jobs:
        key = "|".join([
            _normalize_company(job.get("company", "")),
            _normalize_title(job.get("title", "")),
            _normalize_city(job.get("location_normalized")),
        ])
        buckets.setdefault(key, []).append(job)

    merged = []
    for key, group in buckets.items():
        # Sort by source priority
        group.sort(key=lambda j: SOURCE_PRIORITY.index(j["source_board"])
                   if j["source_board"] in SOURCE_PRIORITY else 99)
        primary = dict(group[0])  # shallow copy
        primary["primary_url"] = primary.get("source_url", "")
        primary["duplicate_urls"] = [j["source_url"] for j in group[1:] if j.get("source_url")]

        # Take the longest JD (often the most complete)
        longest_jd = primary.get("jd_text", "") or ""
        for j in group[1:]:
            if len(j.get("jd_text", "") or "") > len(longest_jd):
                longest_jd = j["jd_text"]
        primary["jd_text"] = longest_jd

        # Take the widest listed salary range if multiple agree
        salaries = [j["salary_listed"] for j in group if j.get("salary_listed")]
        if salaries:
            mins = [s["min"] for s in salaries if s.get("min") is not None]
            maxs = [s["max"] for s in salaries if s.get("max") is not None]
            if mins and maxs:
                primary["salary_listed"] = {
                    "min": min(mins), "max": max(maxs),
                    "currency": salaries[0].get("currency", "USD"),
                    "period": salaries[0].get("period", "year"),
                }

        merged.append(primary)
    return merged


# ---------------------------------------------------------------------------
# Fit scoring
# ---------------------------------------------------------------------------

def score_skills(jd_keywords: list[str], profile: dict) -> tuple[int, list[str], list[str]]:
    """Returns (score 0-100, matched, missing).

    Matched list contains keywords found in profile evidence.
    Missing list contains JD keywords NOT in profile evidence.
    """
    # Import here to avoid circular ref; profile.has_evidence is the source of truth
    from scripts.profile import has_evidence

    if not jd_keywords:
        return (75, [], [])  # Neutral when JD has no clear keyword set

    matched, missing = [], []
    for kw in jd_keywords:
        if has_evidence(profile, kw):
            matched.append(kw)
        else:
            missing.append(kw)

    n = max(len(jd_keywords), 1)
    score = int(100 * len(matched) / n)
    return (min(score, 100), matched, missing)


def score_experience_level(role_seniority: str, user_seniority: str) -> int:
    """Score the alignment of role's required seniority vs user's inferred seniority."""
    try:
        a = SENIORITY_ORDER.index(role_seniority)
        b = SENIORITY_ORDER.index(user_seniority)
    except ValueError:
        return 75
    diff = abs(a - b)
    return {0: 100, 1: 80, 2: 50, 3: 30}.get(diff, 20)


def score_industry(job_industry: str, user_industries: list[str]) -> int:
    """Match user's industry footprint against the company's industry."""
    if not user_industries:
        return 60
    job = (job_industry or "").lower()
    user = [i.lower() for i in user_industries]
    if any(u == job for u in user):
        return 100
    # Adjacent: share a substring or family
    adjacent_families = [
        ["b2b_saas", "devtools", "infra", "data", "martech", "sales", "hr", "security"],
        ["consumer_tech", "media", "media_streaming"],
        ["fintech", "fintech_traditional", "fintech_crypto"],
        ["healthtech", "biotech_saas"],
        ["ai_core", "ai_infra", "ai_consumer", "ai_devtools"],
    ]
    for fam in adjacent_families:
        if any(f in job for f in fam) and any(any(f in u for f in fam) for u in user):
            return 85
    # Same high-level category (tech vs non-tech)
    tech_markers = ["saas", "tech", "software", "ai", "data"]
    if any(m in job for m in tech_markers) and any(any(m in u for m in tech_markers) for u in user):
        return 65
    return 40


def score_location_comp(job: dict, profile: dict, settings: dict) -> int:
    """Average of location sub-score and comp sub-score."""
    # Location
    loc = job.get("location_normalized") or {}
    prefs = profile.get("job_preferences") or {}
    user_locations = [l.lower() for l in prefs.get("locations", [])]
    remote_pref = prefs.get("remote_preference", "hybrid_or_remote")
    is_remote = loc.get("is_remote", False)
    city = (loc.get("city") or "").lower()

    loc_score = 40
    if is_remote:
        if remote_pref in {"remote_only", "hybrid_or_remote"}:
            loc_score = 100
        elif remote_pref == "hybrid_ok":
            loc_score = 60
        else:
            loc_score = 10
    else:
        if any(city in l or l in city for l in user_locations if l):
            loc_score = 100
        elif user_locations:
            loc_score = 40

    # Comp
    floor = settings.get("salary_floor")
    salary = job.get("salary_listed")
    inferred = job.get("salary_min_inferred")
    comp_score = 75
    if floor:
        target = None
        if salary and salary.get("max") is not None:
            target = salary["max"]
        elif salary and salary.get("min") is not None:
            target = salary["min"]
        elif inferred:
            target = inferred
        if target is None:
            comp_score = 75
        elif target >= floor:
            comp_score = 100
        elif target >= 0.9 * floor:
            comp_score = 80
        elif target >= 0.8 * floor:
            comp_score = 50
        else:
            comp_score = 20
    return (loc_score + comp_score) // 2


def score_fit(job: dict, profile: dict, settings: dict,
              jd_keywords: list[str], industries: list[str]) -> dict:
    """Compute full fit score and breakdown. `jd_keywords` and `industries`
    are typically produced by the LLM (Stage 5 orchestrator) and passed in.
    """
    role_seniority = _detect_role_seniority(job.get("title", ""), job.get("jd_text", ""))
    user_seniority = profile.get("inferred_seniority") or "mid"

    skills_score, matched, missing = score_skills(jd_keywords, profile)
    experience_score = score_experience_level(role_seniority, user_seniority)
    industry_score = score_industry(job.get("company_industry", ""), industries)
    location_comp_score = score_location_comp(job, profile, settings)

    total = round(
        0.40 * skills_score +
        0.25 * experience_score +
        0.15 * industry_score +
        0.20 * location_comp_score
    )
    return {
        "total": int(total),
        "skills": skills_score,
        "experience": experience_score,
        "industry": industry_score,
        "location_comp": location_comp_score,
        "matched_keywords": matched,
        "missing_keywords": missing,
        "detected_role_seniority": role_seniority,
    }


# ---------------------------------------------------------------------------
# Ghost job detection
# ---------------------------------------------------------------------------

def ghost_risk(job: dict, prior_hunt_history: list[dict] | None = None) -> dict:
    """Return {risk: low|medium|high, points: int, reason: str}."""
    points = 0
    reasons = []

    jd = job.get("jd_text", "") or ""
    jd_len = len(jd)
    hours = job.get("hours_since_posted")
    salary = job.get("salary_listed")
    title = (job.get("title") or "").lower()

    # Content flags
    if jd_len > 0 and jd_len < 400:
        points += 3
        reasons.append(f"generic boilerplate JD ({jd_len} chars)")
    low_jd = jd.lower()
    if any(p in low_jd for p in ["join our talent network", "talent community",
                                 "always hiring", "always interested",
                                 "submit your resume for future"]):
        points += 3
        reasons.append("talent-network language")
    if jd_len > 0 and not re.search(
        r"(\d+\s*(years?|yrs?)|experience with|required|must have|proficiency)",
        low_jd,
    ):
        points += 2
        reasons.append("no specific requirements")
    if jd_len > 0 and not re.search(r"(team|product|project|customer)", low_jd):
        points += 2
        reasons.append("no team/product mentioned")

    # Temporal flags
    if hours is not None:
        if hours > 24 * 30:
            points += 3
            reasons.append(f"posted {hours // 24} days ago")
        elif hours > 24 * 14:
            points += 2
            reasons.append(f"posted {hours // 24} days ago")

    # Salary signals
    if salary is None and hours is None:
        points += 1

    # Source flag: only from Google Jobs / no ATS confirmation
    if job.get("source_board") == "google_jobs" and not job.get("duplicate_urls"):
        points += 1

    # Positive signals (subtract)
    if len(job.get("duplicate_urls") or []) >= 2:
        points -= 2
    if salary and salary.get("min") and salary.get("max"):
        points -= 2

    # Staffing agency hint
    company_lower = (job.get("company") or "").lower()
    if any(w in company_lower for w in ["staffing", "recruiters", "recruiting",
                                         "talent partners", "search firm",
                                         "placement"]):
        points += 1
        reasons.append("staffing agency")

    # Repeat-post flag against prior hunts
    if prior_hunt_history:
        key_now = (_normalize_company(job.get("company", "")),
                   _normalize_title(title),
                   _normalize_city(job.get("location_normalized")))
        for prior in prior_hunt_history:
            key_prior = (_normalize_company(prior.get("company", "")),
                         _normalize_title(prior.get("title", "")),
                         _normalize_city(prior.get("location_normalized")))
            if key_now == key_prior:
                prior_hours = prior.get("hours_since_posted")
                if prior_hours is not None and prior_hours > 24 * 30:
                    points += 4
                    reasons.append("same posting seen in prior hunts 30+ days ago")
                    break

    # Classify
    if points <= 2:
        risk = "low"
    elif points <= 5:
        risk = "medium"
    else:
        risk = "high"

    reason_str = "; ".join(reasons) if risk != "low" else ""
    return {"risk": risk, "points": points, "reason": reason_str}


# ---------------------------------------------------------------------------
# Filtering (applied during Stage 4)
# ---------------------------------------------------------------------------

def passes_filters(job: dict, profile: dict, settings: dict) -> bool:
    """Return True if job survives hard filters. Used during Stage 4."""
    # Freshness
    freshness = settings.get("freshness_hours", 24)
    hours = job.get("hours_since_posted")
    if hours is not None and hours > freshness:
        return False

    # Excluded companies
    for ex in settings.get("exclude_companies", []):
        if _normalize_company(ex) == _normalize_company(job.get("company", "")):
            return False

    # Excluded keywords
    jd = (job.get("jd_text") or "").lower()
    for kw in settings.get("exclude_keywords", []):
        if kw.lower() in jd:
            return False

    # Salary floor (drop only if listed and below)
    floor = settings.get("salary_floor")
    salary = job.get("salary_listed")
    if floor and salary:
        top = salary.get("max") or salary.get("min")
        if top is not None and top < floor:
            return False

    # Location: if user has strict locations and job isn't remote and not in those cities
    prefs = profile.get("job_preferences") or {}
    user_locations = [l.lower() for l in prefs.get("locations", [])]
    remote_pref = prefs.get("remote_preference", "hybrid_or_remote")
    loc = job.get("location_normalized") or {}
    is_remote = loc.get("is_remote", False)

    if remote_pref == "remote_only" and not is_remote:
        return False
    if remote_pref == "onsite_only" and is_remote:
        return False
    if not is_remote and user_locations:
        city = (loc.get("city") or "").lower()
        if not any(city and (city in l or l in city) for l in user_locations):
            return False

    return True


# ---------------------------------------------------------------------------
# CSV output
# ---------------------------------------------------------------------------

CSV_FIELDS = [
    "rank", "fit_score",
    "fit_breakdown_skills", "fit_breakdown_experience",
    "fit_breakdown_industry", "fit_breakdown_location_comp",
    "job_title", "company", "company_size", "company_industry",
    "location", "remote_type", "seniority_level", "employment_type",
    "salary_min", "salary_max", "salary_source", "salary_confidence", "salary_basis",
    "posted_date", "hours_since_posted",
    "ghost_job_risk", "ghost_job_reason",
    "primary_url", "duplicate_urls", "source_board", "ats_type",
    "required_keywords", "matched_keywords", "missing_keywords",
    "why_it_matches", "full_jd", "apply_method",
]


def _remote_type(loc_norm: dict | None, jd: str) -> str:
    if loc_norm and loc_norm.get("is_remote"):
        return "remote"
    jd_low = (jd or "").lower()
    if "hybrid" in jd_low:
        return "hybrid"
    if "on-site" in jd_low or "onsite" in jd_low or "in office" in jd_low:
        return "onsite"
    return "unknown"


def _flatten_for_csv(ranked_job: dict) -> dict:
    """Turn an enriched job record into the flat row used in CSV."""
    sal = ranked_job.get("salary_listed") or {}
    inferred = ranked_job.get("salary_inferred") or {}
    if sal.get("min") is not None or sal.get("max") is not None:
        salary_min, salary_max = sal.get("min"), sal.get("max")
        salary_source = "listed"
        salary_confidence = "high"
        salary_basis = ""
    elif inferred:
        salary_min, salary_max = inferred.get("min_usd"), inferred.get("max_usd")
        salary_source = "inferred"
        salary_confidence = inferred.get("confidence", "medium")
        salary_basis = inferred.get("basis", "")
    else:
        salary_min = salary_max = None
        salary_source = "unknown"
        salary_confidence = "low"
        salary_basis = ""

    fit = ranked_job.get("fit", {})
    ghost = ranked_job.get("ghost", {})
    apply_url = ranked_job.get("apply_url") or ranked_job.get("primary_url", "")
    apply_method = "direct" if ranked_job.get("ats_type") != "unknown" else "unknown"
    if "linkedin.com" in (apply_url or ""):
        apply_method = "via_linkedin"
    elif "indeed.com" in (apply_url or ""):
        apply_method = "via_indeed"
    elif ranked_job.get("source_board") == "google_jobs":
        apply_method = "via_google_jobs"

    return {
        "rank": ranked_job.get("rank"),
        "fit_score": fit.get("total"),
        "fit_breakdown_skills": fit.get("skills"),
        "fit_breakdown_experience": fit.get("experience"),
        "fit_breakdown_industry": fit.get("industry"),
        "fit_breakdown_location_comp": fit.get("location_comp"),
        "job_title": ranked_job.get("title", ""),
        "company": ranked_job.get("company", ""),
        "company_size": ranked_job.get("company_size", "unknown"),
        "company_industry": ranked_job.get("company_industry", "unknown"),
        "location": ranked_job.get("location", ""),
        "remote_type": _remote_type(ranked_job.get("location_normalized"),
                                    ranked_job.get("jd_text", "")),
        "seniority_level": fit.get("detected_role_seniority", "unknown"),
        "employment_type": ranked_job.get("employment_type", "unknown"),
        "salary_min": salary_min,
        "salary_max": salary_max,
        "salary_source": salary_source,
        "salary_confidence": salary_confidence,
        "salary_basis": salary_basis,
        "posted_date": ranked_job.get("posted_date", ""),
        "hours_since_posted": ranked_job.get("hours_since_posted"),
        "ghost_job_risk": ghost.get("risk", "low"),
        "ghost_job_reason": ghost.get("reason", ""),
        "primary_url": ranked_job.get("primary_url", ""),
        "duplicate_urls": "|".join(ranked_job.get("duplicate_urls") or []),
        "source_board": ranked_job.get("source_board", ""),
        "ats_type": ranked_job.get("ats_type", "unknown"),
        "required_keywords": "|".join(ranked_job.get("required_keywords") or []),
        "matched_keywords": "|".join(fit.get("matched_keywords") or []),
        "missing_keywords": "|".join(fit.get("missing_keywords") or []),
        "why_it_matches": ranked_job.get("why_it_matches", ""),
        "full_jd": ranked_job.get("jd_text", ""),
        "apply_method": apply_method,
    }


def write_csv(ranked_jobs: list[dict], path: str | Path) -> Path:
    """Write ranked jobs to CSV. Ranks are 1-based and computed from fit_score."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Sort by fit_score desc; break ties by hours_since_posted asc (fresher first)
    ranked = sorted(
        ranked_jobs,
        key=lambda j: (-(j.get("fit", {}).get("total", 0)),
                       j.get("hours_since_posted") or 99999),
    )
    for i, job in enumerate(ranked, start=1):
        job["rank"] = i

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        for job in ranked:
            writer.writerow(_flatten_for_csv(job))
    return path


def write_summary_md(ranked_jobs: list[dict], path: str | Path, top_n: int = 10) -> Path:
    """Produce a human-readable markdown summary of the top N jobs."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ranked = sorted(ranked_jobs,
                    key=lambda j: -(j.get("fit", {}).get("total", 0)))[:top_n]

    lines = [f"# FATS — Top {min(top_n, len(ranked))} matches",
             f"Generated {datetime.now(timezone.utc).isoformat()}\n",
             "| # | Fit | Role | Company | Location | Salary | Posted |",
             "|---|-----|------|---------|----------|--------|--------|"]
    for i, j in enumerate(ranked, start=1):
        fit = j.get("fit", {}).get("total", "?")
        title = j.get("title", "")
        company = j.get("company", "")
        loc = j.get("location", "")
        sal = j.get("salary_listed")
        inf = j.get("salary_inferred")
        if sal and (sal.get("min") or sal.get("max")):
            sal_str = f"${(sal.get('min') or 0)//1000}K-${(sal.get('max') or 0)//1000}K"
        elif inf and inf.get("min_usd"):
            sal_str = f"${inf['min_usd']//1000}K-${inf['max_usd']//1000}K*"
        else:
            sal_str = "—"
        hours = j.get("hours_since_posted")
        hours_str = f"{hours}h ago" if hours is not None else "—"
        lines.append(f"| {i} | {fit} | {title} | {company} | {loc} | {sal_str} | {hours_str} |")
    lines.append("\n*Inferred salary (not listed).\n")
    path.write_text("\n".join(lines))
    return path


# ---------------------------------------------------------------------------
# Role aliases (used by the hunt for fuzzy title matching)
# ---------------------------------------------------------------------------

def role_aliases(title: str) -> list[str]:
    """Known-equivalent title phrasings. Extend as needed."""
    t = title.lower().strip()
    aliases = {t}

    # Seniority variants
    if "senior" in t:
        aliases.add(t.replace("senior", "sr.").strip())
        aliases.add(t.replace("senior", "sr").strip())
    if "software engineer" in t:
        aliases.update([t.replace("software engineer", v) for v in
                        ["software developer", "swe", "engineer"]])
    if "product manager" in t:
        aliases.add(t.replace("product manager", "product lead"))
    if "demand gen" in t:
        aliases.update([t.replace("demand gen", v) for v in
                        ["growth marketing", "performance marketing"]])
    if "marketing manager" in t:
        aliases.add(t.replace("marketing manager", "marketing lead"))
    return [a.strip() for a in aliases if a.strip()]


def title_matches_targets(posted_title: str, target_roles: list[dict]) -> bool:
    """Fuzzy check: does this posted title match any target role or alias?"""
    pt = posted_title.lower()
    for role in target_roles:
        for alias in role_aliases(role.get("title", "")):
            if alias and (alias in pt or pt in alias):
                return True
    return False
