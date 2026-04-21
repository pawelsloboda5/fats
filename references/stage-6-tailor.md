# Stage 6 — Tailor resumes

## Goal

For each selected job, produce a tailored `.docx` and `.pdf` resume that:
1. Passes ATS parsing cleanly (single column, standard headings, no tables/icons/columns).
2. Hits 70-80% keyword match with the JD.
3. Reorders and reframes the user's real experience to foreground what the JD cares about.
4. **Never fabricates anything.** See `references/never-fabricate.md` — this is the non-negotiable core.

Output: one `.docx` and one `.pdf` per selected job, named `Resume - {Company} - {Role} - {YYYY-MM-DD}.docx` (and `.pdf`), saved to `/mnt/user-data/outputs/` and presented together via `present_files`.

## Pick the template

Before tailoring, ask the user once (not per job):

> For your resume template, pick one:
>
> **1. Clean Modern** — one-page, contemporary, Calibri 11pt. Default for most roles.
> **2. Harvard Classic** — traditional serif, heavier hierarchy. Good for law, finance, consulting, academia.
> **3. Mirror your original** — match the fonts, margins, and hierarchy of the resume you uploaded.

Use `ask_user_input_v0` if available. Store the pick in `fats-profile.json` under `resume_template` so you don't re-ask next session.

Template implementations are in `scripts/resume.py`:
- `build_clean_modern(profile, tailored_content, out_path)`
- `build_harvard(profile, tailored_content, out_path)`
- `build_mirror_user(profile, tailored_content, out_path, source_doc_path)`

All three emit ATS-safe output per `references/resume-templates.md`.

## The tailoring algorithm

For each job the user picked, run this loop:

### Step 1 — Extract JD keywords

Read the `full_jd` from the CSV row. Use the LLM to extract:

- **Hard skills** (tools, languages, platforms) — e.g., "Salesforce", "Python", "HubSpot", "SQL"
- **Soft skills** (named competencies) — e.g., "cross-functional leadership", "stakeholder management"
- **Domain keywords** — e.g., "B2B SaaS", "product-led growth", "ABM"
- **Seniority signals** — "manage a team of 4", "own end-to-end", "report to VP"
- **Required credentials** — degrees, certifications, clearances, visas

Prioritize keywords that appear in "Requirements," "Must-haves," or "Qualifications" sections. De-emphasize "nice to have" unless the user already has them.

Target list size: top 20-25 keywords.

### Step 2 — Match against profile evidence

For each JD keyword, check if the user's `profile.evidence` has a match. Three possible outcomes per keyword:

1. **Exact evidence exists** — e.g., JD says "Salesforce" and profile has `evidence.skills_evidence["Salesforce"] = ["bullet at Acme Corp 2021"]`. Free to use.
2. **Related evidence exists** — e.g., JD says "Salesforce Marketing Cloud" and user has evidence for "Salesforce" and "HubSpot". Can be used with reframing but not claimed as exact match.
3. **No evidence** — e.g., JD says "Marketo" and the user has never used it. **This keyword goes in `missing_keywords` and is NEVER added to the resume.** It's a gap, not an opportunity.

### Step 3 — Reframe existing bullets

For each work experience entry, look at the bullets and decide:

