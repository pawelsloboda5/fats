# Salary inference

When a job posting doesn't list a salary, FATS estimates one so the user can still compare jobs on comp. The inferred range goes in `salary_min` / `salary_max` with `salary_source = "inferred"` and a `salary_basis` note explaining how we got there.

## When to infer

Always infer when `salary_listed` is null. Never overwrite a listed salary with an inference. If the salary is listed but only has a single number (e.g., "$150K"), treat that as a point estimate and leave it as `salary_min = 150000, salary_max = 150000, salary_source = "listed"`.

## Inputs to the inference

1. **Role + level**: "Senior Marketing Manager", "Staff Software Engineer", etc.
2. **Location**: city-specific. This is critical — DC/SF/NYC skew 20-40% above national median; Midwest/South often 10-25% below.
3. **Remote flag**: remote-US typically mid-tier (company pays slightly below in-office top markets but above national median).
4. **Company size**: small startup (<50) usually 10-20% below; scale-ups (50-500) at median; public/big tech 20-40% above.
5. **Company industry**: fintech / big tech / AI-core usually +15-30%; nonprofit / edu usually -20-30%.
6. **Years of experience expected**: reinforces role + level.

## The LLM approach

FATS doesn't call out to a paid salary API. Instead, the LLM uses its priors (trained on public comp data sources like Levels.fyi, Payscale, BLS, Glassdoor up to its knowledge cutoff) to produce a range. The prompt template:

```
You are estimating salary range for this job. Do not invent precision you don't have.

Role + level: {title} ({inferred_seniority})
Location: {city}, {state_or_region} (remote_type: {remote_type})
Company: {company_name} — {company_size}, {company_industry}
JD excerpt (for years-of-experience signals): {first 400 chars of JD}

Output a JSON object:
{
  "min_usd": int,
  "max_usd": int,
  "confidence": "high" | "medium" | "low",
  "basis": "1-sentence explanation in plain English"
}

Rules:
- Be in annual USD, total cash comp (base + expected cash bonus; exclude equity).
- Prefer ranges of 15-25% width. Don't say "$100K-$300K" — that's useless.
- If you genuinely don't know, set confidence to "low" and explain.
- Base your estimate on what a Jan 2026 market rate would be, not 2020.
- Do not anchor on the user's desires — anchor on the market for THIS role at THIS company.
```

The LLM response goes directly into the job record's salary fields.

## Location adjustments (quick reference)

When the LLM is anchoring, these rough 2026 multipliers apply to a national-median base:

| Location | Multiplier |
|---|---|
| San Francisco Bay Area | 1.35x |
| NYC metro | 1.25x |
| Seattle | 1.20x |
| Boston | 1.15x |
| DC metro | 1.15x |
| LA | 1.15x |
| Austin / Denver / Chicago | 1.05x |
| National median (remote-US) | 1.00x |
| Most Midwest / South metros | 0.90x |
| Rural / small metros | 0.80x |

These are rough — the LLM should use them as sanity checks, not formulas.

## Flagging low confidence

If `confidence = "low"`, Stage 5's summary should call it out:

> Note: 3 of the top jobs don't list salary. I've inferred ranges (marked with *), but two are low-confidence because the companies are small and industry is unusual. Treat those ranges as guesses, not quotes.

## Implementation

`scripts/jobs.py` has a `infer_salary(job, profile, llm_call)` function. The LLM call itself is handled by Claude directly (not via an API key) — Python calls into it via a callback passed in from the skill orchestrator.

In practice, this means Stage 5 loops over jobs that need inference, Claude generates each salary estimate inline using its own priors, and Python just stores the result.
