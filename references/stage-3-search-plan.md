# Stage 3 — Search plan (the dry-run)

## Goal

Before firing off any scraping or fetching, show the user exactly what you're about to do. They approve (with or without edits), and only then does Stage 4 run.

This exists because: (a) job searches are slow and users hate re-running them, (b) users often have unstated preferences that only surface when they see the plan, and (c) being shown the plan builds trust with non-technical users who don't know what "Google Jobs via web_search" even means.

Output: a rendered summary + table, then an approved `search_plan.json`.

## Load the settings

Read `fats-settings.json` if it exists (from `/mnt/user-data/outputs/` or uploads). If not, use defaults from `assets/settings_defaults.json`. The settings that matter for Stage 3:

- `freshness_hours` — default 24
- `target_count` — default 20 (range 10-25)
- `boards_enabled` — default: all (Greenhouse, Lever, Ashby, Workable, SmartRecruiters, Google Jobs)
- `salary_floor` — optional, dollar amount
- `exclude_companies` — list of company names to skip
- `exclude_keywords` — list of JD keywords that disqualify (e.g., "Night shift", "Clearance required")

If `fats-settings.json` doesn't exist, tell the user they can run `/fats-settings` anytime to change these; for now you'll use defaults.

## Build the plan

For each target role × each enabled board, create a search entry. Expand into multiple queries per role when the role has common aliases ("Software Engineer" / "Software Developer" / "SWE"). Script helper: `scripts/jobs.py` `build_search_plan(profile, settings)`.

The plan object:

```json
{
  "generated_at": "ISO timestamp",
  "target_count": 20,
  "freshness_hours": 24,
  "locations": ["Washington, DC", "Remote - US"],
  "searches": [
    {
      "role": "Senior Marketing Manager",
      "category": "focused",
      "board": "greenhouse",
      "board_type": "ats_feed",
      "company_list_source": "seed_b2b_saas",
      "expected_count": 30,
      "eta_seconds": 10
    },
    {
      "role": "Senior Marketing Manager",
      "board": "google_jobs",
      "board_type": "search",
      "query": "\"Senior Marketing Manager\" B2B SaaS Washington DC remote past 24 hours",
      "expected_count": 15,
      "eta_seconds": 20
    },
    ...
  ],
  "estimated_total_results_before_dedupe": 180,
  "estimated_after_dedupe": 45,
  "estimated_after_fit_filter": 22
}
```

## Present it to the user

### The summary paragraph

Keep it to 4-6 sentences, no jargon:

```
Here's the plan. I'll search for 6 target roles across 6 job sources:
public ATS feeds (Greenhouse, Lever, Ashby, Workable, SmartRecruiters — these
are the systems companies actually use to post jobs) plus Google Jobs (which
pulls from Indeed, LinkedIn, ZipRecruiter, and thousands of others).

I'll only keep jobs posted in the last 24 hours, in Washington DC or remote-US,
and I'll deduplicate across sources. I expect to end up with around 20-25 strong
matches for you to review. Total runtime: roughly 2-3 minutes.
```

### The table

Render a compact table the user can eyeball. Columns: Role, Board, Location/Filter, Expected hits, ETA.

```
| Role                          | Board            | Filter                | Est hits | ETA  |
|-------------------------------|------------------|-----------------------|----------|------|
| Senior Marketing Manager      | Greenhouse feed  | B2B SaaS cos (~200)   | ~30      | 10s  |
| Senior Marketing Manager      | Google Jobs      | "Past 24h" DC/remote  | ~15      | 20s  |
| Senior Growth Marketing Mgr   | Greenhouse feed  | B2B SaaS cos          | ~12      | 10s  |
| ...                                                                                   |
| Director of Marketing         | Lever feed       | <500 employees        | ~8       | 8s   |
| Product Marketing Manager     | Google Jobs      | "Past 24h" DC/remote  | ~20      | 20s  |
| TOTAL                                                              ~180     ~2-3 min   |
```

### The role-to-board warning

If a role is ATS-feed-light (common for non-tech roles, blue-collar, creative, healthcare-specific, trades, gov contracting), surface this explicitly:

> **Heads up:** "Registered Nurse" is a role where public ATS feeds won't help much — most hospitals use Workday or iCIMS, which don't expose feeds. Your best results will come from Google Jobs (which indexes Indeed, LinkedIn, and hospital career sites). I'm still running ATS feeds in case, but expect maybe 2-3 from them vs 15-20 from Google Jobs.

The full list of ATS-heavy vs ATS-light role types is in `references/ats-feeds.md`.

## Ask for approval

Use `ask_user_input_v0` if available:

```
Options:
  - Looks good, run the hunt
  - Add or remove a board
  - Change filters (freshness, salary, location)
  - Cancel
```

If they say "change filters," route to settings (`references/settings.md`) and then come back to Stage 3 with the updated plan.

If they accept, save `search_plan.json` locally (for Stage 4 to pick up) and start Stage 4.

## Edge cases

- **Target count = 10 but plan expects 4**: warn the user, propose loosening filters (freshness 24h → 72h, salary floor dropped, +1 adjacent role).
- **Target count = 25 but plan expects 200**: warn that it'll be a flood, offer to tighten.
- **User has `exclude_companies` set**: show the list in the summary so they can double-check they meant to exclude those.
- **No enabled boards**: user turned off everything. Cannot proceed — prompt to enable at least one.
