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

  "models": {
    "orchestrator": "opus",
    "search_agent": "haiku",
    "resume_agent": "sonnet"
  },
  "concurrency": {
    "search_agents": 5,
    "resume_agents": 5
  },

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

## Model selection (`models`)

`models.orchestrator`, `models.search_agent`, and `models.resume_agent` name the three tiers of the FATS model stack. The orchestrator tier is the top-level Claude that reads SKILL.md and routes the 6 stages; the other two tiers drive the parallel subagents dispatched in Stage 4 (Hunt) and Stage 6 (Tailor). The orchestrator reads all three values before fan-out and passes the worker tiers through to each subagent call. The full dispatch mechanics live in `references/subagents.md`; this section only covers the user-facing settings surface.

### `models.orchestrator`

- **Controls**: which Claude model runs the top-level FATS orchestrator — the Claude that reads SKILL.md, routes between the 6 stages, aggregates subagent results, and enforces the never-fabricate doctrine.
- **Valid values**: `"haiku"`, `"sonnet"`, `"opus"`.
- **Default**: `"opus"`.
- **Honest caveats — this is a declared preference, not a hard control.** On **claude.ai** browser skills, the orchestrator model is whatever the user's Claude plan + model picker says it is for that chat. The skill cannot override the browser session's model; `models.orchestrator` here is a documentary recommendation only. On **Claude Code**, the user sets the orchestrator model via `/model <name>` *before* starting the /fats session. The skill can suggest ("for Balanced or Premium, run `/model opus` before /fats") but again cannot force it mid-session. We keep the key in settings because (a) Quality Mode presets reference it, (b) it signals intent clearly to returning users, and (c) future Agent SDK or skill runtime versions may expose programmatic orchestrator control — at which point this value becomes authoritative without a schema change.
- **Cost/latency note**: Opus orchestrator is slower per turn and pricier than Sonnet, but stage-gating, ambiguous-signal handling, and fabrication policing noticeably improve on complex profiles (multi-industry career pivots, senior/exec roles, messy uploaded artifacts). Resume quality compounds when the router is smart — a well-routed Sonnet resume subagent beats a poorly routed Opus one. Downgrade to Sonnet (Fast mode) for straightforward hunts where the router's job is mostly sequencing; stay on Opus (Balanced / Premium) when any stage might need judgment the worker tiers can't provide.

### `models.search_agent`

- **Controls**: which model runs the per-source search subagent in Stage 4 (one subagent per ATS feed or query slice).
- **Valid values**: `"haiku"`, `"sonnet"`, `"opus"`.
- **Default**: `"haiku"`.
- **When to change**: search-agent work is mostly JD extraction, freshness filtering, and light normalization — a small-context, pattern-matching task. Haiku handles it cleanly and is the fastest and cheapest tier. Upgrade to Sonnet if the user is hunting in a niche where role-title matching needs more judgment (e.g., atypical industry vocabulary, multilingual postings). Opus is almost never justified here; the search agent's ceiling is set by input quality, not model smarts.

### `models.resume_agent`

- **Controls**: which model runs the per-job tailoring subagent in Stage 6. That's keyword extraction, bullet reframing, summary writing, and the fabrication self-check.
- **Valid values**: `"haiku"`, `"sonnet"`, `"opus"`.
- **Default**: `"sonnet"`.
- **When to change**: downgrade to Haiku only for mass low-stakes hunts (e.g., exploratory batch of 20+ jobs where the user is screening, not committing). Upgrade to Opus when the user is applying to a short list of high-priority roles and wants the tightest possible bullet reframing and summary craft.

### Cost implications

Per-token pricing follows `haiku < sonnet < opus`, and the gap is not small — Opus is materially more expensive per token than Sonnet, which is materially more expensive than Haiku. Concrete implication: switching `resume_agent` from `"sonnet"` to `"opus"` for a 10-job tailor batch is the biggest cost lever in FATS. It's still a reasonable choice for a final top-3 polish pass, but the user should know they're opting into premium pricing. Orchestrator surfaces a confirmation prompt when `resume_agent == "opus"` and the tailor queue is larger than 10 jobs — see `references/subagents.md` "Cost guardrails".

Exact prices drift; don't quote dollar figures. Quote the order of magnitude and let the user decide.

## Concurrency (`concurrency`)

`concurrency.search_agents` and `concurrency.resume_agents` cap how many subagents run in parallel during Stage 4 and Stage 6 respectively. On Claude Code the orchestrator dispatches real subagents up to this cap; on claude.ai it caps the number of concurrent `web_fetch` / rendering tool calls issued in a single assistant turn.

### `concurrency.search_agents`

- **Controls**: max parallel search subagents (Claude Code) or parallel `web_fetch` calls per turn (claude.ai) during Stage 4.
- **Valid values**: integers 1–8 inclusive.
- **Default**: `5`.
- **When to change**: drop to `3` if the user sees API rate-limit errors ("429" or "throttled") during hunts. Raise to `6`–`8` only if the user is on a high-tier API plan and wants all 6 ATS sources running in fully separate subagents with room to spare.

### `concurrency.resume_agents`

- **Controls**: max parallel resume subagents during Stage 6 (Claude Code path only — on claude.ai, Stage 6 processes jobs serially regardless of this value; see `references/subagents.md`).
- **Valid values**: integers 1–8 inclusive.
- **Default**: `5`.
- **When to change**: drop to `2`–`3` for large batches to avoid rate limits if `resume_agent` is set to Sonnet or Opus. Raise above `5` only if the user is tailoring many jobs on a high-tier plan and has confirmed no throttling.

### Cost implications

Concurrency itself doesn't change cost per job — 10 jobs tailored with concurrency=1 and concurrency=5 cost the same in tokens. It only changes wall-clock time. Cost is driven by `models.*` and by how many jobs the user chose to tailor. The concurrency knob is purely a speed-vs-throttling tradeoff.

## Persistence

`/fats-settings` writes to `/mnt/user-data/outputs/fats-settings.json` and presents via `present_files` so the user has a downloadable copy for portability across sessions.

On the first turn of a new session, check for uploaded `fats-settings.json` the same way you check for `fats-profile.json` (see SKILL.md "Very first thing: resume state").
