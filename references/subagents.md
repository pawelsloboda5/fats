# Parallel subagent dispatch — Stage 4 and Stage 6 playbook

Authoritative playbook for how the orchestrator Claude fans out work in Stage 4 (Hunt) and Stage 6 (Tailor). FATS supports two runtime paths: real subagents under Claude Code, and parallel tool-call fan-out under claude.ai. This file is the single source of truth for which path to take, what to dispatch, and how to aggregate results.

## Three-tier architecture

FATS v1.1.0 runs on three model tiers, each with a distinct job:

- **Orchestrator** (1 instance, default **Opus**). This is the top-level Claude reading SKILL.md. It routes between the 6 stages, holds conversation state, aggregates what the subagents return, renders `.docx` / `.pdf` via `scripts/resume.py`, and enforces the never-fabricate doctrine. The orchestrator also reads `settings.models.*` and decides which tier each subagent call runs on.
- **Search subagents** (up to N=5 in parallel, default **Haiku**). Dispatched in Stage 4 (Hunt). Each subagent owns one or two ATS sources — fetch feed, extract postings, normalize to the common schema, filter by freshness / location / exclude lists, return JSON. Small-context, pattern-matching work that Haiku handles cleanly.
- **Resume subagents** (up to N=5 in parallel, default **Sonnet**, upgradable to Opus via Quality Mode). Dispatched in Stage 6 (Tailor). Each subagent owns one job end-to-end — keyword extraction, bullet reframing, summary drafting, skills section, fabrication self-check — and returns a tailored content object that the orchestrator then renders.

Both subagent tiers are tunable per-hunt via Quality Mode or persistently via `/fats-settings`. The orchestrator tier is also declared in settings but is only partially under the skill's control at runtime: on **claude.ai** the orchestrator model is whatever the user's plan + model picker sets for the browser session, and the subagent tiers collapse to the parallel tool-call fallback described below. On **Claude Code** the orchestrator model is whatever the user selected with `/model` before starting the session, and subagent tiers are real `Task`-tool dispatches with per-call model selection. In both environments `models.orchestrator` is a declared preference more than a direct lever — see `references/settings.md` for the full caveats.

## Runtime detection

The orchestrator must decide at the start of Stage 4 (and again at Stage 6) whether it's running under Claude Code or claude.ai. The practical heuristic is a no-op probe of the `Task` tool:

- If `Task` (subagent dispatch) is callable, the orchestrator is running under Claude Code. Take the **real subagents** path.
- If `Task` is not available, the orchestrator is running under claude.ai browser skills. Take the **parallel tool calls** fallback path.

```pseudocode
def pick_dispatch_path():
    try:
        # No-op probe: try to reference the Task tool.
        # In Claude Code this resolves; in claude.ai it does not.
        probe = tool_exists("Task")
        if probe:
            return "claude_code_subagents"
    except ToolNotAvailable:
        pass
    return "claude_ai_parallel_toolcalls"
```

Do not ask the user which runtime they're on. The orchestrator detects once per hunt and commits. If detection is ambiguous, default to the claude.ai parallel-tool-call path — it works everywhere, it's just slower on Claude Code.

Log the detected path at the top of `fats-hunt-log.json` so forensics are possible later.

## Claude Code path: real subagents

Under Claude Code, the orchestrator can dispatch fresh-context subagents via the `Task` tool with per-call model selection. This is where the 5× speedup lives.

### Before Stage 4 (Hunt)

Read two settings values:
- `settings.models.search_agent` — model tier for each search subagent (`"haiku"` / `"sonnet"` / `"opus"`).
- `settings.concurrency.search_agents` — max concurrent subagents (integer 1–8, default 5).

### Stage 4 dispatch pattern

Six ATS sources are in scope: Greenhouse, Lever, Ashby, Workable, SmartRecruiters, Google Jobs. With `concurrency.search_agents = 5`, split the six sources across five subagents by combining the two smallest-yield feeds (typically Workable + SmartRecruiters) into one subagent. General rule: `ceil(sources / concurrency)` sources per subagent, biasing toward keeping the high-yield feeds (Greenhouse, Lever, Google Jobs) in dedicated subagents so their failure modes don't contaminate other work.

