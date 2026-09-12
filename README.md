# Take-Home Assignment: AI-Assisted Mini Lead Management System

**Role:** AI Builder (Mid-Level)
**Time budget:** ~6–8 focused hours, spread over up to 1 week
**Format:** Take-home, submitted as a code repo (zip or GitHub link)

## Context

Our company is evaluating replacing HubSpot with an internal system for tracking marketing/sales leads.
This assignment is a **scoped-down slice** of that real project. You won't build the whole thing — just
enough to show us how you design data models, build a small API, and apply AI/LLM techniques to a
practical, messy, real-world problem (not a toy problem with clean inputs).

We've provided a synthetic (fake) dataset so you don't need any real integrations or credentials to start.
It's deliberately shaped like a raw CRM export rather than a clean sample table — see "About the dataset"
below before you start modeling it.

## Getting started

1. Unzip this package. You should have `README.md` (this file) and a `data/` folder containing
   `leads_seed.csv` and `website_form_submissions.json`.
2. Read "About the dataset" below, then skim `data/leads_seed.csv` yourself before writing any code —
   the columns and messiness are part of the problem, not an appendix.
3. Read through all of "What you're building" once before starting, so you can budget your ~6–8 hours
   across the 3 core pieces sensibly rather than over-investing in the first one.
4. Build, using whatever language/framework you're fastest in — there's no required stack (Python and
   Node are both fine, and so is anything else).
5. Write the README described under "Submission" as you go, not as an afterthought at hour 8.
6. Submit within 7 days — see "Submission" for exactly what to send and how.

If anything here is ambiguous, that's expected in places (see "About the dataset") — make a reasonable
call, document it, and move on. If you're genuinely stuck on what's in scope, email us; asking a good
scoping question is a positive signal, not a negative one.

## About the dataset

`data/leads_seed.csv` has just over **2,000 rows** and 22 columns, mirroring what a real HubSpot contacts
export looks like: most columns are irrelevant or entirely blank for every row (`Annual Revenue`, `GDPR
consent`, `Marketing contact status`, etc.), some are only populated for a handful of rows (`Job Title`,
`City`, `Lead Score`), and a number of rows use `Full Name` instead of `First Name`/`Last Name` (or vice
versa). Dates show up in mixed formats (`2026-06-02`, `6/4/2026`, `2026-05-20T00:00:00Z`), and `Lead
Status` casing/whitespace is inconsistent (`New`, `new`, `NEW`, `" New"`). The `Original Source` field is
sometimes blank or genuinely unhelpful (e.g. `"Offline Sources"` for an event lead) — the real story is
usually only in the free-text `Notes` column. None of this is a data bug to report back to us; it's the
starting condition. Deciding what to normalize, what to ignore, and how much cleaning effort is worth it
before you start on the AI tasks is part of what we're evaluating.

A meaningful fraction of the ~2,000 rows are duplicate or near-duplicate entries of someone already in the
file (re-entered with typos, a different name format, or reformatted contact details), and a smaller number
are genuinely different people who happen to share a company and a similar-sounding name — we're not
telling you the exact counts, since figuring that out is the point. At this size, an approach that eyeballs
the file or runs a full pairwise comparison across every record (~2,000² comparisons) won't be practical —
part of what we're evaluating is whether you reach for something that scales (blocking/candidate
generation before scoring, vectorized similarity, embeddings + nearest-neighbor search, etc.) rather than
brute-forcing it.

## What you're building

A small backend service (language/framework of your choice — Python and Node are both fine) that manages
a "leads" dataset and includes **two AI-assisted features**. A minimal frontend or CLI is fine; you do not
need a polished UI.

### 1. Lead store + API (core, ~2 hrs)

Load `data/leads_seed.csv` into storage (SQLite, Postgres, or even an in-memory store — your call, just
justify it in your README). Expose an API (REST is fine) with:

- `GET /leads` — list leads, with filtering by `status`, `owner` (Contact Owner), `country`, and a
  free-text `q` search across name/company/email
