# Changelog

All notable changes to FATS are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project uses [Semantic Versioning](https://semver.org/).

## [1.0.0] — 2026-04-21

First public release.

### Pipeline
- Six-stage gated pipeline: Profile → Roles → Search Plan → Hunt → Review → Tailor
- Stage-gating: each stage produces a concrete artifact that the next stage consumes
- Cross-session persistence: profile, settings, CSV, and resumes save to `/mnt/user-data/outputs`
- Resume-state check on every session start — returning users skip straight to where they left off

### Data sources
- Five public ATS feed parsers: Greenhouse, Lever, Ashby, Workable, SmartRecruiters
- Google Jobs integration via Claude's `web_search` + `web_fetch` (covers Indeed, LinkedIn, ZipRecruiter indirectly)
- 187 seed companies curated across the five ATSes
- URL builder + common job record schema normalizes every source to the same shape

### Scoring and ranking
- 4-axis fit score (skills 40%, experience 25%, industry 15%, location+comp 20%) with per-axis breakdown columns in the CSV
- Ghost-job detection with content/temporal/company/source signals; threshold at 3+ points = medium, 6+ = high
- Salary inference via LLM priors when not listed, location-aware with multipliers for SF/NYC/DC/etc.
- Dedupe across boards by normalized `(company | title | city)` with source-priority merging

### Resumes
- Three ATS-safe templates: Clean Modern (default), Harvard Classic, Mirror User
- Strict ATS compliance: single column, standard headings, no tables/icons/photos, web-safe fonts
- Programmatic `fabrication_check` before any save — flags invented numbers, team sizes, skills, credentials, employers
- `.docx` output via python-docx and `.pdf` output via reportlab direct — no `docx → pdf` conversion step, so PDFs render identically on every platform without requiring MS Word, LibreOffice, or system libraries
- Bundled OFL-licensed fonts (EB Garamond, Carlito) in `assets/fonts/` guarantee typographically faithful PDFs on any install

### User experience
- README-style `/fats` welcome with 6-step workflow, commands table, ground rules, and clear next-action prompts
- `/fats-healthcheck` runs 13 self-tests in ~3 seconds — recommended as first command on any new install
- Fail-loud error handling: partial results surfaced with explicit source-by-source status
- Non-technical user doctrine: no jargon without definitions, short choices with `ask_user_input_v0` where possible, always show the plan before acting

### Quality
- 141 pytest tests across 7 test files (profile, ATS fetchers, jobs, resume, company seed, healthcheck, end-to-end integration)
- 13-check runtime health check covers imports, schemas, seed data, all 5 parsers, scoring pipeline, ghost detection, bundled fonts, resume rendering (.docx + .pdf), and fabrication-check behavior
- JSON schema validation for profiles and settings
- Evidence ledger in profile for traceability — every skill and claim points to a source doc

### Slash commands
- `/fats`
- `/fats-help` (show welcome README)
- `/fats-healthcheck` (12-check self-test)
- `/fats-new-hunt`, `/fats-profile`, `/fats-settings`, `/fats-status`, `/fats-reset`

---

## Planned

### [1.1.0] — next minor
- Cover letter companion flow
- Expanded company seed list (target: 500+ across ATSes)
- Persistent hunt history across sessions for stronger ghost detection

### [1.2.0]
- JobSpy integration for direct Indeed/LinkedIn scraping (Claude Code only)
- Per-role company seed overrides in settings

### [2.0.0]
- One-line Claude Code install (`/plugin install fats`)
- Project-level distribution for teams
- Multi-profile support for users hunting across two different career paths simultaneously