Each subagent prompt must be self-contained because subagents run with fresh context. Pass:
- The role targets and aliases (from the Stage 3 search plan)
- The profile excerpt relevant to search filtering (locations, remote preference, seniority range, salary floor, exclude lists)
- The ATS source list assigned to this subagent
- The freshness window and target count share
- The common job record schema (from `references/csv-schema.md`)
- An explicit instruction: return a JSON array of normalized job records, nothing else

### Before Stage 6 (Tailor)

Read two settings values:
- `settings.models.resume_agent` — model tier for each tailoring subagent.
- `settings.concurrency.resume_agents` — max concurrent subagents (integer 1–8, default 5).

### Stage 6 dispatch pattern

One subagent per job in the selected queue. Keep at most `concurrency.resume_agents` in flight at any time. When a subagent completes, dispatch the next queued job. If the user picked 5 jobs and concurrency is 5, everything runs in parallel and the batch finishes in one generation window.

Each subagent prompt must include:
- The profile (full `fats-profile.json`, not excerpted — Stage 6 needs evidence traceability)
- The single job record (title, company, `full_jd`, location, salary, ats_type)
- The chosen resume template (`clean_modern` / `harvard` / `mirror_user`)
- The fabrication rules from `references/never-fabricate.md` (inlined or summarized)
- The output contract: tailored content object, not rendered files — rendering happens in the main orchestrator after return, so the subagent only does LLM work

### Aggregation

The main orchestrator waits for all dispatched subagents to complete, then merges:
- **Stage 4**: concatenate job records from all search subagents, then dedupe across sources (by `job_id` + `company` + normalized `title`). Log per-source counts and failures.
- **Stage 6**: collect tailored content objects, render each to `.docx` and `.pdf` via `scripts/resume.py`, run `fabrication_check`, write match reports, `present_files` all outputs in one call.

## claude.ai fallback: parallel tool calls

Under claude.ai browser skills, the orchestrator does not have a subagent-dispatch API. The runtime does, however, execute multiple `tool_use` blocks from a single assistant turn concurrently. Use that.

### Stage 4 on claude.ai

Issue 5–6 parallel `web_fetch` calls in a **single assistant turn**, one `tool_use` block per ATS source. The runtime fans them out. The next assistant turn receives all results and parses / filters them together. Target: a single round-trip per ATS feed pass. If a source needs multiple pages (e.g., Google Jobs runs one query per target role), do each query pass as its own turn, but keep all queries within the pass parallel.

```pseudocode
# Turn N (single assistant message, multiple tool calls)
web_fetch(url=greenhouse_feed_url_1)
web_fetch(url=lever_feed_url_1)
web_fetch(url=ashby_feed_url_1)
web_fetch(url=workable_feed_url_1)
web_fetch(url=smartrecruiters_feed_url_1)
web_fetch(url=google_jobs_search_url_1)

# Turn N+1: parse all responses, filter, normalize, dedupe
```

This produces ~6× fan-out for the ATS-feed pass. Google Jobs typically needs N role-query passes, so that's N additional turns. Total Stage 4 wall-clock on claude.ai lands around 1–3 minutes depending on role breadth and feed sizes.

### Stage 6 on claude.ai

Resume tailoring is one logical LLM unit per job: keyword extraction → bullet reframing → summary → skills section → fabrication self-check. That chain runs in the orchestrator's own turn and cannot be farmed out to a subagent on claude.ai. Jobs are therefore **processed serially**.

Within a single job, the final rendering steps can still fire as parallel tool calls in one turn:

```pseudocode
# After LLM generation completes for job N:
# Single turn, parallel tool calls
code_execution(build_docx, tailored_content, out_path_docx)
code_execution(build_pdf, tailored_content, out_path_pdf)
code_execution(fabrication_check, tailored_content, profile)
```