- `GET /leads/:id` — single lead detail
- `PATCH /leads/:id` — update status, owner, or notes
- `GET /leads/export` — CSV export of the current filtered view
- `POST /leads/ingest` — accepts a payload shaped like `data/website_form_submissions.json` entries and
  creates a new lead **or** updates an existing one if it's the same person (see dedup below)

### 2. AI-assisted lead deduplication (core, ~2–3 hrs)

The seed data has intentional duplicate/near-duplicate leads — same person entered more than once with
typos, formatting differences, or partial info (e.g. an email localpart that differs between entries, or a
company name with a different legal-suffix punctuation). Exact-match dedup on email won't catch all of
them, and running an LLM call over every possible pair isn't feasible at ~2,000 rows — you'll need to
narrow the candidate set first (e.g. block on normalized phone digits, email domain, or a cheap similarity
pre-filter) before applying a more expensive comparison to the surviving pairs.

Build a `POST /leads/dedupe-candidates` endpoint (or an offline script — your call) that returns groups of
likely-duplicate leads, ranked by confidence, using whatever approach you think is appropriate: embeddings
+ similarity, an LLM prompt-based comparison, fuzzy string matching, or a hybrid. Briefly justify your
approach in the README — we care more about your reasoning than which specific technique you pick, and
about how you kept it tractable at this scale.

You do **not** need to auto-merge leads. Surfacing candidate pairs with a confidence score/explanation is
enough.

### 3. AI-assisted source extraction (core, ~1–2 hrs)

Real lead source data is messy — see the `Notes` column in the seed data (e.g. `"Met him at the SFF booth,
scanned our QR code"` or `"Found us through organic google search then booked a demo"`), and don't assume
the `Original Source` column is trustworthy (it's often blank or too generic to be useful — see "About the
dataset" above). Write a function/endpoint that takes the raw text and extracts a structured result:

```json
{ "channel": "Event", "detail": "Singapore FinTech Festival 2026 — Booth QR Code" }
```

Channel should map to one of: `Website`, `Event`, `LinkedIn`, `Organic Search`, `Referral`, `Manual/Sales`,
`Other`. You can use an LLM call, a rules/regex pass, or a hybrid — again, justify the choice.

### 4. Basic dashboard endpoint (bonus, ~30–60 min)

`GET /dashboard` returning lead counts by status and by source channel. JSON is enough; a rendered chart is
a nice-to-have, not required.

## Explicitly out of scope (do not build these)

To keep this to one week, please **skip**: authentication/user roles, website analytics/GA integration,
webhook infra beyond the single ingest endpoint, full audit-log/activity-history UI, HubSpot data migration
tooling, and any production concerns (deployment, scaling, monitoring). If you have time left over, a short
"what I'd do next" note in the README is worth more than partial extra features.

## What we're evaluating

- How you model messy, real-world data and make reasonable tradeoffs under time pressure
- How you apply AI/LLM techniques to a genuinely ambiguous problem (dedup, extraction) rather than a
  leetcode-style prompt
- Code clarity and basic test coverage (a handful of meaningful tests, not 100% coverage)
- Judgment about scope — what you cut and why, documented in your README

## Submission

1. Make sure your `README.md` covers: how to run it, your design decisions (especially for dedup and
   source extraction), and what you'd do next with more time.
2. Include whatever tests you wrote — no minimum count, just enough to show you tested the ambiguous
   cases, not only the happy path.
3. If you used a paid LLM API, note which provider/model in your README and roughly what it cost you in
   credits. If you'd rather not spend personal money on API credits, a free-tier key, a local/open-source
   model, or a mocked LLM call are all completely fine — just say in your README which you used and why.
   We're evaluating your approach, not your spend.
4. Send us a GitHub repo link (make sure we have access) or a zip file, within **7 days** of receiving
   this assignment.

Questions welcome any time before you submit — email us. Asking a good scoping question is a positive
signal, not a negative one.
