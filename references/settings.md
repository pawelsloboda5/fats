# Settings (`/fats-settings`)

A user can run `/fats-settings` at any time to view and change the filters FATS uses. Settings persist to `fats-settings.json` in `/mnt/user-data/outputs/`. If no settings file exists, defaults from `assets/settings_defaults.json` are used.

## The settings object

```json
{
  "freshness_hours": 24,
  "target_count": 20,
  "boards_enabled": ["greenhouse", "lever", "ashby", "workable", "smartrecruiters", "google_jobs"],
  "max_companies_per_ats": 50,

  "locations": ["Washington, DC"],
  "remote_preference": "hybrid_or_remote",
  "accept_relocation": false,

  "seniority_range": ["senior", "staff"],

  "salary_floor": null,
  "salary_source_ok": ["listed", "inferred"],

  "exclude_companies": [],
  "exclude_keywords": [],

  "include_stretch_roles": false,

  "user_company_list": [],

  "resume_template": "clean_modern",

  "auto_retry_on_failure": false,
  "ghost_risk_accept": ["low", "medium"],

  "last_updated": "ISO timestamp"
}
```

## The `/fats-settings` conversation

When the user runs `/fats-settings`, show the current values in a plain-English summary, then ask what to change:

```
Here's how FATS is currently set up:

**Freshness**: jobs posted in the last 24 hours
**Target count**: aim for 20 jobs per hunt (range 10-25)
**Boards**: all 6 enabled (Greenhouse, Lever, Ashby, Workable, SmartRecruiters, Google Jobs)
**Locations**: Washington, DC + remote
**Remote preference**: hybrid or remote OK
**Seniority**: Senior and Staff
**Salary floor**: none set
**Excluded companies**: none
**Excluded keywords**: none
**Template**: Clean Modern
**Ghost-job tolerance**: skip high-risk only

What do you want to change? (You can say things like "freshness to 48 hours", "drop LinkedIn", "salary floor 160k", "exclude Amazon", or "reset to defaults".)
```

Parse whatever they say into updates. Common things and their mappings:

| User says | Updates |
|---|---|
| "freshness 48" / "show me jobs from the last 48 hours" | `freshness_hours = 48` |
| "want 30 jobs" / "more jobs please" | `target_count = 30` |
| "drop Google Jobs" / "ATS only" | remove `"google_jobs"` from `boards_enabled` |
| "ATS only" | `boards_enabled = ["greenhouse", "lever", "ashby", "workable", "smartrecruiters"]` |
| "salary floor 160k" / "minimum 160,000" | `salary_floor = 160000` |
| "exclude Amazon and Meta" | append to `exclude_companies` |
| "skip jobs that need clearance" | append "clearance" to `exclude_keywords` |
| "include stretch roles" | `include_stretch_roles = true` |
| "only remote" | `remote_preference = "remote_only"`; may also imply `locations` update |
| "add Boston" | append to `locations` |
| "use Harvard template" | `resume_template = "harvard"` |
| "auto-retry" | `auto_retry_on_failure = true` |
| "reset to defaults" | copy from `assets/settings_defaults.json` |

Always confirm the changes in plain English and save:

```
Updated:
  - Freshness: 24 → 48 hours
  - Excluded companies added: Amazon, Meta

Saved. Run /fats to start a new hunt with these settings.
```

## Scope of settings changes

Settings changes don't retroactively affect a finished hunt. If the user has a CSV from an earlier hunt and changes `salary_floor`, the old CSV stays as-is. The new floor applies to the next `/fats-new-hunt`.

However, if the user is mid-pipeline (e.g., Stage 3 approved but Stage 4 not yet run), changing settings invalidates the approved plan and forces a re-run of Stage 3 before Stage 4. Tell the user:

> Your search plan used the old settings. Rebuild the plan with the new ones? (yes/no)

If yes, redo Stage 3 with updated settings.

## Remote preference values

`remote_preference` is an enum with these meanings:
- `"onsite_only"` — only match jobs requiring daily office presence in one of user's locations
- `"hybrid_ok"` — onsite + hybrid, but not fully remote
- `"hybrid_or_remote"` — hybrid + fully remote, but not pure onsite
- `"remote_only"` — fully remote only
- `"any"` — no filter

## Remote region (for `remote_only` / `hybrid_or_remote`)

If user's preference includes remote, also capture which remote regions they accept in `locations`. Common values:
- `"Remote - US"` / `"Remote - United States"`
- `"Remote - North America"`
- `"Remote - EU"`
- `"Remote - Global"` / `"Remote - Worldwide"`

If a job is posted as "Remote - Europe" and user only accepts "Remote - US", the job is filtered out.

## Persistence

`/fats-settings` writes to `/mnt/user-data/outputs/fats-settings.json` and presents via `present_files` so the user has a downloadable copy for portability across sessions.

On the first turn of a new session, check for uploaded `fats-settings.json` the same way you check for `fats-profile.json` (see SKILL.md "Very first thing: resume state").