- **Keep as-is** — if the bullet already uses JD vocabulary and lands.
- **Reword** — keep the underlying fact, change wording to mirror JD terms. Example: user wrote "Ran digital campaigns for B2B software companies." JD says "Demand generation for B2B SaaS." Rewrite: "Led demand generation campaigns for B2B SaaS clients." Same fact, JD vocabulary.
- **Elevate a detail** — the user's original bullet buried a relevant detail. Pull it forward. Example: "Managed marketing ops (tools, reporting, lead routing)." → "Owned marketing ops stack including Salesforce CRM, HubSpot automation, and lead routing logic." Only valid if the user's source docs or LinkedIn mention those tools.
- **Drop** — if the bullet is irrelevant to this JD, drop it from the tailored version. (Don't literally delete from the canonical profile; just omit.)
- **Reorder** — put JD-relevant bullets first in each role.

Never invent a new bullet from whole cloth. Every bullet must trace back to the profile's `evidence` or `experience[].bullets`.

### Step 4 — Write a tailored summary

The top-of-resume summary changes for every job. Template:

```
{Years} years driving {top JD-aligned function} for {industries user has worked in}.
{Concrete user accomplishment from evidence that matches JD}.
Known for {soft skill that matches JD}.
```

Example:
> 8 years driving demand generation for B2B SaaS companies. Built marketing ops stack that cut lead routing time 70% at TechCorp. Known for cross-functional partnership with product and sales.

Rules:
- Exact numbers must come from the profile's `quantified_achievements`. If not there, don't make them up.
- Industry terms must be ones the user has actually worked in.
- Soft-skill phrasing can mirror the JD if the user has evidence.

### Step 5 — Build the skills section

Three subsections, reordered per JD:

1. **Core competencies** (picked from JD's top 5-8 skills where user has evidence)
2. **Tools & platforms** (tools the user has used, ordered by JD emphasis first)
3. **Additional** (remaining relevant skills)

Never include a tool/skill/platform without evidence.

### Step 6 — Render to .docx and .pdf

Call the template's build function twice — once per output format. The same function dispatches on the file extension:

```python
from scripts.resume import build_resume
build_resume(template, profile, tailored_content, out_docx_path)  # .docx
build_resume(template, profile, tailored_content, out_pdf_path)   # .pdf
```

The `.docx` is rendered via `python-docx`; the `.pdf` is rendered directly via `reportlab` using the bundled OFL fonts in `assets/fonts/` (EB Garamond for Harvard, Carlito for Clean Modern). There is no `docx → pdf` conversion step — no MS Word, no LibreOffice, no system libraries needed. The two outputs are independent renderings of the same tailored content.

### Step 7 — Self-check for fabrication

Before presenting, run `scripts/resume.py` `fabrication_check(tailored_content, profile)`. It checks every bullet, skill, and number in the tailored content for traceability back to profile.evidence or profile.experience. Any hits where the evidence is missing get flagged.

If anything is flagged, STOP and tell the user — don't silently present a resume with a fabrication warning hidden in it. Example:

> **Before I share the resume, flagging this:** the tailored version I drafted mentions "led a team of 8" in the Acme Corp bullet, but your profile says "4 direct reports." I'll change it to 4. [Revise and re-run check.]

### Step 8 — Build a keyword match report

For each tailored resume, also generate a short companion report showing:
- Matched keywords (and where on the resume they appear)
- Missing keywords (and an honest assessment: "you don't have Marketo on your resume because you haven't used it. If you've used it informally, tell me and I'll add it with evidence.")
- Estimated ATS match % (share of JD's top 20 keywords present on the resume)

Save as `Resume Match Report - {Company} - {Role}.md` in `/mnt/user-data/outputs/`.

## Batch across all picked jobs

Run Steps 1-8 once per picked job. For top 5, that's 5 resume docx + 5 PDFs + 5 match reports = 15 files.

Naming:
- `Resume - Segment - Senior Marketing Manager - 2026-04-20.docx`
- `Resume - Segment - Senior Marketing Manager - 2026-04-20.pdf`
- `Resume Match Report - Segment - Senior Marketing Manager - 2026-04-20.md`

Use `present_files` with all files in one call so the user gets them in a single presentation.

## Progress updates during the loop

Resume tailoring is slow (a minute or two per job for the LLM work plus rendering). Tell the user what's happening:

> Tailoring resumes for your top 5 jobs…
> - Segment / Senior Marketing Manager — done ✓
> - Vercel / Senior Growth Marketing Manager — done ✓
> - Figma / Senior Marketing Manager, B2B — in progress…
> - Clearbit / Director, Demand Generation — queued
> - Retool / Senior Product Marketing Manager — queued

## Wrap-up summary

When all resumes are done, give the user:

```
Done. 5 resumes ready in your output folder.

- Segment: 92% keyword match (18/20 JD keywords on resume)
- Vercel: 88% match
- Figma: 85% match (missing "Marketo" — you've never used it. Want me to flag it as "learning" or leave it off?)
- Clearbit: 79% match
- Retool: 90% match

Each resume has a companion match report explaining what I reordered and what I changed. Open any of them in Word or Google Docs — they're single-column, standard headings, and should parse cleanly in any ATS.

Want me to tailor resumes for more jobs from the CSV, or are you done for this round?
```
