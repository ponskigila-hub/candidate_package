# LeadFlow — Mini Lead Management System

A scoped-down internal replacement for a HubSpot-style lead tracker: a FastAPI
backend over the provided seed data, plus two AI-assisted features (dedup and
source extraction).

## Running it

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/uvicorn app.main:app --reload
```

The seed CSV (`data/leads_seed.csv`) is loaded into a local SQLite database
(`leadflow.db`) automatically on first startup — delete that file to reload
from scratch. API docs (Swagger UI) are available at `http://localhost:8000/docs`
once running.

**Tests:**

```bash
./venv/bin/pip install -r requirements.txt  # includes pytest
./venv/bin/python -m pytest tests/ -v
```

29 tests, covering data-cleaning edge cases, source-extraction rules, and API
behavior (filtering, ingest/upsert, dedup, dashboard). Each test spins up a
fresh isolated SQLite DB (see `tests/conftest.py`), so they don't touch your
local `leadflow.db`.

## Endpoints

| Method | Path | Notes |
|---|---|---|
| GET | `/leads` | filter by `status`, `owner`, `country`, free-text `q` across name/company/email; paginated (`limit`/`offset`) |
| GET | `/leads/{id}` | single lead |
| PATCH | `/leads/{id}` | update `status`, `contact_owner`, `notes` |
| GET | `/leads/export` | CSV export of the current filtered view (same filter params as `/leads`) |
| POST | `/leads/ingest` | accepts a `website_form_submissions.json`-shaped payload; upserts on exact email/phone match |
| POST | `/leads/dedupe-candidates` | returns ranked groups of likely-duplicate leads |
| POST | `/leads/{id}/extract-source` | (re-)runs source extraction for one lead |
| GET | `/dashboard` | counts by status and by extracted source channel |

## Design decisions

### Storage: SQLite

~2,000 rows doesn't need Postgres. SQLite needs zero setup, gives real SQL
filtering (vs. hand-rolling query logic over an in-memory dict), and the
SQLAlchemy models are a one-line change away from pointing at Postgres if
this ever needed to run multi-process.

### Data cleaning (`app/cleaning.py`)

The CSV is genuinely messy, and cleaning choices affect both correctness and
the dedup/extraction results, so I made these explicit and testable rather
than ad hoc:

- **Names**: some rows have only `Full Name`, some only `First`/`Last`, a few
  have both (occasionally inconsistent). Explicit First/Last wins when
  present; otherwise `Full Name` is split on whitespace (last token = last
  name). Imperfect for multi-word surnames, but a defensible default for the
  scope of this exercise — documented as a known limitation.
- **Status**: stripped and title-cased, so `"New"`, `" New"`, `"NEW"`,
  `"new"` all normalize to `"New"` for filtering.
- **Dates**: parsed with `dateutil`, which tolerates the mixed formats in the
  file (`2026-06-02`, `6/4/2026`, `2026-05-20T00:00:00Z`). Unparseable dates
  become `None` rather than raising, so a handful of bad rows don't kill the
  whole load.
- **Phone**: normalized to digits-only; the *last 8 digits* are used as a
  dedup blocking key, since country-code formatting varies (`+86 138...` vs
  `0138-...`) but the local number is usually stable across duplicate
  entries.
- I did **not** attempt to backfill or guess values in sparse columns
  (`Annual Revenue`, `GDPR consent`, etc.) — out of scope, and guessing would
  fabricate data that isn't there.

### Dedup (`app/dedup.py`)

At ~2,000 rows, full pairwise comparison is ~2M pairs — not practical to
eyeball or run an LLM call over. The pipeline is:

1. **Blocking**: each lead gets 1+ coarse "block keys" computed at load time
   — last-8-digits of phone, email domain, and a loose
   first-initial+last-name+first-company-token key. A pair only needs to
   share *one* block to become a candidate. This is deliberately permissive
   (false positives are cheap — they get filtered by scoring; false
   negatives from an overly strict block are unrecoverable). Oversized
   blocks (>200 members — i.e. a key that turned out not to be
   discriminating) are skipped rather than compared exhaustively, to keep
   this tractable.
