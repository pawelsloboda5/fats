"""ATS feed parsers.

Claude fetches the feed URLs with `web_fetch` and passes the parsed JSON
(or raw text) to these functions, which normalize each ATS's idiosyncratic
schema into the common FATS job record.

These are PURE FUNCTIONS — no network, no side effects. Fetching is Claude's
job via the web_fetch tool.

Common output schema (see references/csv-schema.md and references/stage-4-hunt.md):

    {
        "source_board": "greenhouse" | "lever" | "ashby" | "workable" | "smartrecruiters",
        "source_url": str,
        "fetched_at": ISO str,
        "ats_type": same as source_board,
        "job_id": str | None,
        "title": str,
        "company": str,
        "company_size": "<50"|"50-200"|"200-1000"|"1000-5000"|"5000+"|"unknown",
        "company_industry": str,
        "location": str,
        "location_normalized": {
            "city": str|None, "state": str|None, "country": str|None,
            "is_remote": bool, "remote_region": str|None
        },
        "posted_date": ISO str or None,
        "hours_since_posted": int or None,
        "employment_type": "full-time"|"part-time"|"contract"|"internship"|"unknown",
        "salary_listed": {"min":int|None, "max":int|None, "currency":"USD", "period":"year"} or None,
        "jd_text": str,
        "apply_url": str | None,
        "raw_parsed": dict,
    }
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _strip_html(s: str | None) -> str:
    if not s:
        return ""
    # Drop scripts/styles
    s = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", s, flags=re.I | re.S)
    # Replace common block tags with newlines
    s = re.sub(r"</(p|div|li|h[1-6]|br)\s*>", "\n", s, flags=re.I)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    # Strip remaining tags
    s = re.sub(r"<[^>]+>", "", s)
    # Collapse whitespace, unescape entities
    s = html.unescape(s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    s = re.sub(r"[ \t]+", " ", s)
    return s.strip()


def _compute_hours_since(posted_iso: str | None,
                         now: datetime | None = None) -> int | None:
    if not posted_iso:
        return None
    try:
        # Support several shapes
        s = posted_iso.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    now = now or datetime.now(timezone.utc)
    delta = now - dt
    return int(delta.total_seconds() // 3600)


def _detect_remote(location_str: str) -> tuple[bool, str | None]:
    """Heuristic: is this location 'remote' and what region?"""
    if not location_str:
        return (False, None)
    low = location_str.lower()
    if "remote" not in low and "work from home" not in low and "wfh" not in low:
        return (False, None)
    # Region guess
    if re.search(r"united states|u\.?s\.?a?\.?|usa\b|us$|us[,\s]", low):
        return (True, "Remote - US")
    if "canada" in low:
        return (True, "Remote - Canada")
    if "europe" in low or "emea" in low or "eu " in low or low.endswith("eu"):
        return (True, "Remote - EU")
    if "worldwide" in low or "global" in low or "anywhere" in low:
        return (True, "Remote - Global")
    return (True, "Remote - Unspecified")


def _parse_location(loc: str) -> dict:
    """Best-effort split of a location string. Not perfect."""
    is_remote, region = _detect_remote(loc or "")
    # Strip "Remote - " prefix for city parsing
    s = (loc or "").strip()
    s_clean = re.sub(r"(?i)^remote\s*[-—]\s*", "", s)
    parts = [p.strip() for p in re.split(r"[,/•|]", s_clean) if p.strip()]
    city = state = country = None
    if parts:
        city = parts[0]
    if len(parts) >= 2:
        state = parts[1]
    if len(parts) >= 3:
        country = parts[-1]
    return {
        "city": city, "state": state, "country": country,
        "is_remote": is_remote, "remote_region": region,
    }


def _parse_salary_from_text(text: str) -> dict | None:
    """Very light extraction of 'Salary: $X-$Y' style strings from JD text.

    Returns None if no confident match. Avoids false positives by requiring
    explicit $ or USD and a plausible range.
    """
    if not text:
        return None
    # Look for "$XXX,XXX - $XXX,XXX" style
    m = re.search(
        r"\$(\d{2,3}(?:,\d{3})+|\d{4,6})\s*(?:-|to|–|—)\s*\$?(\d{2,3}(?:,\d{3})+|\d{4,6})",
        text,
    )
    if m:
        lo = int(m.group(1).replace(",", ""))
        hi = int(m.group(2).replace(",", ""))
        if 30000 <= lo <= 1000000 and lo <= hi <= 1500000:
            return {"min": lo, "max": hi, "currency": "USD", "period": "year"}
    return None


# ---------------------------------------------------------------------------
# Greenhouse
# ---------------------------------------------------------------------------

def parse_greenhouse(feed_json: dict, company_slug: str,
                     company_meta: dict | None = None) -> list[dict]:
    """Parse Greenhouse /boards/{slug}/jobs?content=true response."""
    company_meta = company_meta or {}
    now_iso = datetime.now(timezone.utc).isoformat()
    out = []
    jobs = feed_json.get("jobs", []) if isinstance(feed_json, dict) else []
    for j in jobs:
        title = j.get("title") or ""
        location = (j.get("location") or {}).get("name") or ""
        url = j.get("absolute_url") or ""
        updated = j.get("updated_at") or j.get("first_published") or None
        content_html = j.get("content") or ""
        jd = _strip_html(content_html)
        salary = _parse_salary_from_text(jd)

        record = {
            "source_board": "greenhouse",
            "source_url": url,
            "fetched_at": now_iso,
            "ats_type": "greenhouse",
            "job_id": str(j.get("id") or ""),
            "title": title,
            "company": company_meta.get("name", company_slug),
            "company_size": company_meta.get("size", "unknown"),
            "company_industry": company_meta.get("industry", "unknown"),
            "location": location,
            "location_normalized": _parse_location(location),
            "posted_date": updated,
            "hours_since_posted": _compute_hours_since(updated),
            "employment_type": "unknown",
            "salary_listed": salary,
            "jd_text": jd,
            "apply_url": url,
            "raw_parsed": j,
        }
        out.append(record)
    return out


# ---------------------------------------------------------------------------
# Lever
# ---------------------------------------------------------------------------

def parse_lever(feed_json: list, company_slug: str,
                company_meta: dict | None = None) -> list[dict]:
    """Parse Lever /v0/postings/{slug}?mode=json response."""
    company_meta = company_meta or {}
    now_iso = datetime.now(timezone.utc).isoformat()
    out = []
    if not isinstance(feed_json, list):
        return out
    for j in feed_json:
        title = j.get("text") or ""
        cats = j.get("categories") or {}
        location = cats.get("location") or ""
        url = j.get("hostedUrl") or j.get("applyUrl") or ""
        created_ms = j.get("createdAt")
        posted_iso = None
        if isinstance(created_ms, (int, float)):
            posted_iso = datetime.fromtimestamp(
                created_ms / 1000, tz=timezone.utc
            ).isoformat()
        jd = j.get("descriptionPlain") or _strip_html(j.get("description", ""))
        # Add requirements/preferred/etc sections
        for section in j.get("lists") or []:
            if section.get("text"):
                jd += f"\n\n{section['text']}\n"
                jd += _strip_html(section.get("content") or "")
        salary = _parse_salary_from_text(jd)
        commitment = (cats.get("commitment") or "").lower()
        emp_type = "full-time" if "full" in commitment else \
                   "part-time" if "part" in commitment else \
                   "contract" if "contract" in commitment else \
                   "internship" if "intern" in commitment else "unknown"

        out.append({
            "source_board": "lever",
            "source_url": url,
            "fetched_at": now_iso,
            "ats_type": "lever",
            "job_id": str(j.get("id") or ""),
            "title": title,
            "company": company_meta.get("name", company_slug),
            "company_size": company_meta.get("size", "unknown"),
            "company_industry": company_meta.get("industry", "unknown"),
            "location": location,
            "location_normalized": _parse_location(location),
            "posted_date": posted_iso,
            "hours_since_posted": _compute_hours_since(posted_iso),
            "employment_type": emp_type,
            "salary_listed": salary,
            "jd_text": jd.strip(),
            "apply_url": j.get("applyUrl") or url,
            "raw_parsed": j,
        })
    return out


# ---------------------------------------------------------------------------
# Ashby
# ---------------------------------------------------------------------------

def parse_ashby(feed_json: dict, company_slug: str,
                company_meta: dict | None = None) -> list[dict]:
    """Parse Ashby /posting-api/job-board/{slug} response."""
    company_meta = company_meta or {}
    now_iso = datetime.now(timezone.utc).isoformat()
    out = []
    jobs = feed_json.get("jobs", []) if isinstance(feed_json, dict) else []
    for j in jobs:
        title = j.get("title") or ""
        location = j.get("location") or j.get("locationName") or ""
        url = j.get("jobUrl") or j.get("applyUrl") or ""
        posted = j.get("publishedDate") or j.get("publishedAt")
        jd = j.get("descriptionPlain") or _strip_html(j.get("descriptionHtml", ""))

        # Ashby sometimes exposes compensation
        salary = None
        comp = j.get("compensation") or {}
        summ = comp.get("summaryComponents") or []
        # summaryComponents: [{"compensationType":"Salary","interval":"1 YEAR","minValue":150000,"maxValue":180000,"currencyCode":"USD"}, ...]
        for c in summ:
            if (c.get("compensationType") or "").lower() == "salary":
                mn, mx = c.get("minValue"), c.get("maxValue")
                if mn or mx:
                    salary = {
                        "min": mn, "max": mx,
                        "currency": c.get("currencyCode", "USD"),
                        "period": "year",
                    }
                    break
        if salary is None:
            salary = _parse_salary_from_text(jd)

        emp = (j.get("employmentType") or "").lower().replace("_", "-")
        emp_type = emp if emp in {"full-time", "part-time", "contract", "internship"} else "unknown"

        out.append({
            "source_board": "ashby",
            "source_url": url,
            "fetched_at": now_iso,
            "ats_type": "ashby",
            "job_id": str(j.get("id") or ""),
            "title": title,
            "company": company_meta.get("name", company_slug),
            "company_size": company_meta.get("size", "unknown"),
            "company_industry": company_meta.get("industry", "unknown"),
            "location": location,
            "location_normalized": _parse_location(location),
            "posted_date": posted,
            "hours_since_posted": _compute_hours_since(posted),
            "employment_type": emp_type,
            "salary_listed": salary,
            "jd_text": jd,
            "apply_url": url,
            "raw_parsed": j,
        })
    return out


# ---------------------------------------------------------------------------
# Workable
# ---------------------------------------------------------------------------

def parse_workable(feed_json: dict, company_slug: str,
                   company_meta: dict | None = None) -> list[dict]:
    """Parse Workable v3 response shapes."""
    company_meta = company_meta or {}
    now_iso = datetime.now(timezone.utc).isoformat()
    out = []
    # Workable sometimes returns {"results":[...]}, sometimes {"jobs":[...]}.
    jobs = []
    if isinstance(feed_json, dict):
        jobs = feed_json.get("results") or feed_json.get("jobs") or []
    elif isinstance(feed_json, list):
        jobs = feed_json
    for j in jobs:
        title = j.get("title") or j.get("full_title") or ""
        loc_obj = j.get("location") or {}
        if isinstance(loc_obj, dict):
            parts = [loc_obj.get("city"), loc_obj.get("region"), loc_obj.get("country")]
            location = ", ".join([p for p in parts if p]) or (loc_obj.get("location_str") or "")
            if loc_obj.get("telecommuting"):
                location = f"Remote - {loc_obj.get('country') or 'Unspecified'}"
        else:
            location = str(loc_obj)
        url = j.get("url") or j.get("application_url") or ""
        posted = j.get("created_at") or j.get("published_on")
        jd_parts = []
        for k in ("description", "requirements", "benefits"):
            if j.get(k):
                jd_parts.append(_strip_html(j[k]))
        jd = "\n\n".join([p for p in jd_parts if p])
        salary = _parse_salary_from_text(jd)

        out.append({
            "source_board": "workable",
            "source_url": url,
            "fetched_at": now_iso,
            "ats_type": "workable",
            "job_id": str(j.get("id") or j.get("shortcode") or j.get("code") or ""),
            "title": title,
            "company": company_meta.get("name", company_slug),
            "company_size": company_meta.get("size", "unknown"),
            "company_industry": company_meta.get("industry", "unknown"),
            "location": location,
            "location_normalized": _parse_location(location),
            "posted_date": posted,
            "hours_since_posted": _compute_hours_since(posted),
            "employment_type": "unknown",
            "salary_listed": salary,
            "jd_text": jd,
            "apply_url": j.get("application_url") or url,
            "raw_parsed": j,
        })
    return out


# ---------------------------------------------------------------------------
# SmartRecruiters
# ---------------------------------------------------------------------------

def parse_smartrecruiters(feed_json: dict, company_slug: str,
                          company_meta: dict | None = None) -> list[dict]:
    """Parse SmartRecruiters /v1/companies/{id}/postings response."""
    company_meta = company_meta or {}
    now_iso = datetime.now(timezone.utc).isoformat()
    out = []
    jobs = feed_json.get("content", []) if isinstance(feed_json, dict) else []
    for j in jobs:
        title = j.get("name") or ""
        loc_obj = j.get("location") or {}
        parts = [loc_obj.get("city"), loc_obj.get("region"), loc_obj.get("country")]
        location = ", ".join([p for p in parts if p])
        if loc_obj.get("remote"):
            location = f"Remote - {loc_obj.get('country') or 'Unspecified'}"
        # SmartRecruiters provides a detail URL, not full JD in list. The skill
        # orchestrator may web_fetch individual jobs for full JDs.
        posted = j.get("releasedDate") or j.get("updated_on")
        jd_sections = []
        for sec in (j.get("jobAd", {}).get("sections") or {}).values():
            if isinstance(sec, dict) and sec.get("text"):
                jd_sections.append(_strip_html(sec["text"]))
        jd = "\n\n".join(jd_sections)
        salary = _parse_salary_from_text(jd)

        out.append({
            "source_board": "smartrecruiters",
            "source_url": j.get("ref") or j.get("applyUrl") or "",
            "fetched_at": now_iso,
            "ats_type": "smartrecruiters",
            "job_id": str(j.get("id") or j.get("refNumber") or ""),
            "title": title,
            "company": company_meta.get("name", company_slug),
            "company_size": company_meta.get("size", "unknown"),
            "company_industry": company_meta.get("industry", "unknown"),
            "location": location,
            "location_normalized": _parse_location(location),
            "posted_date": posted,
            "hours_since_posted": _compute_hours_since(posted),
            "employment_type": "unknown",
            "salary_listed": salary,
            "jd_text": jd,
            "apply_url": j.get("applyUrl") or "",
            "raw_parsed": j,
        })
    return out


# ---------------------------------------------------------------------------
# URL builders (the orchestrator uses these to construct web_fetch targets)
# ---------------------------------------------------------------------------

def build_feed_url(ats: str, slug: str) -> str:
    if ats == "greenhouse":
        return f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    if ats == "lever":
        return f"https://api.lever.co/v0/postings/{slug}?mode=json"
    if ats == "ashby":
        return f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true"
    if ats == "workable":
        # Public subdomain-style endpoint
        return f"https://apply.workable.com/api/v1/widget/accounts/{slug}"
    if ats == "smartrecruiters":
        return f"https://api.smartrecruiters.com/v1/companies/{slug}/postings"
    raise ValueError(f"Unknown ATS: {ats}")


PARSERS = {
    "greenhouse": parse_greenhouse,
    "lever": parse_lever,
    "ashby": parse_ashby,
    "workable": parse_workable,
    "smartrecruiters": parse_smartrecruiters,
}
