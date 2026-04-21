# Changelog

All notable changes to FATS are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project uses [Semantic Versioning](https://semver.org/).

## [1.1.1] — 2026-04-20

### Fixed
- **Quality Mode preset drift.** `references/subagents.md` described the wrong Fast/Balanced/Premium mappings (Fast-as-default, Balanced bumping search to sonnet, orchestrator tier omitted). Realigned to match SKILL.md and the v1.1.0 directive — Balanced is the default (orchestrator opus, search haiku, resume sonnet), Fast downgrades the orchestrator to sonnet, Premium goes opus end-to-end with sonnet search. Added the on-runtime caveat that orchestrator tier is documentary on claude.ai.
- `README.md` healthcheck count corrected to 13 checks (was 12) and pytest count to 150 across 8 files (was 141 across 7).
- `CHANGELOG.md` "Planned" section renumbered: 1.1.0 is released, so pending roadmap items now roll up under 1.2.0.
- `CHANGELOG.md [1.1.0] Unchanged` line corrected — 145 previous tests + 5 new settings tests = 150 total (previously claimed 145).

## [1.1.0] — 2026-04-20

### Added
- **Three-tier model architecture.** Main orchestrator (default Opus) + 5 parallel search subagents (default Haiku) + 5 parallel resume subagents (default Sonnet). All three tiers configurable via `/fats-settings`.
- **Parallel subagent dispatch for Stage 4 (Hunt) and Stage 6 (Tailor)** in Claude Code — 5 concurrent subagents with per-call model selection. Default: Haiku for search, Sonnet for resumes.
- **Parallel tool-call fallback** in claude.ai browser — Stage 4 fans out as 6 concurrent `web_fetch` calls in one turn; Stage 6 keeps per-job generation serial but parallelizes rendering within a job.
- **Quality Mode preset** asked once at fresh-hunt start — **Balanced is now the default** (orchestrator opus, search haiku, resume sonnet). Options: Fast (orchestrator sonnet, search haiku, resume sonnet) / Balanced (default — orchestrator opus, search haiku, resume sonnet) / Premium (orchestrator opus, search sonnet, resume opus) / keep saved settings. Applies in-memory for the session unless the user saves it as default.
- New settings keys: `models.orchestrator` (default opus), `models.search_agent` (default haiku), `models.resume_agent` (default sonnet) — all enum `haiku` | `sonnet` | `opus`. Plus `concurrency.search_agents`, `concurrency.resume_agents` (integer 1–8).
- New playbook: `references/subagents.md` — authoritative reference for the three-tier architecture, runtime detection (Claude Code vs claude.ai), and parallel dispatch mechanics for both runtimes.

### Changed
- `README.md` install section moved to prominent position directly after the hero; browser (claude.ai) path listed first, Claude Code paths second and third.
- `SKILL.md` metadata.version → 1.1.0. Added Quality Mode prompt section. Description trigger phrases lightly extended to cover speed/parallel queries.
- `references/stage-4-hunt.md` and `references/stage-6-tailor.md` now point to `subagents.md` for dispatch mechanics and Quality-Mode-aware model selection.
- `references/settings.md` documents the new `models.*` and `concurrency.*` keys with cost and throttle notes.

### Unchanged
- PolyForm Noncommercial 1.0.0 license. No behavior changes in never-fabricate doctrine, fit scoring, ghost-job detection, or CSV schema. All 145 previous pytest tests still apply; v1.1.0 adds 5 new tests for the three-tier settings keys (150 total).

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

### [1.2.0] — next minor
- Cover letter companion flow
- Expanded company seed list (target: 500+ across ATSes)
- Persistent hunt history across sessions for stronger ghost detection
- JobSpy integration for direct Indeed/LinkedIn scraping (Claude Code only)
- Per-role company seed overrides in settings

### [2.0.0]
- One-line Claude Code install (`/plugin install fats`)
- Project-level distribution for teams
- Multi-profile support for users hunting across two different career paths simultaneously
