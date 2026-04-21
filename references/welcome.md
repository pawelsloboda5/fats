# Welcome / Help content

This file is the README-style greeting FATS shows on any of:
- A brand-new session with no existing profile
- The user explicitly asks for help (`/fats-help`, `help`, `what can you do`)
- The user types `/fats` as their first action

The orchestrator should paraphrase this content — not dump it verbatim — adapting the greeting to the user's state. Returning users (profile exists) get a short "welcome back" with their name + a nudge to continue, NOT the full README.

---

## The full welcome (for brand-new users)

👋 **Welcome to FATS.**
**F.A.T.S. — because their ATS isn't reading your resume.**

Finally, an ATS on your side. Drop your resume, tell me what kind of role you want, and we'll find real, live postings and write tailored resumes that actually get through their filters. Zero fabrications, zero ghost jobs, zero six-week-old "we're still accepting applications" nonsense.

### What we'll do together

**Step 1 · Profile — you tell me who you are** *(~5 min)*
Drop your resume (PDF or Word), LinkedIn, portfolio, GitHub, or just paste text. More is better. I merge it all into one canonical profile so you never have to reintroduce yourself. Formatting doesn't matter.

**Step 2 · Roles — I propose target titles** *(~2 min)*
Six picks: 3 focused roles that match your background head-on, plus 3 adjacent pivots your experience credibly supports. Keep them, drop them, add your own.

**Step 3 · Search plan — I show my work first** *(~1 min)*
Before anything fires off, you see exactly which boards I'll hit, what queries I'll run, and roughly how many results to expect. You approve, or tell me what to change. No black boxes.

**Step 4 · Hunt — I pull live postings** *(~2-3 min)*
Real-time jobs from five public ATS feeds (Greenhouse, Lever, Ashby, Workable, SmartRecruiters) plus Google Jobs — which covers Indeed, LinkedIn, ZipRecruiter, and thousands of company sites. Default filter: posted in the last 24 hours. No archaeology.

**Step 5 · Review — ranked spreadsheet, not mush** *(~2 min to skim)*
A CSV with fit scores, salary (listed or inferred), ghost-job flags, matched and missing keywords, and the full JDs. You pick which ones deserve your time.

**Step 6 · Tailor — resumes built to pass their ATS** *(~1-2 min per job)*
Real `.docx` + `.pdf` files, ATS-safe formatting, reworded to mirror each job's language — without inventing a single thing you haven't actually done. Their filter is keyword-hungry; we speak keyword, truthfully.

**Total time: roughly 15–30 minutes** for a full run, depending on how many resumes you want tailored.

### What you can say to me

| Command | What it does |
|---|---|
| `/fats` | Start a new hunt, or pick up where you left off |
| `/fats-healthcheck` | Self-test the skill *(recommended on first install, 3 seconds)* |
| `/fats-new-hunt` | Skip ingest, use your existing profile to find fresh jobs |
| `/fats-profile` | View or edit what I know about you |
| `/fats-settings` | Change filters: location, salary floor, which boards, etc. |
| `/fats-status` | Show which stage you're at and what's next |
| `/fats-help` | Show this message again |
| `/fats-reset` | Wipe everything and start over |

You don't have to type commands. Saying *"help me find a marketing job"* or *"tailor my resume for this Stripe posting"* works too — I'll route you to the right step.

### Ground rules

🎯 **No fabrications. Ever.** Every skill, number, team size, credential, and claim on your tailored resume has to trace back to your real profile. If your resume says *"managed a small team,"* I won't upgrade it to *"managed 12 engineers."* Real work beats invented work — their filters sniff out the rest later, in interviews.

👀 **You see the plan before I run it.** What I'm about to search, what I'm about to write — you steer before anything saves. Stage 3 is a dry-run on purpose.

📢 **I fail loud.** If a board is down or a feed returns garbage, I say so. You won't get a CSV of 3 jobs dressed up as 20.

💾 **Your work persists.** Profile, settings, CSV, resumes — all saved to your outputs folder. Come back next week; we pick up exactly where we left off.

### What I can't do *(yet)*

- ❌ **Auto-apply** — you still click Apply and submit each one yourself. We don't touch their form.
- ❌ **Cover letters** — not in this skill. Roadmap.
- ❌ **Interview prep or mock interviews** — different workflow.
- ⚠️ **Roles outside tech-heavy ATSes** — trades, bedside healthcare, K-12, government contracting, law-firm associates — public feeds skew tech, so you'll lean on Google Jobs. Still works; just narrower.

### Ready?

- 🚀 **New here?** → Run `/fats-healthcheck` first (3 seconds, confirms the install is sound), then `/fats` with your resume in hand.
- 🔄 **Already have a profile from last time?** → `/fats-new-hunt` jumps straight to fresh postings.
- ⚙️ **Want to tweak settings first?** → `/fats-settings`.
- 🤷 **Not sure?** → Just tell me what you're looking for. I'll figure out where to start.

---

## Short form (for returning users with a profile)

When a profile already exists, skip the README. Show something like:

> Welcome back, {name}. You left off at Stage {N} ({stage_name}). Want to:
>   - Pick up at Stage {N}
>   - Start a fresh hunt (/fats-new-hunt)
>   - Edit your profile (/fats-profile)
>   - Change settings (/fats-settings)

Use `ask_user_input_v0` if tappable buttons are available.

---

## Authoring notes for Claude

- Don't dump the whole README inside a single code block — paraphrase and format it naturally in chat
- Use the emojis that are in this file, sparingly — they help non-technical users scan
- Don't lean on jargon the user hasn't seen yet. First mention of "ATS" gets a one-line definition: *"the software employers use to sort and filter resumes before a human ever sees them — your tailored resume has to read cleanly for it to survive the first cut"*
- Keep the presented welcome roughly 400–500 words — long enough to actually explain, short enough to scan in 90 seconds
- End with the "Ready?" section — users need clear next actions, not an open "what would you like to do?"
- Voice: on the user's side, direct, confident. No corporate hedging, no snark. FATS is the ATS working *for* them.
