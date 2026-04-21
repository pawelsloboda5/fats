# Stage 4 — The hunt

## Goal

Execute the approved search plan. Fetch postings from every enabled source, normalize them into a common schema, write raw results to disk.

Output: `fats-hunt-raw.json` — an array of job records (pre-dedupe, pre-score). Ranking, dedup, and CSV generation happen in Stage 5.

## Parallel dispatch

Three-tier architecture — Opus orchestrator (this Claude), plus N=5 search subagents (default Haiku) that fan out across ATS sources. See `references/subagents.md` for runtime mechanics.

The hunt fans out across 6 sources. Running them serially takes ~3 minutes; running them in parallel shaves it to ~30-60 seconds. See `references/subagents.md` for runtime detection and dispatch mechanics — this section just covers what Stage 4 specifically dispatches.

**Defaults (from `assets/settings_defaults.json`):**
- `settings.models.search_agent` — default `haiku`
- `settings.concurrency.search_agents` — default `5`

**Quality Mode context:** if the user picked **Fast** in the Quality Mode preset, this stage uses haiku (cheap, quick, good enough for feed parsing and title filtering). **Balanced** and **Premium** both bump search to sonnet (sharper on niche roles, ambiguous titles, and unusual aliases). The orchestrator passes the chosen model into each subagent call.

**Claude Code path (Task tool available):** spawn 5 subagents, one per dispatch unit. The 6 sources collapse into 5 because the two smallest-yield feeds combine cleanly:

1. Greenhouse (high-yield, dedicated subagent)
2. Lever (high-yield, dedicated subagent)
3. Ashby (dedicated subagent)
4. Workable + SmartRecruiters (combined — both low-yield, same pattern)
5. Google Jobs (high-yield, dedicated subagent)

Each subagent gets: the filtered company list for its source(s), the role_constraints, freshness window, the normalized schema, and writes its slice of results back to a shared `fats-hunt-raw.json` or returns records for the orchestrator to merge.

**claude.ai fallback (no Task tool):** issue 6 parallel `web_fetch` tool_use calls in a SINGLE assistant turn — one per source. Don't serialize them across turns. Parse and filter on the next turn once all responses return. This gets most of the speed benefit without real subagents.

**User-facing speed note:** parallel dispatch takes Stage 4 from ~3 min serial to ~30-60 sec. Mention this in the progress message so users know why it's fast.

## Source-by-source playbook

### Public ATS feeds (the free, legal, clean path)

Five ATSes expose public JSON feeds with no auth required. Patterns in `references/ats-feeds.md`. The workflow for each:

1. Load the company list from `assets/company_list_seed.json`, filtered to those on that ATS.
2. Filter further by any `role_constraints` (industry, size, agency exclusion).
3. For each company, construct the feed URL (see `ats-feeds.md`).
4. Use `web_fetch` to retrieve the JSON.
5. Parse with the corresponding parser in `scripts/ats_fetchers.py`.
6. Filter results by role title match (fuzzy — substring or known alias), location, and freshness (posted within `freshness_hours`).
7. Normalize to the common job record schema (see `references/csv-schema.md`).

Do not try to hit every company in parallel via 200 `web_fetch` calls. That's wasteful and slow. Instead:
- Prioritize companies that match `role_constraints` first.
- Cap at ~50 companies per ATS per run (configurable in settings as `max_companies_per_ats`, default 50).
- If fewer than `target_count/2` results come back, expand the cap.

### Google Jobs (via web_search → web_fetch)

Google Jobs is a meta-aggregator that indexes Indeed, LinkedIn, ZipRecruiter, company career pages, and thousands of others. You cannot hit its API directly for free, but you can:

1. Run a `web_search` query like: `"Senior Marketing Manager" "Washington DC" site:indeed.com OR site:linkedin.com posted past 24 hours`
2. Pull the top 10-15 results.
3. For each result URL, `web_fetch` the page to get the full JD.
4. Extract: title, company, location, posted_date, salary (if listed), description, apply_url.

Key practical tips:
- Include quotes around the exact role title to avoid fuzzy matches.
- Include the location term.
- Include "past 24 hours" or "this week" based on freshness setting.
- If `site:` operators are disallowed, fall back to plain queries — they still work, just with more noise.
- Parse the posted date carefully. "Posted 3 hours ago" → now - 3h. "Posted 2 days ago" → drop if freshness is 24h. "Posted 30+ days ago" → almost certainly a ghost job; drop unless user opted in.

