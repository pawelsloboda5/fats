"""FATS profile construction and validation.

Stage 1 uses this module to merge everything the user has provided (resumes,
LinkedIn text, portfolio content, pasted text) into a single canonical JSON
profile that every other stage reads from.

The LLM (Claude, running the skill) does the hard extraction work — reading
PDFs, pulling fields out of unstructured text, resolving conflicts. This
module provides the deterministic scaffolding: schema validation, merging
rules, evidence-ledger maintenance, and the "propose_roles" heuristic for
Stage 2.

Usage:
    from scripts.profile import (
        new_profile, validate_profile, save_profile, load_profile,
        add_source_doc, add_evidence, propose_roles,
    )
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Construction and I/O
# ---------------------------------------------------------------------------

def new_profile(name: str) -> dict:
    """Return a blank profile skeleton. Caller fills in fields."""
    return {
        "schema_version": "1.0",
        "name": name,
        "contact": {
            "email": None, "phone": None, "city": None, "state_region": None,
            "country": None, "linkedin_url": None, "portfolio_url": None,
            "github_url": None, "other_urls": [],
        },
        "headline": None,
        "summary": None,
        "years_experience_total": None,
        "inferred_seniority": None,
        "experience": [],
        "education": [],
        "certifications": [],
        "skills": {
            "technical": [], "tools": [], "soft": [],
            "languages": [], "domains": [],
        },
        "projects": [],
        "publications_or_talks": [],
        "clearances_or_licenses": [],
        "preferences_hints": {
            "roles_mentioned": [], "industries_mentioned": [],
            "locations_mentioned": [], "salary_mentioned": None,
            "remote_mentioned": None,
        },
        "target_roles": [],
        "job_preferences": {
            "locations": [], "remote_preference": "hybrid_or_remote",
            "seniority_range": [], "accept_relocation": False,
            "salary_floor": None,
        },
        "resume_template": "clean_modern",
        "source_docs": [],
        "evidence": {
            "skills_evidence": {},
            "tools_evidence": {},
            "claims_evidence": {},
        },
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


def validate_profile(profile: dict, schema_path: str | Path) -> list[str]:
    """Validate a profile against the JSON schema.

    Returns a list of error strings. Empty list means valid.

    Doesn't use jsonschema package (may not be in the sandbox). Does a
    targeted check of the required top-level fields and key substructures.
    """
    errors = []
    required_top = ["name", "contact", "experience", "skills", "evidence", "last_updated"]
    for field in required_top:
        if field not in profile:
            errors.append(f"missing required field: {field}")

    if "contact" in profile and not isinstance(profile["contact"], dict):
        errors.append("contact must be an object")

    if "experience" in profile:
        if not isinstance(profile["experience"], list):
            errors.append("experience must be an array")
        else:
            for i, exp in enumerate(profile["experience"]):
                if not isinstance(exp, dict):
                    errors.append(f"experience[{i}] must be an object")
                    continue
                for req in ("title", "company"):
                    if req not in exp:
                        errors.append(f"experience[{i}] missing {req}")

    if "inferred_seniority" in profile and profile["inferred_seniority"] is not None:
        allowed = {"entry", "junior", "mid", "senior", "staff", "principal",
                   "manager", "director", "vp", "c-level"}
        if profile["inferred_seniority"] not in allowed:
            errors.append(
                f"inferred_seniority must be one of {sorted(allowed)}"
            )

    if "resume_template" in profile:
        if profile["resume_template"] not in {"clean_modern", "harvard", "mirror_user"}:
            errors.append("resume_template must be clean_modern|harvard|mirror_user")

    return errors


def save_profile(profile: dict, out_path: str | Path) -> Path:
    """Write profile to disk with pretty-print. Updates last_updated."""
    profile["last_updated"] = datetime.now(timezone.utc).isoformat()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(profile, indent=2))
    return out_path


def load_profile(path: str | Path) -> dict:
    return json.loads(Path(path).read_text())


# ---------------------------------------------------------------------------
# Source docs & evidence
# ---------------------------------------------------------------------------

def _hash_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:12]


def add_source_doc(profile: dict, doc_type: str,
                   path_or_url: str | None,
                   content: str | None = None) -> str:
    """Register a source doc. Returns the doc's ID (used in evidence pointers).

    doc_type: resume_pdf | resume_docx | linkedin | github | portfolio |
              user_pasted | cover_letter | other
    """
    # Generate a stable, readable ID.
    base = doc_type
    if path_or_url:
        base += "_" + Path(path_or_url).stem if path_or_url.startswith("/") else "_" + _hash_text(path_or_url)[:6]
    elif content:
        base += "_" + _hash_text(content)[:6]
    else:
        base += "_" + _hash_text(str(datetime.now()))[:6]

    doc_id = base
    # Avoid collisions
    existing_ids = {d["id"] for d in profile.get("source_docs", [])}
    i = 2
    while doc_id in existing_ids:
        doc_id = f"{base}_{i}"
        i += 1

    profile["source_docs"].append({
        "id": doc_id,
        "type": doc_type,
        "path_or_url": path_or_url,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "fingerprint": _hash_text(content) if content else None,
    })
    return doc_id


def add_evidence(profile: dict, category: str, key: str,
                 source_doc_id: str, location_hint: str) -> None:
    """Record that `key` (a skill, tool, or claim) traces back to a source.

    category: "skills_evidence" | "tools_evidence" | "claims_evidence"
    """
    assert category in ("skills_evidence", "tools_evidence", "claims_evidence")
    bucket = profile["evidence"].setdefault(category, {})
    ledger = bucket.setdefault(key, [])
    pointer = f"{source_doc_id}:{location_hint}"
    if pointer not in ledger:
        ledger.append(pointer)


def has_evidence(profile: dict, skill_or_tool: str) -> bool:
    """Check if a given skill/tool has traceable evidence. Used by Stage 6."""
    needle = skill_or_tool.strip().lower()
    # Check skills_evidence, tools_evidence, and raw experience
    for cat in ("skills_evidence", "tools_evidence"):
        for key in profile.get("evidence", {}).get(cat, {}).keys():
            if key.strip().lower() == needle:
                return True
    # Also scan experience[].technologies and bullets for mentions — looser check
    for exp in profile.get("experience", []):
        for tech in exp.get("technologies", []) or []:
            if tech.strip().lower() == needle:
                return True
        for bullet in exp.get("bullets", []) or []:
            if needle in bullet.lower():
                return True
    # Also scan skills structure
    for bucket in ("technical", "tools", "soft", "languages", "domains"):
        for s in profile.get("skills", {}).get(bucket, []) or []:
            if s.strip().lower() == needle:
                return True
    return False


# ---------------------------------------------------------------------------
# Inference helpers
# ---------------------------------------------------------------------------

def compute_years_experience(experience: list[dict]) -> float | None:
    """Sum non-overlapping role durations. Rounds to nearest 0.5."""
    # Parse periods → list of (start_month_int, end_month_int)
    periods = []
    for exp in experience:
        start = _parse_month(exp.get("start"))
        end = _parse_month(exp.get("end"))
        if start is None:
            continue
        if end is None or exp.get("current"):
            # Use current month
            now = datetime.now()
            end = now.year * 12 + (now.month - 1)
        if end < start:
            continue
        periods.append((start, end))

    if not periods:
        return None

    # Merge overlapping intervals
    periods.sort()
    merged = [list(periods[0])]
    for s, e in periods[1:]:
        if s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])

    total_months = sum(e - s + 1 for s, e in merged)
    years = total_months / 12.0
    return round(years * 2) / 2  # nearest 0.5


def _parse_month(val) -> int | None:
    """Parse 'YYYY-MM' or 'YYYY' or ISO date to month-count integer."""
    if val is None or val == "" or (isinstance(val, str) and val.lower() in {"present", "current"}):
        return None
    if isinstance(val, str):
        # Try YYYY-MM first
        m = re.match(r"^(\d{4})-(\d{1,2})", val)
        if m:
            y, mo = int(m.group(1)), int(m.group(2))
            return y * 12 + (mo - 1)
        # Try YYYY alone
        m = re.match(r"^(\d{4})$", val)
        if m:
            return int(m.group(1)) * 12
    return None


def infer_seniority(profile: dict) -> str:
    """Guess seniority from years + most recent title. Conservative, not flattering."""
    years = profile.get("years_experience_total") or 0
    latest_title = ""
    for exp in profile.get("experience", []):
        if exp.get("current"):
            latest_title = (exp.get("title") or "").lower()
            break
    if not latest_title and profile.get("experience"):
        latest_title = (profile["experience"][0].get("title") or "").lower()

    # Title-based override (use word boundaries so e.g. "cto" doesn't hit "direCTOr")
    def _has_word(title: str, word: str) -> bool:
        return re.search(rf"\b{re.escape(word)}\b", title) is not None

    if any(_has_word(latest_title, w) for w in ("cto", "cfo", "ceo", "coo", "cmo")) \
       or "chief " in latest_title:
        return "c-level"
    if _has_word(latest_title, "vp") or "vice president" in latest_title:
        return "vp"
    if _has_word(latest_title, "director"):
        return "director"
    if (any(_has_word(latest_title, w) for w in ("manager", "lead"))
            or "head of" in latest_title) and years >= 5:
        return "manager"
    if _has_word(latest_title, "principal"):
        return "principal"
    if _has_word(latest_title, "staff"):
        return "staff"
    if _has_word(latest_title, "senior") or _has_word(latest_title, "sr"):
        return "senior"

    # Fallback to years alone
    if years >= 10:
        return "senior"
    if years >= 6:
        return "senior"
    if years >= 3:
        return "mid"
    if years >= 1:
        return "junior"
    return "entry"


# ---------------------------------------------------------------------------
# Stage 2: role proposal heuristic
# ---------------------------------------------------------------------------

# Map most recent title family → focused + adjacent role candidates.
# LLM refines these at runtime; this provides a reasonable first pass.
_ROLE_FAMILIES = {
    # Engineering
    "software_engineer": {
        "keywords": ["software engineer", "swe", "developer", "backend", "frontend", "fullstack", "full stack", "full-stack"],
        "focused": ["{level} Software Engineer", "{level} Backend Engineer", "{level} Full-Stack Engineer"],
        "adjacent": ["Platform Engineer", "Developer Experience Engineer", "Solutions Engineer", "Infrastructure Engineer"],
    },
    "data_scientist": {
        "keywords": ["data scientist", "machine learning engineer", "ml engineer", "ml scientist"],
        "focused": ["{level} Data Scientist", "{level} Machine Learning Engineer", "{level} Applied Scientist"],
        "adjacent": ["Research Engineer", "Analytics Engineer", "Decision Scientist", "ML Platform Engineer"],
    },
    "data_engineer": {
        "keywords": ["data engineer", "analytics engineer", "data platform"],
        "focused": ["{level} Data Engineer", "{level} Analytics Engineer", "{level} Data Platform Engineer"],
        "adjacent": ["Software Engineer, Data", "BI Engineer", "ML Engineer"],
    },
    "product_manager": {
        "keywords": ["product manager", "pm ", "product owner", "product lead"],
        "focused": ["{level} Product Manager", "{level} Technical Product Manager", "{level} Growth Product Manager"],
        "adjacent": ["Principal PM", "Product Operations Manager", "Product Marketing Manager"],
    },
    "designer": {
        "keywords": ["designer", "ux ", "ui ", "product design"],
        "focused": ["{level} Product Designer", "{level} UX Designer", "{level} Design Lead"],
        "adjacent": ["Design Systems Lead", "UX Researcher", "Brand Designer"],
    },
    # Marketing
    "marketing": {
        "keywords": ["marketing", "demand gen", "growth marketing", "brand"],
        "focused": ["{level} Marketing Manager", "{level} Growth Marketing Manager", "{level} Demand Gen Manager"],
        "adjacent": ["Product Marketing Manager", "Marketing Operations Manager", "Content Strategy Lead", "SEO Manager"],
    },
    "sales": {
        "keywords": ["account executive", "ae ", "sdr", "bdr", "sales rep", "account manager"],
        "focused": ["{level} Account Executive", "Enterprise Account Executive", "{level} Sales Manager"],
        "adjacent": ["Solutions Consultant", "Sales Engineer", "Customer Success Manager", "Partnerships Manager"],
    },
    "cs": {
        "keywords": ["customer success", "csm", "implementation"],
        "focused": ["{level} Customer Success Manager", "Enterprise CSM", "{level} Implementation Manager"],
        "adjacent": ["Solutions Consultant", "Account Manager", "Technical Account Manager"],
    },
    "ops": {
        "keywords": ["operations", "program manager", "chief of staff"],
        "focused": ["{level} Operations Manager", "{level} Program Manager", "{level} Business Operations"],
        "adjacent": ["Chief of Staff", "Strategy Manager", "Finance Business Partner"],
    },
    "finance": {
        "keywords": ["financial analyst", "fp&a", "controller", "accountant"],
        "focused": ["{level} Financial Analyst", "{level} FP&A Manager", "{level} Accountant"],
        "adjacent": ["Business Operations", "Revenue Operations", "Strategic Finance"],
    },
    "hr": {
        "keywords": ["recruiter", "talent", "people ops", "hr ", "human resources"],
        "focused": ["{level} Recruiter", "{level} People Operations Manager", "{level} Talent Partner"],
        "adjacent": ["HR Business Partner", "Talent Operations", "Compensation Analyst"],
    },
}


def _level_prefix(seniority: str) -> str:
    return {
        "entry": "", "junior": "", "mid": "", "senior": "Senior",
        "staff": "Staff", "principal": "Principal",
        "manager": "Senior", "director": "Director of",
        "vp": "VP of", "c-level": "Chief",
    }.get(seniority, "Senior")


def propose_roles(profile: dict) -> dict:
    """Return a dict with `focused`, `adjacent`, and `stretch` role lists.

    Heuristic first pass. The LLM refines, prunes, and adds market-aware
    variants in Stage 2.
    """
    latest_title = ""
    for exp in profile.get("experience", []):
        if exp.get("current"):
            latest_title = (exp.get("title") or "").lower()
            break
    if not latest_title and profile.get("experience"):
        latest_title = (profile["experience"][0].get("title") or "").lower()

    seniority = profile.get("inferred_seniority") or infer_seniority(profile)
    level_word = _level_prefix(seniority)

    # Pick the best-matching family
    family = None
    for fam_name, spec in _ROLE_FAMILIES.items():
        if any(kw in latest_title for kw in spec["keywords"]):
            family = spec
            break

    out = {"focused": [], "adjacent": [], "stretch": []}
    if family is None:
        # Unknown family — fall back to the user's title variations
        base_title = latest_title.title() if latest_title else "Specialist"
        out["focused"] = [
            base_title,
            f"Senior {base_title}" if "senior" not in base_title.lower() else base_title,
            f"Lead {base_title}",
        ]
        return out

    def _fmt(t):
        t = t.replace("{level}", level_word).strip()
        return re.sub(r"\s+", " ", t)

    out["focused"] = [_fmt(t) for t in family["focused"]][:3]
    out["adjacent"] = [_fmt(t) for t in family["adjacent"]][:3]

    # Stretch = one level up if it's different
    if seniority == "senior":
        # Suggest Staff/Manager stretch for relevant families
        if family is _ROLE_FAMILIES["software_engineer"]:
            out["stretch"].append("Staff Software Engineer")
        elif "marketing" in (latest_title or ""):
            out["stretch"].append("Director of Marketing")

    # Dedupe while preserving order
    for k in out:
        out[k] = list(dict.fromkeys(out[k]))
    return out


# ---------------------------------------------------------------------------
# Profile merge (for users who upload multiple resumes)
# ---------------------------------------------------------------------------

def merge_profiles(primary: dict, secondary: dict) -> dict:
    """Merge secondary into primary. Primary (newer) wins on conflicts.

    The LLM is expected to do most of the merging during Stage 1 by
    reading multiple sources and producing a unified draft. This helper
    is for programmatic top-offs.
    """
    out = dict(primary)

    # Union skills
    for bucket in ("technical", "tools", "soft", "languages", "domains"):
        combined = (out.get("skills", {}).get(bucket, []) or []) + \
                   (secondary.get("skills", {}).get(bucket, []) or [])
        # dedupe case-insensitive, preserve first-seen casing
        seen, deduped = set(), []
        for s in combined:
            key = s.strip().lower()
            if key and key not in seen:
                seen.add(key)
                deduped.append(s)
        out.setdefault("skills", {})[bucket] = deduped

    # Union certifications, education, experience (primary first, dedupe by key)
    def _union(list_key, dedupe_key):
        a = out.get(list_key, []) or []
        b = secondary.get(list_key, []) or []
        seen = {_dedupe_key(item, dedupe_key) for item in a if _dedupe_key(item, dedupe_key)}
        for item in b:
            k = _dedupe_key(item, dedupe_key)
            if k and k not in seen:
                a.append(item)
                seen.add(k)
        out[list_key] = a

    _union("experience", ["title", "company"])
    _union("education", ["school", "degree"])
    _union("certifications", ["name"])
    _union("projects", ["name"])

    # Union source docs
    out["source_docs"] = (out.get("source_docs", []) or []) + \
                         (secondary.get("source_docs", []) or [])

    # Merge evidence ledgers
    for cat in ("skills_evidence", "tools_evidence", "claims_evidence"):
        a = out.setdefault("evidence", {}).setdefault(cat, {})
        b = secondary.get("evidence", {}).get(cat, {})
        for key, pointers in b.items():
            a.setdefault(key, [])
            for p in pointers:
                if p not in a[key]:
                    a[key].append(p)

    return out


def _dedupe_key(item: dict, keys: list[str]) -> str:
    return "|".join((item.get(k) or "").strip().lower() for k in keys)
