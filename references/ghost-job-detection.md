# Ghost job detection

Ghost jobs — postings that aren't real open roles — are roughly 18-22% of job listings in 2026. They waste user time and create false hope. FATS flags them but doesn't auto-drop, because detection is imperfect.

Every job gets `ghost_job_risk`: `low`, `medium`, or `high`, plus a `ghost_job_reason` string explaining flagged items.

## Red flags and scoring

Start each job at 0 risk points. Add points for each red flag triggered. Threshold:
- 0-2 points: `low`
- 3-5 points: `medium`
- 6+ points: `high`

### Content-based flags

**+3: Generic boilerplate JD**
- JD is under 400 characters
- JD contains only generic "we're a growing company, looking for passionate people" language with no role-specific duties

**+2: No specific requirements listed**
- "We're looking for smart people" with no list of hard skills, tools, or years of experience

**+2: No team, product, or project named**
- Doesn't mention which team this role is on, what product they work on, or what projects they'd own

**+1: Salary not listed AND seniority ambiguous AND location vague**
- "Professional", "experienced", "various locations"

**+3: "Join our talent network" or "always hiring" language**
- "We're always interested in meeting great people"
- "Submit your resume for future opportunities"
- "Join our talent community"

### Temporal flags

**+3: Posted more than 30 days ago but still live**
- Legitimate roles that take 30+ days to fill usually get updated/reposted or closed. A 60-day-old posting that's still up is very often a ghost.

**+2: Posted 14-30 days ago but still live**
- Soft flag — could be real but getting stale.

**+4: Known reposted repeatedly**
- If this job title+company+location appeared in a prior FATS hunt more than 30 days ago, that's a strong signal. This requires persistent hunt history — check for prior `fats-hunt-raw.json` files in outputs or uploads.

### Company-behavior flags

**+2: Company has 20+ simultaneous open postings**
- Often a "pipeline builder" company that posts aggressively for future hiring, not current need. Count from ATS feed response.

**+2: Company has 5+ identical title postings currently open**
- "Senior Software Engineer" posted 8 times for the same company in the same week is often a pipeline ploy.

**+1: Company is a staffing agency or recruiting firm**
- Detectable from company name patterns ("Talent Partners", "Staffing", "Recruiters", "Search", etc.) or from company description.

### Source flags

**+1: Sourced only from LinkedIn with no ATS-feed confirmation**
- LinkedIn hosts a lot of ghost jobs, especially from large companies. Cross-presence on Greenhouse/Lever/etc. is a positive signal.

**-2 (subtraction): Job appears on multiple ATS feeds with consistent data**
- Strong signal it's real. Reduces risk.

**-2 (subtraction): Salary explicitly listed with a specific range**
- Real jobs are more likely to have real salary ranges. Ghost postings often omit salary.

## The `ghost_job_reason` string

When risk is `medium` or `high`, explain in plain English. Cap at ~2 sentences.

Examples:

- "Posted 47 days ago and still open; no salary range." → `medium`
- "JD is 180 characters of boilerplate; no specific requirements." → `medium`
- "Company has 28 simultaneous open postings including 7 for this exact title; posted 34 days ago." → `high`
- "Talent-network-style language; JD mentions no team or product." → `medium`

## Honesty in the UI

When you surface ghost flags to the user (Stage 5 summary), don't moralize. Something like:

> **1 medium-risk ghost job flagged** (Acme Corp, posted 41 days ago with no salary range). That doesn't mean it's fake — sometimes roles sit open for weeks — but it's worth checking LinkedIn or Glassdoor for recent employee reviews before investing in an application.

## Implementation

`scripts/jobs.py` `ghost_risk(job, profile, prior_hunt_history=None)` returns `{risk, points, reason}`.
