# Stage 2 — Propose target roles

## Goal

From the canonical profile, generate a short list of job titles that are (a) realistic fits for this person today and (b) a mix of "same trajectory" and "sideways/upward pivot." User confirms, edits, or adds their own.

Output: a `target_roles` array written into `fats-profile.json`, plus a saved version of the profile to `/mnt/user-data/outputs/`.

## Default proposal: 3 focused + 3 adjacent

**Focused (3 roles)** — the obvious next step from where they are. If they're a Senior Backend Engineer at a B2B SaaS, focused = Senior Backend Engineer, Staff Backend Engineer, Senior Software Engineer. Use the same seniority, same function, maybe one level up.

**Adjacent (3 roles)** — sideways or pivot moves that their experience credibly supports. For the same engineer: Platform Engineer, Developer Experience Engineer, Solutions Architect. Pivots should require <20% new skill acquisition to be credible.

**Stretch (1-2 roles, optional)** — only include if the user's `preferences_hints.roles_mentioned` contains something clearly ambitious or pivot-y. Flag these explicitly as "you'd be stretching on this one — probably 30%+ new skills, but worth a shot if it excites you."

If the user is a clear career changer (e.g., teacher → instructional designer, bartender → software), lead with the pivot target they stated and make the "focused" set be entry/junior-level postings in the new field. Don't waste their time showing them more of what they want to leave.

## How to choose titles

Read `scripts/profile.py`'s `propose_roles` helper — it does the LLM-free first pass based on skills, most recent title, years of experience, and industry. Then you (the model) refine:

1. Apply your knowledge of the current job market to prune titles that are dying ("Growth Hacker") or niche-to-the-point-of-unfindable.
2. Check that the roles span salary ranges the user likely wants. Don't propose all lateral-pay roles — include at least one that's a meaningful raise.
3. Use the exact title phrasing that job boards actually use. "Senior Software Engineer," not "Senior Engineer, Software." "Product Manager," not "Product Owner" (unless the user's in an Agile-heavy stack).
4. Include common seniority alternatives. If "Senior" fits, also add variants like "Sr." and include the one-level-up ("Staff") as a stretch option.

## Present it conversationally

Don't dump a JSON. Give a short narrative:

```
Based on your profile, here's where I'd hunt for jobs. I'll look for each of these across all the boards.

**Focused — clear next step:**
  1. Senior Marketing Manager
  2. Senior Growth Marketing Manager
  3. Marketing Lead

**Adjacent — your experience supports these without much stretch:**
  4. Director of Marketing (small-company version, not enterprise)
  5. Product Marketing Manager
  6. Demand Gen Manager

I'd skip: "Head of Marketing" (usually needs 12+ years) and "CMO" (ditto).

Want to keep all 6, drop any, add your own? Or just say "looks good."
```

## Accept user edits

Users can:
- Drop any role ("remove #4")
- Add their own ("add 'Brand Strategy Director'")
- Replace ("swap #3 for 'Marketing Operations Manager'")
- Broaden ("also include non-senior versions")
- Narrow to a specific company type ("only agency-side" or "only B2B SaaS")

Translate whatever they say into an updated `target_roles` array. Company-type or industry preferences go into `role_constraints` on each role:

```json
{
  "target_roles": [
    {
      "title": "Senior Marketing Manager",
      "category": "focused",
      "role_constraints": {
        "industries": ["B2B SaaS", "fintech"],
        "company_size_max": 500,
        "exclude_agencies": true
      }
    },
    ...
  ]
}
```

## Location and remote preference

This is also the stage where you MUST confirm location and remote preference, because the search plan (Stage 3) needs them. Ask as a single focused question:

> Before we search, two quick ones:
>
> **Location** — where do you want to work? (your current city / a specific other city / open to multiple / anywhere in US / anywhere globally)
>
> **Remote** — on-site only, hybrid OK, or remote preferred/remote only?

Use `ask_user_input_v0` for the remote question if tappable buttons are available. Save answers to `profile.job_preferences.locations` and `profile.job_preferences.remote_preference`.

## Seniority confirmation

You inferred seniority in Stage 1. Now confirm:

> I've got you pegged as a **Senior** (about 8 years). Should I also include **Staff-level** postings (a stretch but maybe worth a look) or stick to Senior?

## Finalize

Update `fats-profile.json` with:
- `target_roles` array
- `job_preferences.locations` array
- `job_preferences.remote_preference`
- `job_preferences.seniority_range`

Save the updated profile to `/mnt/user-data/outputs/fats-profile.json` and `present_files` it.

Then move to Stage 3.
