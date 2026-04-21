# Stage 1 — Build the canonical profile

## Goal

Take everything the user has about themselves — resumes, LinkedIn, portfolio, GitHub, cover letters, past job descriptions, salary history, whatever — and merge it into one canonical profile JSON that every downstream stage reads from.

Output: `fats-profile.json` conforming to `assets/profile_schema.json`.

## The ingestion conversation

On the first turn of Stage 1, greet the user and ask for their materials. Use this script as a starting template and adapt to the user's tone:

> Welcome to FATS. I'll build one profile from everything you've got, then use it to find matching jobs and tailor your resume for each one.
>
> To get started, drop in whatever you have:
> - **Resume(s)** — any format, any version, old or new (I'll merge them)
> - **LinkedIn URL** (recommended) — I'll pull your full work history
> - **Portfolio or personal site URL** (optional)
> - **GitHub URL** (optional, if you're in tech)
> - **Any other docs** — cover letters, past job descriptions, performance reviews, bios
>
> Paste the URLs in your next message and attach the files. More is better — I'll reconcile any conflicts with you before finalizing.

Don't ask them to fill out a form. Don't ask for structured fields. Let them throw in what they have.

## Collecting the inputs

### Uploaded files

Check `/mnt/user-data/uploads/` for files the user attached. Typical things you might see:
- `.pdf` resumes — read with the pdf-reading skill or `pypdf`/`pdfplumber`
- `.docx` resumes — read with `python-docx`
- `.txt` or `.md` — read directly
- `.jpg`/`.png` — OCR only if user says it's a resume image (note you need tesseract; if unavailable, ask the user to resubmit as PDF or DOCX)

If the user uploads multiple resumes (common: an old one + a newer one), treat them as complementary, not competing. Merge union of experience with the newer version winning on conflicts.

### URLs

For each URL the user provides, use `web_fetch` to retrieve the content. Key sources:

- **LinkedIn profile** — `web_fetch` the public URL. Expect partial content (LinkedIn blocks a lot). Extract what you can: work history, education, skills, about section, headline. If the fetch returns mostly login-wall content, tell the user and ask them to paste the text of their LinkedIn about/experience sections directly.
- **Portfolio site** — `web_fetch` the top-level page. If it links to projects, fetch 2-3 of the most recent or most prominent. Extract project names, descriptions, tech used, outcomes.
- **GitHub** — `web_fetch` the profile page. Look at pinned repos, recent activity, bio. Pull the top 5 repos by stars/activity for their tech footprint.
- **Company bio/team page** — if the user gives you a "here's my current company's about page," fetch it for employer context.

If a URL fetch fails, say so and ask the user to paste the key content directly. Don't silently drop it.

### Text pasted in chat

The user may just paste text. Treat it as another source document. Don't be picky about format.

## Building the canonical profile

Use `scripts/profile.py` to do the actual merging and validation. The script takes a list of source documents and produces a schema-valid JSON. The schema is in `assets/profile_schema.json` — read it so you know what fields to fill.

Key fields the schema expects (abbreviated — see the schema for full):

```
{
  "name": "...",
  "contact": { "email", "phone", "city", "state_region", "country", "linkedin_url", "portfolio_url", "github_url", "other_urls" },
  "headline": "one-line current positioning",
  "summary": "2-4 sentence narrative",
  "years_experience_total": 0,
  "inferred_seniority": "entry | junior | mid | senior | staff | principal | manager | director | vp | c-level",
  "experience": [
    { "title", "company", "location", "start", "end", "current", "bullets": [...], "technologies": [...], "quantified_achievements": [...] }
  ],
  "education": [...],
  "certifications": [...],
  "skills": {
    "technical": [...],
    "tools": [...],
    "soft": [...],
    "languages": [...],
    "domains": [...]
  },
  "projects": [...],
  "publications_or_talks": [...],
  "clearances_or_licenses": [...],
  "preferences_hints": {
    "roles_mentioned": [],
    "industries_mentioned": [],
    "locations_mentioned": [],
    "salary_mentioned": null,
    "remote_mentioned": null
  },
  "source_docs": [
    { "type": "resume_pdf | linkedin | github | portfolio | user_pasted", "fetched_at": "...", "fingerprint": "..." }
  ],
  "evidence": {
    "skills_evidence": {
      "Python": ["bullet at Acme Corp 2021", "project FooBar"],
      ...
    }
  },
  "last_updated": "ISO timestamp"
}
```

The `evidence` block is important. For every skill, tool, and quantified claim in the profile, record *where it came from* (which bullet, which project, which source doc). Stage 6 needs this to enforce the never-fabricate rule — if a skill isn't in `evidence`, it can't be added to a tailored resume.

## Reconciling conflicts

Conflicts happen. A resume says the user left TechCorp in 2022, LinkedIn says 2023. Three titles across three versions. Don't silently pick — ask.

When you detect a conflict, collect all of them and batch them into one question:

> I noticed a few things that don't match across your documents. Quick checks before I finalize:
>
> 1. **TechCorp end date** — resume says "Jan 2022", LinkedIn says "Mar 2023". Which is right?
> 2. **Your current title** — resume says "Senior Engineer", LinkedIn says "Staff Engineer". Which do you use now?
> 3. **Phone number** — I saw two different numbers. Which should go on applications?

Use `ask_user_input_v0` if available for the multiple-choice ones.

## Inferring things the user didn't say

After merging, infer:

- **Total years of experience** — sum the durations of non-overlapping jobs, round to nearest half year.
- **Seniority level** — based on years, most recent title, and team/scope words in bullets ("led a team of 6", "architected", "managed P&L"). Be honest, not flattering.
- **Industry footprint** — fintech, healthtech, edtech, gov, agency, etc. Derived from company names and domain keywords.
- **Location** — their current city. If ambiguous, ask.
- **Role preferences** — if the summary says "seeking X," extract it.

All inferences go in `inferred_*` fields so downstream stages can tell them apart from user-stated facts.

## Finalize and confirm

Before moving to Stage 2, show the user a human-readable summary (not the JSON — the summary). Template:

```
Here's what I've got. Does this look right?

Name: Jane Doe
Current: Senior Marketing Manager at TechCorp (Washington DC, remote)
Seniority: Senior (8 years experience)
Core strengths: demand gen, paid media, marketing analytics, HubSpot
Top skills I'll use for matching:
  - Marketing ops (HubSpot, Salesforce, Marketo)
  - Paid media (Google Ads, LinkedIn Ads, Meta)
  - Content strategy, SEO
  - Team leadership (managed 4 direct reports)
Industries: B2B SaaS, fintech
Education: BS Marketing, University of Maryland (2016)

I'll use all of this to find jobs and tailor resumes. Anything to fix before we move on?
```

If they say it's good, save `fats-profile.json` to `/mnt/user-data/outputs/`, use `present_files`, and move to Stage 2.

If they say no, ask what to fix and loop.

## Edge cases

- **Career changer** — the user uploaded a resume for a field they want to leave. Ask directly: "Are you looking for more of the same, or switching? If switching, what direction?" Set `preferences_hints.roles_mentioned` accordingly.
- **Very sparse info** — only a LinkedIn URL, no resume. Fetch LinkedIn, extract what you can, then ask 3-5 pointed questions to fill critical gaps (current role, 2-3 strongest skills, target location).
- **Very rich info** — the user dumps 5 resumes, 3 URLs, and a cover letter pack. Don't truncate. Merge everything. If they have contradictory branding (different "headlines" across docs), ask which feels most current.
- **No resume at all** — offer to build one together. Walk through: work history (company, title, dates, top 3 accomplishments each), education, skills. This becomes the "user_pasted" source doc.

## What's persisted

At the end of Stage 1, two artifacts exist in `/mnt/user-data/outputs/`:

- `fats-profile.json` — the canonical profile
- `fats-profile-summary.md` — the human-readable version for the user to eyeball

Both should be presented via `present_files`.
