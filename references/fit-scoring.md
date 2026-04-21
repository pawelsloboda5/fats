# Fit scoring

A 0-100 number expressing how good a match a job is for the user. Computed as a weighted sum of four sub-axes, each also 0-100. Both the total and the breakdown appear in the CSV.

## The four axes

### 1. Skills match (weight: 40%)

Most important axis. Measures the overlap between the JD's top keywords and the user's profile.evidence.

**Formula:**
- Extract top 20 JD keywords (hard skills + tools + domain terms). See `stage-6-tailor.md` Step 1 for the extraction method.
- For each keyword, check if it appears in `profile.evidence.skills_evidence` or in `profile.experience[].bullets` or `profile.experience[].technologies`.
- Score = 100 × (matches / 20), clamped to 0-100.

**Bonus:** if the JD lists 5 or fewer total keywords (sparse JD), normalize against the actual count. A 4-keyword JD with all 4 matched is 100, not 20.

### 2. Experience level match (weight: 25%)

How well the user's seniority aligns with what the role wants.

**Method:**
- Detect the role's required seniority from the JD. Signals: title words ("Senior", "Staff", "Lead"), years of experience language ("5+ years"), scope language ("manage a team", "own end-to-end", "IC role").
- Compare to user's `inferred_seniority` from Stage 1.

**Scoring:**
- Exact match (e.g., both "senior"): 100
- One level off in either direction: 80
- Two levels off: 50
- Three+ levels off: 20

**Edge cases:**
- JD is ambiguous on level: 75 (assume reasonable fit but not excellent)
- Role is IC and user is management-track: deduct 20 (and vice versa) unless user is deliberately pivoting

### 3. Industry match (weight: 15%)

Lowest weight because industry is the most flexible — most roles work across industries for most users.

**Method:**
- Determine the company's industry from `company_industry` in the job record.
- Compare to the industries in user's `profile.experience[].company`-derived industry footprint.

**Scoring:**
- Same industry: 100
- Adjacent industry (e.g., B2B SaaS ↔ DevTools): 85
- Distant but applicable (e.g., consumer tech ↔ B2B SaaS): 65
- Different vertical entirely (e.g., healthcare ↔ manufacturing): 40
- Regulated industry where user has no regulated experience (finance, healthcare, defense): 30

### 4. Location + comp match (weight: 20%)

Two sub-factors averaged.

**Location sub-score (0-100):**
- Role location matches user's stated `job_preferences.locations`: 100
- Role is remote and user accepts remote: 100
- Role is hybrid in user's city: 100
- Role is in a city user listed as secondary: 85
- Role requires relocation to a city user didn't mention: 40
- Role is onsite in a city user explicitly rejected: 0

**Comp sub-score (0-100):**
- Salary meets or exceeds user's `salary_floor`: 100
- Salary within 10% below floor: 80
- Salary within 20% below floor: 50
- Salary below 20% of floor: 20
- No salary listed but inferred salary is above floor: 85 (discounted because inference can be off)
- No salary listed and no floor set: 75 (neutral)

Average the two: `(location_score + comp_score) / 2`.

## The final score

```
fit_score = round(
  0.40 * skills_score +
  0.25 * experience_score +
  0.15 * industry_score +
  0.20 * location_comp_score
)
```

Save all four sub-scores in the CSV (columns 3-6 per `csv-schema.md`) so users can see why a score is what it is.

## Honest scoring doctrine

**Don't inflate.** A user with 3 years of Python applying to a Senior Backend Engineer role should see a lower experience score, not a 90 just to be encouraging. The fit score is most valuable when it's honest — it helps the user prioritize where to spend effort, and a sea of 90s helps no one.

**Don't be harsh on pivots.** If the user has explicitly said they're pivoting (Stage 2 stretch roles, or `preferences_hints.roles_mentioned` indicating a new direction), be forgiving on industry (up to +20) and experience (up to +15 for adjacent-level roles).

**Explain the score in `why_it_matches`.** The user shouldn't have to stare at the breakdown to understand why job #7 scored 72. The `why_it_matches` column should name the strengths and the gaps.

## Implementation

`scripts/jobs.py` `score_fit(job, profile)` returns `{total, skills, experience, industry, location_comp, why}` where `why` is the 2-sentence `why_it_matches` string.
