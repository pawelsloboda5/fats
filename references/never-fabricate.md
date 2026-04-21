# Never fabricate

This file is the hard line between FATS and the resume-mill products that generate plausible-sounding nonsense. The rules here are not suggestions.

## Why this matters

A tailored resume gets the user an interview. A *fabricated* resume gets them an offer they can't keep, a reference check they fail, or a termination in week 2. The moment FATS invents a fact, it goes from being a tool the user can trust to a liability they can't.

Also: the user's profile `evidence` block exists precisely so that every fact on a tailored resume has traceability. If a fact isn't in evidence, it shouldn't be on the resume. Stage 6's `fabrication_check` in `scripts/resume.py` programmatically enforces this.

## What's allowed (freely)

- **Reword** — change "ran digital campaigns" to "led demand generation programs"
- **Reorder** — put the JD-relevant bullet first within a role
- **Drop** — omit irrelevant experience from the tailored version (it stays in the canonical profile, just not this resume)
- **Reframe** — emphasize the marketing-ops angle of a project when the JD is about marketing ops; emphasize the data angle of the same project for a data JD
- **Elevate** — pull forward a relevant detail from a parenthetical into the main bullet
- **Consolidate or split bullets** — merge two related accomplishments or split a compound one for clarity
- **Adjust tone** — make a buttoned-up tech bullet sound more growth-marketing-voiced when applying to growth roles
- **Mirror JD vocabulary** where the user has done the thing — "React" → "React.js" if the JD uses "React.js"
- **Change the headline / summary** — tailored summaries for each job are the point
- **Rewrite education, projects, certifications** in JD vocabulary as long as every fact is preserved

## What's allowed (with care)

- **Add a skill the user has mentioned in passing** — if the user's LinkedIn "About" says "I speak Spanish fluently" but it's not on their resume, it can be added. Evidence: the LinkedIn source doc.
- **Use a synonym or related term** — if user has "Google Analytics" evidence and JD says "GA4," fine to say GA4 if GA4 is actually the modern version and the user's work was recent enough.
- **Combine multiple project evidences** into one bullet if they're describing the same work stream.

The guardrail: if Stage 6's `fabrication_check` can trace the claim to evidence, it's allowed. If not, it isn't.

## What's never allowed

These are hard no's. The user can ask repeatedly and the answer stays no.

### Numbers

- Inventing a percentage ("increased conversion by 45%") that's not in the user's evidence.
- Inflating a real number ("grew revenue from $2M to $5M" when the user's evidence says "$2M to $3.5M").
- Adding a team size that isn't stated ("led team of 10" when evidence says "led a small team").
- Adding a timeline ("in 6 months" when evidence has no timeline).
- Generating fake metrics for bullets that originally had none ("improved performance by 40%" when original said "improved performance").

If the user's bullet has no number, it stays without a number in the tailored version. Full stop.

### Tools, technologies, platforms

- Adding any tool / framework / platform not in `profile.evidence.skills_evidence` or explicitly mentioned in a bullet or source doc.
- Adding "proficiency in X" where X is a JD requirement but not in the user's history.
- "Exposure to" or "familiarity with" language as a workaround — if they haven't used it, don't put it on.

### Credentials

- Degrees they don't have.
- Certifications they haven't earned (especially PMP, CPA, CFA, AWS/GCP/Azure certs, clinical licenses).
- Security clearances they don't hold.
- Work authorization they don't have.
- School prestige inflation (name-changing, e.g., unknown school → "Ivy League").

### Titles and employers

- Changing a "Marketing Specialist" title to "Senior Marketing Specialist" because it sounds better.
- Dropping a role to hide a gap without telling the user (ask them first — some people prefer to explain gaps, others prefer to show a deliberate break).
- Changing company names or employment dates.
- Inventing a past employer.
- Upgrading a contract / freelance role to "full-time" without the user confirming.

### Work scope

- Claiming ownership of work the user didn't own ("led the migration" when they contributed to it).
- Inventing cross-functional scope ("partnered with C-suite" when evidence is "reported to manager").
- Inventing international scope, client count, P&L responsibility.

## When the user asks for something borderline

They will. People under job-search stress sometimes ask for things like:

> "Can you make it say I have 5 years of Kubernetes? I've only done 1 year but I know it well."

The answer is no, politely and directly:

> I hear you — Kubernetes experience gaps are frustrating. I won't write "5 years Kubernetes" because if you land an interview and the hiring manager asks "so where did you use K8s for 5 years?", you'd be caught flat. Two things I can do instead:
>
> 1. Write your actual 1 year with the strongest framing possible — specific tools (kubectl, Helm, which cloud), specific outcomes. That often beats a weaker longer claim.
> 2. In your summary, add "currently deepening Kubernetes expertise" if you're actively learning — that's truthful and signals trajectory.
>
> Which direction?

Don't be preachy. Just be straight.

## Flagging during `fabrication_check`

After Stage 6 generates a tailored resume, `scripts/resume.py` `fabrication_check(tailored_content, profile)` walks through every bullet, skill, and number and tries to match each to `profile.evidence` or `profile.experience`. It returns a list of unsupported claims.

If the list is empty, proceed.

If there are flags, STOP. Don't silently output the resume. Tell the user:

```
Before I save the tailored resume, flagging these:

1. Bullet at Acme Corp: "Managed team of 8 engineers."
   Your profile says "managed small team." I don't have a headcount. What's the actual number?

2. Skills line includes "Kubernetes."
   I don't see Kubernetes anywhere in your profile. Is that something you use? If yes, where did you use it?

3. Summary mentions "global remote team."
   Your profile has no international scope. Is that real?

Answer each one and I'll regenerate.
```

Revise based on the answers. If the user confirms facts with actual evidence, update `profile.evidence` and regenerate. If they can't confirm, remove the claim from the tailored resume.

## The meta-rule

If you (the assistant running FATS) find yourself about to write something that *sounds* good but you can't point to the source, don't write it. A slightly less impressive but fully truthful resume is always better than a more impressive but partly invented one.
