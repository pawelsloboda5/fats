# Stage 5 — Review (rank, dedupe, score, CSV)

## Goal

Turn the raw hunt results into a ranked, deduplicated CSV the user can open in Excel or Google Sheets, then help them pick which jobs to tailor resumes for.

Output: `fats-jobs.csv` in `/mnt/user-data/outputs/`, a short summary in chat, and user's selection of jobs to advance to Stage 6.

## Dedupe

Jobs get cross-posted. Same role at Acme Corp appears on Greenhouse, on LinkedIn via Google Jobs, and on Indeed via Google Jobs. Dedupe key:

```
dedupe_key = normalize(company) + "|" + normalize(title) + "|" + normalize(location_city)
```

`normalize` lowercases, strips punctuation, strips seniority decorators ("Sr.", "Senior"), and maps known company aliases ("Meta" / "Facebook").

When multiple records share a dedupe key:
- Merge into a single record.
- `primary_url` = the best source, in preference order: `user_list > greenhouse > lever > ashby > workable > smartrecruiters > google_jobs`. The logic: direct ATS posts are more authoritative and usually have richer JDs than Google Jobs-indexed pages.
- `duplicate_urls` = array of all other URLs for the same posting.
- Merge salary fields (take widest range if multiple).
- Merge JD text (take the longest; shorter ones are usually truncated).

Helper: `scripts/jobs.py` `dedupe(raw_jobs)`.

## Fit scoring

For each unique job, compute a 0-100 fit score on four axes. Full rubric in `references/fit-scoring.md`. Summary:

| Axis | Weight | What it measures |
|---|---|---|
| Skills match | 40% | Fraction of JD-required skills present in profile `evidence` |
| Experience level match | 25% | Alignment of user's seniority with the role's required seniority |
| Industry match | 15% | Alignment of user's industry footprint with the company's industry |
| Location / comp match | 20% | Location feasibility + salary vs user's floor |

Record both the total (`fit_score`) and the per-axis breakdown (`fit_breakdown`). Both columns go in the CSV.

## Ghost job flagging

For each job, compute a ghost-job risk: `low`, `medium`, `high`, with a reason string. Full detection rules in `references/ghost-job-detection.md`. Short list of red flags:

- Posting repeatedly re-posted (appears in prior hunts with different dates)
- JD is generic boilerplate under 400 chars
- Company has 20+ simultaneous open postings for similar titles (visible from ATS feed counts)
- No salary listed AND no clear level AND no specific team named
- Posted 30+ days ago but still open
- "We're always hiring" / "Join our talent network" language

Most jobs will be `low`. Flag aggressively enough that users can skip red flags if they want, but don't auto-drop.

## Salary inference

For any job where `salary_listed` is null, use the LLM to infer a median salary range based on:

- Role title + seniority
- Location (DC/SF/NYC skew high; Midwest lower)
- Company size and industry

Full methodology in `references/salary-inference.md`. Record:

```json
{
  "salary_source": "inferred",
  "salary_min_inferred": 120000,
  "salary_max_inferred": 155000,
  "salary_confidence": "medium",
  "salary_basis": "DC-metro median for Senior Marketing Manager at mid-size B2B SaaS, based on 2026 BLS + Levels.fyi priors"
}
```

If salary IS listed, `salary_source = "listed"` and the basis field is empty.

## Build the CSV

Use `scripts/jobs.py` `write_csv(ranked_jobs, path)`. Columns per `references/csv-schema.md`:

1. `rank` (1-N by fit_score desc)
2. `fit_score` (0-100)
3. `fit_breakdown_skills` (0-100)
4. `fit_breakdown_experience` (0-100)
5. `fit_breakdown_industry` (0-100)
6. `fit_breakdown_location_comp` (0-100)
7. `job_title`
8. `company`
9. `company_size`
10. `company_industry`
11. `location`
12. `remote_type` (onsite / hybrid / remote)
13. `seniority_level`
14. `employment_type`
15. `salary_min`
16. `salary_max`
17. `salary_source` (listed / inferred)
18. `salary_confidence` (high / medium / low — "high" for listed)
19. `salary_basis` (blank if listed)
20. `posted_date`
21. `hours_since_posted`
22. `ghost_job_risk` (low / medium / high)
23. `ghost_job_reason`
24. `primary_url`
25. `duplicate_urls` (pipe-separated)
26. `source_board` (which board the primary came from)
27. `ats_type`
28. `required_keywords` (top 15 JD keywords, pipe-separated)
29. `matched_keywords` (subset present in profile evidence)
30. `missing_keywords` (subset NOT in profile evidence — the gaps)
31. `why_it_matches` (2-sentence LLM-generated summary of fit)
32. `full_jd` (complete plain-text JD)
33. `apply_method` (direct / via_linkedin / via_indeed / unknown)

## Summarize in chat

After writing the CSV, give the user a short summary plus the top 5-10 in a rendered table:

```
Hunt complete: **23 unique jobs** after dedupe, all posted in the last 24 hours.

**Top 5 by fit:**

| #  | Fit | Role                                 | Company      | Salary        | Posted  |
|----|-----|--------------------------------------|--------------|---------------|---------|
|  1 | 94  | Senior Marketing Manager             | Segment      | $165K-$195K   | 4h ago  |
|  2 | 91  | Senior Growth Marketing Manager      | Vercel       | $155K-$185K   | 11h ago |
|  3 | 88  | Senior Marketing Manager, B2B        | Figma        | $170K-$200K   | 7h ago  |
|  4 | 85  | Director, Demand Generation          | Clearbit     | $180K-$215K*  | 2h ago  |
|  5 | 83  | Senior Product Marketing Manager     | Retool       | $150K-$175K   | 18h ago |

*Inferred salary (range not listed).

**Ghost-job flags:** 1 medium-risk job (Acme Corp, reposted 4 times this year).

Full CSV is ready. Next: I'll tailor a resume for the top 5 by default. Want:
  (a) Top 5
  (b) Top 10
  (c) All 23
  (d) Let me pick specific rows
```

Use `ask_user_input_v0` if available.

## Present the CSV

Save `fats-jobs.csv` to `/mnt/user-data/outputs/` and call `present_files` so the user can download it immediately, even before picking resumes.

## Handle the user's selection

Based on their answer:
- **Top N** → pass rows 1..N to Stage 6.
- **All** → pass everything to Stage 6 with a warning that it'll take longer.
- **Pick specific** → ask for row numbers, parse, validate, pass those rows.

Save the selection to `fats-tailor-selection.json` so Stage 6 knows what to work on.
