# Submission Notes

This file is separate from `README.md` on purpose: `README.md` documents the
project itself (setup, endpoints, design rationale) the way any repo README
would. This file is context for whoever's reviewing the *submission* —
process, tools used, and what I'd want to be asked about.

## How this was built

I used an AI coding assistant throughout, given the one-week/6-8hr scope and
my own time constraints this week. I want to be upfront about that rather
than have it come up awkwardly in a follow-up conversation.

What that looked like in practice:
- I explored the seed data and the assignment requirements myself first.
- I worked through the architecture and the two AI-feature approaches
  (dedup blocking+scoring, rules-first source extraction) with the
  assistant, including the reasoning for each tradeoff — documented in
  `README.md` under "Design decisions."
- The assistant wrote the bulk of the implementation; I reviewed it,
  verified it runs and passes its tests, and manually exercised every
  endpoint against the live server (not just trusting the code looked
  right) before submitting.
- I did not personally hand-write every line, and I want to be honest about
  that rather than imply otherwise if asked.

## Steps to run it

```bash
# 1. From the project root, create a virtual environment and install deps
python -m venv venv
./venv/bin/pip install -r requirements.txt

# 2. Start the API (loads data/leads_seed.csv into SQLite on first run)
./venv/bin/uvicorn app.main:app --reload
# API docs available at http://localhost:8000/docs

# 3. (optional) In a second terminal, serve the minimal frontend
cd frontend
python -m http.server 5500
# open http://localhost:5500 — API base URL is editable on the page

# 4. (optional) Run the test suite
./venv/bin/python -m pytest tests/ -v
```

Delete `leadflow.db` to reload the seed data from scratch on next startup.

## What I can speak to confidently in a follow-up conversation

- **Why blocking-before-scoring for dedup**, and why the blocking keys are
  deliberately permissive (high recall over high precision) — false
  positives get filtered at scoring, false negatives from a too-strict
  block are unrecoverable.
- **Why TF-IDF character n-grams instead of real embeddings** — this was a
  real engineering tradeoff (a `sentence-transformers`/torch install
  exceeded available disk space in the build environment mid-project), not
  the original plan. I can explain what would change if I swapped in real
  embeddings and why the blocking/ranking split would stay the same.
- **Why rules-first, LLM-fallback-second for source extraction**, and how
  the rules were tuned by actually inspecting which notes fell into
  "Other" after the first pass (599/2049 → 244/2049) rather than guessed
  upfront.
- **Why ingest-time dedup is strict (exact match only)** while the
  candidate-dedup endpoint is fuzzy — different consequences justify
  different confidence bars.
- The scope cuts (no auth, no real LLM API call activated, minimal
  frontend) and why each was reasonable given the stated out-of-scope list
  and time budget.

## What I'd genuinely want to spend more prep time on if asked to extend it

- Actually wiring the LLM fallback to a real API key and measuring how many
  of the remaining "Other" notes it resolves.
- Multi-word surname handling in name-splitting — currently a documented
  heuristic, not something I'd stand fully behind under scrutiny.
- Real embeddings for dedup, to see how much it actually improves match
  quality over the TF-IDF approach on this dataset.

## What's in the submission

- `README.md` — project documentation (setup, endpoints, design decisions)
- `app/`, `tests/`, `data/`, `frontend/` — the implementation
- This file
