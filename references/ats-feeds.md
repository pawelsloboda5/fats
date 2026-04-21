# ATS feed endpoints

Public JSON feeds exposed by ATS providers, no auth required. These are how FATS hits job data for free and legally.

## Greenhouse

- **Pattern:** `https://boards-api.greenhouse.io/v1/boards/{company_slug}/jobs?content=true`
- **Response:** JSON with `jobs` array. Each job has `id`, `title`, `location.name`, `absolute_url`, `updated_at`, `content` (HTML description), `departments`, `offices`, `metadata`.
- **Notes:** `company_slug` is usually a lowercase version of company name without spaces, e.g. "segment" for Segment, "dbtlabs" for dbt Labs. Sometimes they're weirder (e.g. "stripe" is just `stripe`). Maintain the mapping in `assets/company_list_seed.json`.
- **Rate limit:** Generous but not unlimited. Keep to ~30 requests/minute per IP.
- **How to get `updated_at` → posted_date:** Greenhouse exposes `updated_at` but not posted_date directly. Use `updated_at` as a proxy. Jobs re-posted without changes keep the original `updated_at`.

## Lever

- **Pattern:** `https://api.lever.co/v0/postings/{company_slug}?mode=json`
- **Response:** JSON array of posting objects. Each has `id`, `text` (title), `categories.location`, `categories.team`, `categories.commitment`, `hostedUrl`, `descriptionPlain`, `createdAt` (Unix millis), `lists` (requirements, preferred, etc.).
- **Notes:** `createdAt` is the posting timestamp, used directly for freshness. `descriptionPlain` is clean text — no HTML parsing needed.
- **Rate limit:** Modest. ~60 requests/minute is safe.

## Ashby

- **Pattern:** `https://api.ashbyhq.com/posting-api/job-board/{company_slug}?includeCompensation=true`
- **Response:** JSON with `jobs` array. Each has `id`, `title`, `location`, `employmentType`, `publishedDate`, `jobUrl`, `compensation` (with `summaryComponents` containing salary if exposed), `descriptionHtml`, `descriptionPlain`.
- **Notes:** `publishedDate` is exact. Ashby often exposes comp ranges — capture them. `company_slug` is usually the company's Ashby subdomain (e.g., "notion" → `notion`).
- **Rate limit:** Lightweight. ~30 req/min.

## Workable

- **Pattern:** `https://apply.workable.com/api/v3/accounts/{account_id}/jobs` (POST with filters) OR `https://{subdomain}.workable.com/spi/v3/jobs` for subdomained accounts.
- **Response:** JSON with `results` array. Each has `id`, `title`, `full_title`, `shortcode`, `code`, `state` (published if live), `department`, `url`, `application_url`, `location`, `created_at`, `description`, `requirements`, `benefits`.
- **Notes:** Workable is less uniform than the others. Many companies are on subdomain-style URLs.
- **Rate limit:** ~30 req/min.

## SmartRecruiters

- **Pattern:** `https://api.smartrecruiters.com/v1/companies/{company_identifier}/postings`
- **Response:** JSON with `content` array. Each has `id`, `name` (title), `refNumber`, `releasedDate`, `location`, `company.name`, `customField`, `industry`, `department`, `jobAd.sections` (description, qualifications, additional).
- **Notes:** `company_identifier` is often the company name with no spaces, capitalized first letter (e.g., "Twitch", "Bosch"). Some companies use their legal name.
- **Rate limit:** Public feed allows ~60 req/min.

## ATS role coverage (heads-up to users)

Not every role type is well-covered by these feeds. Use this rough map when warning users in Stage 3:

**Well covered (tech-heavy ATS feeds):**
- Software engineer, data scientist, ML engineer, platform/devops
- Product manager, product designer, UX researcher
- Marketing (growth, content, PMM, demand gen) — at tech companies
- Sales (AE, SDR, CSM) — at tech companies
- Operations, People/HR, Finance — at tech companies

**Moderate coverage:**
- Legal, finance, BD roles at scale-ups
- Customer support, technical writing
- Healthcare-adjacent tech (digital health cos on these ATSes)

**Poor coverage (warn user, lean on Google Jobs):**
- Clinical / bedside nursing, physician, therapist
- Teaching (K-12), academic
- Trades (electrician, plumber, HVAC, welding)
- Retail, food service, hospitality
- Blue-collar manufacturing, warehouse
- Government / defense / clearance-required
- Traditional finance (big banks, insurance)
- Law firm partnership/associate roles
- Construction, real estate
- Most creative freelance (writing, illustration, music)

If the user's target roles fall predominantly in the "Poor coverage" list, Stage 3 should warn them that public ATS feeds won't help much and their results will mostly come from Google Jobs.

## Implementation

All five ATS parsers live in `scripts/ats_fetchers.py`. Each has a consistent interface:

```python
from scripts.ats_fetchers import parse_greenhouse, parse_lever, parse_ashby, parse_workable, parse_smartrecruiters

# Claude calls web_fetch(url) to get the JSON, then:
jobs = parse_greenhouse(fetched_json, company_slug, company_metadata)
# jobs is a list of normalized job records per the common schema in references/csv-schema.md
```

The parsers are pure — no network calls. Network is Claude's job via `web_fetch`; parsing is Python's job.
