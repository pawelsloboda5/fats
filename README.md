# FATS

**Fuak their ATS. Use yours.**

*Every job you apply to gets its own resume. Not a generic template you tweak — a separate `.docx` + `.pdf` per posting, rewritten to mirror that job's language. Zero fabricated experience.*

You applied to 200 jobs. You got three replies — two rejections and a recruiter trying to sell you a different job for less money. You're not the problem. Their filter is.

FATS is an Applicant Tracking System that scores *jobs* for fit to **you**, not the other way around. Drop your resume, tell it what you're looking for, and 15 minutes later you have:

- **A ranked spreadsheet** of 10–25 real, live postings — ghost jobs flagged, salary inferred where missing, every match explained.
- **A custom resume for every job you want to apply to.** Not one resume you send to everyone. A new `.docx` + `.pdf` per posting, each one rewritten to mirror that job's exact wording — 10 applications means 10 tailored files. Three ATS-safe templates to pick from. Nothing gets invented that isn't already in your profile.
- **Your work saved** to your outputs folder. Close the chat, come back next week, pick up mid-hunt.

Built for people doing this with three weeks of severance, on lunch breaks, at 11pm after the kids are asleep. No auto-apply bots — you still decide where to send it. No fabricated experience — their filter sniffs that out in interviews.