Net: jobs serial, per-job rendering parallel. Expected user-facing pace: **~2 minutes per job on claude.ai** versus **~30 seconds per job on Claude Code** (where each job's LLM work also runs in parallel via a real subagent).

Be honest about these numbers in progress updates. If the user picked 5 jobs on claude.ai, the hunt message should quote "~10 minutes" not "~2 minutes" — anchored in the serial reality of the runtime.

## Quality Mode preset

Once per fresh hunt, immediately after Stage 1 (Profile ingest) completes and before Stage 2 (Role proposal) begins, ask the user:

> Pick a Quality Mode for this hunt:
> **1. Fast** (default) — search: haiku, resume: sonnet. Cheapest, fastest, solid quality.
> **2. Balanced** — search: sonnet, resume: sonnet. Smarter search filtering, same resume quality as Fast.
> **3. Premium** — search: sonnet, resume: opus. Best resume craft; materially more expensive per tailor.
> **4. Keep my saved settings** — use whatever `models.*` already holds.

Mapping:

| Preset   | `models.search_agent` | `models.resume_agent` |
|----------|-----------------------|-----------------------|
| Fast     | `haiku`               | `sonnet`              |
| Balanced | `sonnet`              | `sonnet`              |
| Premium  | `sonnet`              | `opus`                |
| Keep saved | (no change)         | (no change)           |

Apply the pick to the in-memory settings object for this hunt. Do **not** write back to `fats-settings.json` unless the user also says "and save this as my default". Power users override per-stage via `/fats-settings`; the preset is a one-shot convenience, not a settings-writer.

Fire this question exactly once per hunt. If the user is resuming a mid-pipeline hunt, skip the preset — they already picked one at the start.

## Cost guardrails

The orchestrator surfaces two confirmation prompts before committing to expensive runs.

### Opus + large tailor queue

If `settings.models.resume_agent == "opus"` **and** the selected tailor queue has more than 10 jobs, pause before Stage 6 dispatch and confirm:

> Heads up — you've got Opus selected for resume tailoring and 14 jobs queued. Opus is materially more expensive per token than Sonnet (order of magnitude, not a quote — pricing drifts). Options:
>  - Continue with Opus for all 14 (premium quality, premium cost)
>  - Switch to Sonnet for the batch (still excellent, much cheaper)
>  - Run Opus on the top 3 only, Sonnet on the rest

Wait for the pick. Don't quote dollar figures — pricing changes. Quote the order-of-magnitude framing and let the user decide.

### High concurrency

If `settings.concurrency.search_agents > 5` or `settings.concurrency.resume_agents > 5`, warn once per hunt:

> Running with concurrency=7 — on Claude Code this may trip rate limits depending on your plan tier. If you see throttling errors mid-hunt, drop to 3 in `/fats-settings` and re-run. On claude.ai this is a non-issue; the runtime caps effective concurrency on its end.

No confirmation required; just emit the warning and proceed.

## What NOT to parallelize

Some stages are single-unit reasoning tasks. No subagent dispatch, no parallel tool calls help. Do not try to fan these out.

- **Stage 1 — Profile ingest.** One synthesis pass over uploaded resume + LinkedIn + supporting docs. Orchestrator does this in its own context; parallelism would fracture the profile.
- **Stage 2 — Role proposal.** Single reasoning pass that proposes 3–5 target roles from the profile. One output, coherent.
- **Stage 3 — Search plan dry-run.** Single plan assembled from role targets + settings. User approves or edits; there's nothing to parallelize.
- **Stage 5 — Review CSV.** One pass over all Stage 4 raw results to dedupe, score, rank, and emit the CSV. Parallelizing this would fracture the ranking logic (each subagent would produce a partial ranking and merging ranked lists is its own problem). Keep it single-unit.

Only Stage 4 (Hunt) and Stage 6 (Tailor) benefit from fan-out.

## Failure handling

Fail-loud doctrine applies. Partial results beat silent drops.

### Claude Code subagent errors

If a dispatched subagent errors or returns empty:
1. Record the failure in `fats-hunt-log.json` with source/job, error type, message, and which model tier was used.
2. Continue aggregating successful subagents — do **not** fail the whole stage.
3. At stage end, surface the partial state to the user:

> Hunt finished with partial results:
>  - Greenhouse ✓ 42 jobs
>  - Lever ✓ 18 jobs
>  - Ashby ✗ subagent errored after 30s (timeout) — 0 jobs
>  - Workable + SmartRecruiters ✓ 12 jobs combined
>  - Google Jobs ✓ 47 jobs
>
> Total: 119 jobs. Retry Ashby only, or continue to Stage 5?

Offer retry **for failed slices only**, not a whole-stage rerun. Successful work is kept.

### claude.ai parallel tool-call errors

Same principle. If 2 of 6 `web_fetch` calls fail in the Stage 4 pass:
1. Log the failures.
2. Proceed to parse and normalize the 4 that succeeded.
3. Offer a one-turn retry of just the failed URLs.

### Stage 6 fabrication-check failures

A fabrication check failure is a **hard stop for that job**, not a silent drop. Surface it to the user per `stage-6-tailor.md` Step 7, fix, and re-render. Other jobs in the batch continue unaffected.
