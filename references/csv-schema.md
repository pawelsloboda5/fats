# CSV schema

The Stage 5 output CSV is the user's single working document for the rest of their job search. It needs to be rich enough to be useful long-term without being so wide they can't open it in Excel.

## Columns (in order)

| # | Column | Type | Description |
|---|--------|------|-------------|
| 1 | `rank` | int | 1-based rank by fit_score desc. Ties broken by hours_since_posted asc. |
| 2 | `fit_score` | int 0-100 | Weighted total of the 4 axes. See `fit-scoring.md`. |
| 3 | `fit_breakdown_skills` | int 0-100 | Skills-axis subscore. |
| 4 | `fit_breakdown_experience` | int 0-100 | Experience-level subscore. |
| 5 | `fit_breakdown_industry` | int 0-100 | Industry match subscore. |
| 6 | `fit_breakdown_location_comp` | int 0-100 | Location + comp subscore. |
| 7 | `job_title` | string | Exact title as posted. |
| 8 | `company` | string | Company name. |
| 9 | `company_size` | enum | `<50`, `50-200`, `200-1000`, `1000-5000`, `5000+`, `unknown`. |
| 10 | `company_industry` | string | Best inference (e.g., "B2B SaaS", "Fintech"). |
| 11 | `location` | string | As-posted location. |
| 12 | `remote_type` | enum | `onsite`, `hybrid`, `remote`, `unknown`. |
| 13 | `seniority_level` | enum | `entry`, `junior`, `mid`, `senior`, `staff`, `principal`, `manager`, `director`, `vp`, `c-level`, `unknown`. |
| 14 | `employment_type` | enum | `full-time`, `part-time`, `contract`, `internship`, `unknown`. |
| 15 | `salary_min` | int \| null | Annual USD. Either listed or inferred. |
| 16 | `salary_max` | int \| null | Annual USD. |
| 17 | `salary_source` | enum | `listed`, `inferred`. |
| 18 | `salary_confidence` | enum | `high` (for listed), `medium`/`low` (for inferred). |
| 19 | `salary_basis` | string | Empty if listed. For inferred: short note ("DC-metro median, mid-size B2B SaaS, Senior IC"). |
| 20 | `posted_date` | ISO | Best estimate. |
| 21 | `hours_since_posted` | int | At fetch time. |
| 22 | `ghost_job_risk` | enum | `low`, `medium`, `high`. |
| 23 | `ghost_job_reason` | string | Short reason if medium/high. Empty if low. |
| 24 | `primary_url` | url | Best source URL for this job (most authoritative). |
| 25 | `duplicate_urls` | string | Pipe-separated (`|`) list of other URLs for the same job. Empty if unique. |
| 26 | `source_board` | enum | Which board `primary_url` came from. |
| 27 | `ats_type` | enum | `greenhouse`, `lever`, `ashby`, `workable`, `smartrecruiters`, `unknown`. |
| 28 | `required_keywords` | string | Top 15 JD keywords, pipe-separated. Order = JD importance. |
| 29 | `matched_keywords` | string | Subset of required_keywords present in user's profile evidence. Pipe-separated. |
| 30 | `missing_keywords` | string | Subset not in evidence. Pipe-separated. These are the user's gaps. |
| 31 | `why_it_matches` | string | 2-sentence LLM summary of fit. Written in 2nd person ("You've done X, and this role needs Y."). |
| 32 | `full_jd` | string | Complete plain-text JD. Can be long — Excel handles it fine. |
| 33 | `apply_method` | enum | `direct`, `via_linkedin`, `via_indeed`, `via_google_jobs`, `unknown`. |

## Notes on tricky fields

### `duplicate_urls`
Use pipe separator, not comma — JDs sometimes contain commas and we don't want to explode the CSV. Excel and Google Sheets render pipe-delimited lists fine.

### `required_keywords`
Extracted by LLM from the JD. Top 15 by importance. Importance signals: keyword appears in "Requirements" section, appears in title, repeated 3+ times, bolded.

### `matched_keywords` / `missing_keywords`
Matching is against `profile.evidence`, not against the whole profile. Evidence is the traceability ledger from Stage 1. A skill only "matches" if there's a documented source for it.

### `why_it_matches`
User-facing summary. Write it TO the user, not about them. Example:
- Good: "You've got 8 years in B2B SaaS marketing ops with HubSpot and Salesforce — this role centers on exactly that stack, and they're looking for someone senior enough to mentor a team of 3."
- Bad: "The candidate has relevant experience in marketing operations."

### `full_jd`
Keep as plain text. Strip HTML. Don't truncate — if a JD is 3000 words, we keep all 3000. Excel handles long cells fine; the CSV library is `csv` module with `csv.writer` using `quoting=csv.QUOTE_ALL` to prevent embedded newlines from breaking rows.

## Implementation

`scripts/jobs.py` `write_csv(ranked_jobs, path)` handles all CSV writing. Uses `csv.DictWriter` with explicit field names (so column order is stable) and `QUOTE_ALL` to survive any weirdness in JD text.

Also writes a sidecar `fats-jobs-summary.md` with the top 10 in a markdown table, for users who just want to eyeball results without opening Excel.