### User-provided company list (optional)

If the user's settings include a `user_company_list`, treat it as the highest-priority source. For each company:
1. Check if it maps to a known ATS. If yes, fetch that feed.
2. If no, try `web_fetch` on `{company_name} careers` via `web_search` first, then fetch the top result.

## Parallelization

On Claude.ai, there's no true parallel subagent execution, but you can still batch `web_fetch` calls in a single turn (the model makes them concurrently). Guidelines:

- Batch ATS feed fetches 10-20 at a time.
- Interleave with Google Jobs queries so the user sees progress.
- After each batch, summarize what came in. A progress message every 20-30 seconds of work keeps the user oriented.

Example progress message:

> Running the hunt…
> - ATS feeds: 3 of 5 done (Greenhouse ✓ 42 jobs, Lever ✓ 18 jobs, Ashby ✓ 11 jobs, Workable in progress, SmartRecruiters in progress)
> - Google Jobs: 2 of 6 role queries done (Senior Marketing Manager ✓ 14 jobs, Growth Marketing Manager ✓ 9 jobs)
> - Total raw hits so far: 94. Deduping and scoring after all sources finish.

## The common job record schema

Every source, after parsing, produces records in this schema:

```json
{
  "source_board": "greenhouse | lever | ashby | workable | smartrecruiters | google_jobs | user_list",
  "source_url": "original posting URL",
  "fetched_at": "ISO timestamp",
  "ats_type": "greenhouse | lever | ashby | workable | smartrecruiters | unknown",
  "job_id": "source-internal ID if available",
  "title": "exact title as posted",
  "company": "company name",
  "company_size": "<50 | 50-200 | 200-1000 | 1000-5000 | 5000+ | unknown",
  "company_industry": "inferred from company name + JD keywords, or unknown",
  "location": "as-posted location string",
  "location_normalized": { "city": "...", "state": "...", "country": "...", "is_remote": bool, "remote_region": "US | Global | null" },
  "posted_date": "ISO timestamp (or best estimate)",
  "hours_since_posted": number,
  "employment_type": "full-time | part-time | contract | internship | unknown",
  "salary_listed": { "min": null, "max": null, "currency": "USD", "period": "year" } or null,
  "jd_text": "full plain-text description",
  "apply_url": "direct apply URL if separate from source_url",
  "raw_parsed": { /* original parsed object for forensics */ }
}
```

## Filtering during the hunt

Apply these filters as records come in — don't wait for Stage 5:

1. **Freshness** — drop anything posted more than `freshness_hours` ago.
2. **Location** — drop if location doesn't match any of the user's accepted locations or remote preferences.
3. **Excluded companies** — drop if company is in `exclude_companies`.
4. **Excluded keywords** — drop if JD contains any `exclude_keywords`.
5. **Salary floor** — drop only if salary is listed and below the floor. Don't drop jobs with no listed salary.
6. **Title match** — keep only if title matches one of the target roles (including known aliases from `scripts/jobs.py` `role_aliases()`). Be generous here — borderline matches should be kept and scored in Stage 5.

Everything that survives goes into the raw results.

## Error handling (fail loud)

When any source fails:

- Record the failure in `fats-hunt-log.json` with source, error type, and message.
- Continue with remaining sources.
- At the end of Stage 4, summarize failures to the user before Stage 5:

> Hunt finished. Here's what I got:
>
> - Greenhouse ✓ 42 raw jobs
> - Lever ✓ 18 raw jobs
> - Ashby ✓ 11 raw jobs
> - Workable ✗ **0 jobs** — the feed returned 429 (rate limited). Retrying once or twice in a new run might help.
> - SmartRecruiters ✓ 6 raw jobs
> - Google Jobs ✓ 47 raw jobs (across 6 role queries)
>
> Total: 124 raw, before dedupe. Moving to Stage 5 to rank and produce the CSV.
>
> Want me to retry Workable before moving on, or continue?

## Save and hand off

Write all raw records to `fats-hunt-raw.json` (workspace file, not an output the user needs to see yet). Write the hunt log to `fats-hunt-log.json`.

Then proceed to Stage 5.
