"""Company seed list utilities.

Loads the seed list, filters by ATS and/or role constraints, and exposes
helpers the skill orchestrator uses to plan the hunt.

Does not fetch from the network. Claude's `web_fetch` handles any live
verification; this module is pure data access.
"""

from __future__ import annotations

import json
from pathlib import Path


_SEED_CACHE = None


def _load_seed() -> dict:
    global _SEED_CACHE
    if _SEED_CACHE is None:
        # Path resolution: prefer skill-local asset, fall back to current dir
        here = Path(__file__).parent
        for candidate in [
            here / ".." / "assets" / "company_list_seed.json",
            Path("assets/company_list_seed.json"),
            Path("company_list_seed.json"),
        ]:
            if candidate.exists():
                _SEED_CACHE = json.loads(candidate.read_text())
                break
        if _SEED_CACHE is None:
            _SEED_CACHE = {"greenhouse": [], "lever": [], "ashby": [],
                           "workable": [], "smartrecruiters": []}
    return _SEED_CACHE


def list_companies(ats: str) -> list[dict]:
    """Return all companies for a given ATS."""
    seed = _load_seed()
    return list(seed.get(ats, []))


def filter_by_constraints(companies: list[dict],
                          constraints: dict | None) -> list[dict]:
    """Filter companies by role_constraints from a target_role.

    Supported constraints:
      industries: list[str]  — match if company.industry contains any of these (substring OK)
      company_size_min: int | None (treated as lower bound of bucket)
      company_size_max: int | None
      exclude_agencies: bool (only excludes companies flagged as agencies — we don't seed any, but stubbed)
    """
    if not constraints:
        return companies

    wanted_industries = [i.lower() for i in constraints.get("industries", []) if i]
    smin = constraints.get("company_size_min")
    smax = constraints.get("company_size_max")

    size_bucket_floor = {"<50": 0, "50-200": 50, "200-1000": 200,
                         "1000-5000": 1000, "5000+": 5000, "unknown": 0}
    size_bucket_ceiling = {"<50": 49, "50-200": 199, "200-1000": 999,
                           "1000-5000": 4999, "5000+": 10_000_000, "unknown": 10_000_000}

    out = []
    for c in companies:
        ind = (c.get("industry") or "").lower()
        if wanted_industries and not any(w in ind for w in wanted_industries):
            continue
        sz = c.get("size") or "unknown"
        if smin and size_bucket_ceiling.get(sz, 10_000_000) < smin:
            continue
        # Strict: if the bucket's lower bound exceeds the user's max, exclude.
        # E.g. user says max=200 → exclude "200-1000" (its floor is 200, which we
        # treat as "starts at 200, so not strictly under 200").
        if smax and size_bucket_floor.get(sz, 0) >= smax and sz != "unknown":
            continue
        out.append(c)
    return out


def plan_hunt_companies(target_roles: list[dict],
                        ats_enabled: list[str],
                        max_per_ats: int = 50) -> dict:
    """For each enabled ATS, pick up to max_per_ats companies that satisfy
    any target_role's constraints.

    Returns: {"greenhouse": [list of companies], "lever": [...], ...}
    """
    seed = _load_seed()
    plan = {}

    # Build a union of companies that satisfy ANY target role's constraints
    for ats in ats_enabled:
        if ats == "google_jobs":
            continue  # not an ATS in this sense
        all_for_ats = seed.get(ats, [])
        if not target_roles:
            plan[ats] = all_for_ats[:max_per_ats]
            continue
        picked_slugs = set()
        ordered = []
        for role in target_roles:
            constraints = role.get("role_constraints") or {}
            subset = filter_by_constraints(all_for_ats, constraints)
            for c in subset:
                if c["slug"] not in picked_slugs:
                    picked_slugs.add(c["slug"])
                    ordered.append(c)
                if len(ordered) >= max_per_ats:
                    break
            if len(ordered) >= max_per_ats:
                break
        # If we still have room, top off with unfiltered
        if len(ordered) < max_per_ats:
            for c in all_for_ats:
                if c["slug"] not in picked_slugs:
                    picked_slugs.add(c["slug"])
                    ordered.append(c)
                if len(ordered) >= max_per_ats:
                    break
        plan[ats] = ordered[:max_per_ats]

    return plan


def all_known_slugs() -> dict[str, list[str]]:
    """Return {ats: [slug, slug, ...]}. Useful for verification scripts."""
    seed = _load_seed()
    return {ats: [c["slug"] for c in seed.get(ats, [])] for ats in seed if ats != "notes" and ats != "schema_version" and ats != "last_verified"}