2. **Scoring**: within each block, leads are compared using **TF-IDF
   character n-gram vectors** (2–4 grams) over a `name | company |
   email-localpart` string, ranked by cosine similarity. This is the same
   *shape* as an embeddings + nearest-neighbor approach — a vector
   representation compared by similarity — but runs locally with no model
   download or API cost, and character n-grams are naturally robust to
   typos and partial-name matches (`"Wei Ming Malik"` vs `"W. Malik"`).
   Swapping in a real embedding model (sentence-transformers, or an
   API-based embedding) later is a one-function change (`_vectorize`/the
   `TfidfVectorizer` call) — the blocking and ranking logic is unaffected.
3. **Confidence**: cosine similarity is boosted for exact-match signals
   (identical email, matching phone suffix, identical company) since those
   are strong independent evidence that string similarity of names alone
   doesn't fully capture.

Verified on the full seed set: runs in ~1 second, surfaces 245 candidate
groups, spot-checked by hand — it correctly groups things like differently
formatted phone numbers, typo'd email localparts, and company names with
different legal suffixes (`"...and Co"` vs `"...Inc"` vs `"...Pte. Ltd."`)
under the same person. It does **not** auto-merge — it returns ranked
groups with a confidence score and reasons, for human review.

### Source extraction (`app/source_extraction.py`)

Rules/regex first, LLM fallback second — not LLM-first. Reasoning:

- **Cost/latency**: a large fraction of the `Notes` text contains
  unambiguous, high-signal phrases ("scanned our QR code," "referred by,"
  "booked a demo via the website"). Regex on these is instant and free; an
  LLM call per lead would be unnecessary overhead for the clear majority.
- **Determinism/auditability**: rules are testable and a rep can see *why*
  a lead got tagged a channel, which matters for a CRM feature.
- The LLM fallback path exists (and is fully wired — see `_llm_fallback` in
  `source_extraction.py`) for genuinely ambiguous notes, where the marginal
  cost of a model call is actually justified. **I did not use a paid LLM
  API for this submission** — no `ANTHROPIC_API_KEY` is set, so the fallback
  path returns a conservative `"Other"` classification with the raw note as
  the detail, rather than crashing or silently guessing. Setting that env
  var would activate the real LLM call (`claude-sonnet-4-6` via the
  `anthropic` Python SDK) with no other code changes.
- I iterated the rules against the actual data rather than guessing blind:
  initial pass classified 599/2049 leads as `"Other"`; inspecting those
  notes surfaced patterns I'd missed (explicit `"Manual - "` / `"Other - "`
  prefixes some reps use, `"Googled us and ended up on the pricing page"`
  phrasing, ad-click-to-demo notes), and adding rules for those brought it
  down to 244 — the remainder being genuinely ambiguous or explicitly
  tagged `"Other"`.

### Ingest dedup vs. candidate dedup — intentionally different strictness

`POST /leads/ingest` only auto-merges on an **exact** email or phone match.
The fuzzy/embedding-based dedup pipeline is for *surfacing* likely
duplicates for a human to review — I didn't want ingest to silently merge
two different people based on a fuzzy name/company similarity score.

## What I'd do next with more time

- Real embeddings (sentence-transformers or an API embedding model) instead
  of TF-IDF for dedup scoring, particularly for cross-language name
  variants the character-n-gram approach won't catch as well.
- A `/leads/dedupe-candidates/{group_id}/merge` endpoint so a reviewer can
  actually resolve a candidate group, not just see it.
- Better multi-word surname handling in name-splitting (currently a
  heuristic, documented as such).
- Wire up the LLM fallback for real against a subset of the "Other" bucket
  and measure how many of those 244 it actually resolves vs. how many are
  truly ambiguous.
- Pagination cursor instead of offset for `/leads` at larger scale.
- A minimal frontend (a table view with filter controls) — skipped per the
  "minimal frontend/CLI is fine" note in the assignment, but easy to bolt on
  given the API is already there.