[![Version](https://img.shields.io/badge/version-1.1.1-blue)](https://github.com/pawelsloboda5/fats/releases)
[![License: PolyForm NC 1.0.0](https://img.shields.io/badge/License-PolyForm%20NC%201.0.0-orange.svg)](https://polyformproject.org/licenses/noncommercial/1.0.0/)
[![Claude](https://img.shields.io/badge/Claude-Pro%20%7C%20Max%20%7C%20Team-6B5ED7)](https://claude.ai)

---

## Install — pick your path

Three ways to run FATS. Pick the one that matches how you already use Claude — you only need one.

### 🖱️ I use Claude in a browser (claude.ai)

*No terminal, no coding. 5 minutes. If you're using Claude at claude.ai, this is you.*

1. Download `fats.zip` from the [Releases page](../../releases/latest). **Don't unzip it** — Claude wants the `.zip` as-is.
2. Go to [claude.ai](https://claude.ai) → profile icon (top-right) → **Settings** → **Capabilities**.
3. Toggle **Code execution and file creation** ON. *(One-time setup. If it's already on, skip.)*
4. Click **Skills** → **+ Create skill** → **Upload ZIP** → pick `fats.zip`. *(Button wording varies slightly by plan — look for the upload option.)*
5. Toggle **FATS** ON in your skills list.
6. Open a new chat, type `/fats-healthcheck`, press Enter. Wait ~3 seconds.

You should see 13 green checkmarks:

```
✅ All systems go.
Passed: 13 · Failed: 0 · Warnings: 0
  ✓ Module imports — 5 modules imported
  ✓ Schema and asset files — 3 asset files valid
  ✓ Company seed list — 187 companies across 5 ATSes
  ✓ File system writable — /mnt/user-data/outputs writable
  ✓ Profile lifecycle (build → validate → save → load)
  ✓ ATS feed parsers (5 ATSes)
  ✓ Dedupe → score → CSV pipeline
  ✓ Ghost-job detection
  ✓ Role proposal across job families
  ✓ Bundled OFL fonts (EB Garamond, Carlito)
  ✓ Resume rendering — .docx (3 templates)
  ✓ Resume rendering — .pdf (3 templates, reportlab)
  ✓ Fabrication check (clean + tainted)
```

If all 13 pass, type `/fats` to start your hunt.

### 💻 I use Claude Code on Mac or Linux

*One git command. 30 seconds. If you already have Claude Code installed and you're on macOS or Linux, this is you.*

```bash
git clone https://github.com/pawelsloboda5/fats.git ~/.claude/skills/fats
```

Open any Claude Code session, type `/fats-healthcheck`, expect 13 green checkmarks (same block as above).

**No git?** Download `fats.zip` from [Releases](../../releases/latest), unzip it, and move the inner `fats/` folder into `~/.claude/skills/`. Same result.

### 🪟 I use Claude Code on Windows

*One PowerShell command. 30 seconds. If you have Claude Code on Windows, this is you.*

```powershell
git clone https://github.com/pawelsloboda5/fats.git $env:USERPROFILE\.claude\skills\fats
```

Open any Claude Code session, type `/fats-healthcheck`, expect 13 green checkmarks (same block as above).

**No git?** Download `fats.zip` from [Releases](../../releases/latest), unzip it, and move the inner `fats/` folder into `C:\Users\<YourName>\.claude\skills\`. Same result.

### Requirements (all paths)

- **A paid Claude plan** — Pro ($20/mo), Max, Team, or Enterprise. [Skills aren't available on Free](https://support.claude.com/en/articles/12512180).
- **For the claude.ai path:** Code execution enabled in Settings → Capabilities (Step 3 above covers this).
- **For the Claude Code paths:** [Claude Code](https://docs.anthropic.com/claude-code) already installed.

### If it's not working

- **"I don't see Skills in Settings."** — You're on the Free plan; Skills need Pro or higher. If you're on a paid plan and still don't see it, try the [Customize](https://claude.ai/customize) page directly — the skills list sometimes lives there.
- **"Upload says 'invalid format'."** — Safari auto-unzipped the file on download. Use Chrome, or right-click → **Save Link As** to keep the zip intact.
- **"I typed `/fats` and nothing happened."** — The skill toggle is OFF, or you're in an old chat (skill changes don't apply to existing chats — start a new one).
- **"`/fats-healthcheck` shows a failure."** — Copy the failed check's detail and [open an issue](../../issues). The skill probably still mostly works — most failed checks don't block core usage (e.g., a missing bundled font is a benign warning; PDFs still render via ReportLab's built-in Helvetica/Times fallback and `.docx` output is unaffected).

## What it does

Six stages, one conversation. Each stage produces something concrete — a profile, a search plan, a CSV of live jobs, a tailored resume — that the next stage builds on. No phases that exist to feel thorough.

| Stage | Output | Time |
|---|---|---|
| 1. **Profile** | Merges your resume, LinkedIn, portfolio, and any other context into one canonical profile | ~5 min |
| 2. **Roles** | Proposes 3 focused + 3 adjacent target job titles for you to approve or edit | ~2 min |
| 3. **Search plan** | Shows you exactly which boards it'll hit and what queries it'll run, before searching | ~1 min |
| 4. **Hunt** | Pulls live postings from Greenhouse, Lever, Ashby, Workable, SmartRecruiters, and Google Jobs | ~3 min |
| 5. **Review** | Ranked CSV with fit scores (4-axis), ghost-job flags, salary inference, matched/missing keywords | ~2 min |
| 6. **Tailor** | Produces `.docx` + `.pdf` resumes (3 ATS-safe templates) with fabrication-proof guardrails | ~2 min/job |

**Total end-to-end: ~15–30 minutes.**

## Key design choices

- 🚫 **Never fabricates.** Every skill, number, team size, employer, credential, and claim on your tailored resume traces back to actual evidence in your profile. A programmatic `fabrication_check` enforces this before any resume saves. Real work beats invented work.
- 🔍 **Free data only.** No paid APIs. Public ATS JSON feeds (seeded with 187 companies) plus Google Jobs — which quietly indexes Indeed, LinkedIn, ZipRecruiter, and thousands of company career sites.
- 👻 **Flags ghost jobs.** Scored 0-2 (low), 3-5 (medium), 6+ (high). Spots talent-network language, boilerplate JDs, staffing-agency patterns, stale postings. We've seen their tricks; we call them out.
- ⚡ **Three-tier architecture.** An Opus orchestrator runs the pipeline and enforces fabrication rules. Five Haiku subagents search in parallel. Five Sonnet subagents tailor resumes in parallel (upgradable to Opus for senior/exec roles). All configurable via `/fats-settings`. Default Quality Mode is Balanced.
- 📁 **Persists across sessions.** Profile, settings, CSV, resumes — all saved to your outputs folder. Come back next week, pick up exactly where you left off.
- 🏥 **Built-in health check.** `/fats-healthcheck` runs 13 self-tests in 3 seconds. Know the install is sound before you hand over real data.

## Commands

| Command | What it does |
|---|---|
| `/fats` | Start a new hunt, or pick up where you left off |
| `/fats-healthcheck` | 13-check self-test. Run this first on a fresh install (3 seconds). |
| `/fats-new-hunt` | Skip ingest, use your existing profile to find fresh jobs |
| `/fats-profile` | View or edit your stored profile |
| `/fats-settings` | Change filters — location, salary floor, boards, freshness, etc. |
| `/fats-status` | Show which pipeline stage you're at |
| `/fats-help` | Show the full welcome/help message |
| `/fats-reset` | Wipe everything and start fresh |

You don't have to use commands. Saying *"help me find a marketing job"* or *"tailor my resume for this Stripe posting"* works too.

## What FATS Doesn't Do *(yet)*

- ❌ **Auto-apply.** You still click Apply and submit each one yourself. We don't touch their form.
- ❌ **Cover letters.** Not in scope for this skill — on the roadmap.
- ❌ **Mock interviews or interview prep.** Different workflow.
- ⚠️ **Non-tech roles get thinner coverage.** Trades, bedside healthcare, K-12 teaching, government contracting — their ATSes aren't in our public-feed set, so you'll lean heavily on Google Jobs. Still works; just narrower.

## Under the hood

```
fats/
├── SKILL.md                         # Orchestrator, stage router, doctrines
├── references/                      # Stage playbooks + cross-cutting docs (15 files)
│   ├── welcome.md                   # README-style first-run greeting
│   ├── stage-1-profile.md           # ... through stage-6-tailor.md
│   ├── ats-feeds.md                 # Endpoint patterns for 5 public ATSes
│   ├── csv-schema.md                # 33-column ranked CSV
│   ├── fit-scoring.md               # 4-axis rubric
│   ├── ghost-job-detection.md       # Red flags and thresholds
│   ├── salary-inference.md          # LLM-based estimation
│   ├── resume-templates.md          # Three ATS-safe templates
│   └── never-fabricate.md           # The tailoring line
├── scripts/                         # Python (pure parsing/rendering, no network)
│   ├── profile.py                   # Canonical profile construction
│   ├── ats_fetchers.py              # 5 ATS JSON parsers + URL builder
│   ├── jobs.py                      # Dedupe, scoring, ghost detection, CSV
│   ├── resume.py                    # 3 templates + docx→pdf + fabrication_check
│   ├── company_seed.py              # Filter/plan hunt companies
│   └── healthcheck.py               # 13-check self-test for /fats-healthcheck
├── assets/
│   ├── profile_schema.json          # JSON schema for profiles
│   ├── settings_defaults.json       # Factory defaults
│   └── company_list_seed.json       # 187 seed companies across 5 ATSes
└── tests/                           # 150 pytest tests across 8 files
```

The Python scripts are **pure parsers and renderers** — all network fetching happens through Claude's built-in `web_fetch` tool, not Python. This keeps the skill portable across Claude.ai, Claude Code, and API deployments.

## Development

```bash
# Clone and set up
git clone https://github.com/pawelsloboda5/fats.git
cd fats

# Run the health check (same one /fats-healthcheck invokes)
python3 -m scripts.healthcheck

# Run the full test suite
pip install pytest python-docx reportlab
python3 -m pytest tests/ -v
```

Expected output: 13/13 health checks pass, 150/150 pytest tests pass.

## Roadmap

- [ ] **v1.1** — Cover letter generation as companion flow
- [ ] **v1.2** — JobSpy integration for Indeed/LinkedIn direct scraping (Claude Code only)
- [ ] **v1.3** — Persistent hunt history for better ghost-job detection across runs
- [ ] **v2.0** — One-line Claude Code install + project-level skill distribution

## License

[PolyForm Noncommercial License 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0/). Free for personal use, research, hobby projects, students, charitable/educational/public-sector organizations, and any other noncommercial purpose. See [LICENSE](LICENSE) for the full text.

## Commercial Use

Using FATS inside a for-profit company, a revenue-generating product or service, a paid consulting engagement, or any other commercial context requires a separate paid commercial license.

To arrange a commercial license, contact:

- Website: [pawelbuilds.com](https://pawelbuilds.com)
- Email: pawelsloboda5@gmail.com

## Contributing

Issues and PRs welcome. Feature requests: open an issue, describe the use case. Bug reports: paste the output of `/fats-healthcheck` so we can see the shape of your environment before we start guessing.

## Acknowledgements

Built on Claude's Skills system. Shoulders-of-giants thanks to the open-source Claude skills community — [anthropics/skills](https://github.com/anthropics/skills) and [VoltAgent/awesome-agent-skills](https://github.com/VoltAgent/awesome-agent-skills) are both worth your time.
