"""AI-assisted dedup: blocking + candidate scoring.

Why not brute-force pairwise comparison:
  ~2,000 rows -> ~2,000,000 pairs. Even a cheap comparison per pair is too
  much to eyeball or LLM-score directly, per the assignment's own framing.

Approach:
  1. BLOCKING: group leads into candidate buckets using cheap, high-recall
     keys computed at ingest time (see app/cleaning.py):
       - phone_block_key (last 8 digits) - catches same person, different
         name spelling/formatting, same phone
       - email_domain - catches same-company duplicates worth comparing
       - name_block_key (first-initial + last-name + first company token) -
         catches typo'd names at the same company
     A pair only needs to share ONE of these keys to become a candidate -
     this keeps recall high (we're deliberately loose here; false positives
     get filtered by scoring, false negatives are unrecoverable).

  2. SCORING (the "embeddings + nearest-neighbor" step): within each block,
     candidates are compared using TF-IDF character n-gram vectors over a
     concatenated "name | company | email-localpart" string, then ranked by
     cosine similarity. Character n-grams (not word n-grams) are deliberate:
     they're robust to typos, transposed characters, and partial-name
     matches ("Wei Ming Malik" vs "W. Malik") in a way word-level tokens
     aren't, while still being just a vector representation + nearest-
     neighbor lookup - the same shape as a semantic-embedding approach, but
     with no model download / API cost. Swapping in a sentence-transformers
     or OpenAI/Anthropic embedding model later is a drop-in change to
     `_vectorize()` - the blocking and ranking logic is unaffected.

  3. CONFIDENCE: cosine similarity (0-1) is combined with a same-phone /
     same-email-domain boost, since those are strong independent duplicate
     signals that raw string similarity of names alone can't fully capture.

This does NOT auto-merge anything - it returns ranked candidate groups with
a confidence score and a short explanation, per the assignment's scope.
"""
from dataclasses import dataclass, field
from itertools import combinations
from typing import Dict, List

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.models import Lead

SIMILARITY_THRESHOLD = 0.55


@dataclass
class DupCandidate:
    lead_a_id: int
    lead_b_id: int
    confidence: float
    reasons: List[str] = field(default_factory=list)


def _comparison_string(lead: Lead) -> str:
    email_local = (lead.email or "").split("@")[0]
    parts = [lead.full_name or "", lead.company_name or "", email_local]
    return " | ".join(p.lower().strip() for p in parts if p)


def _build_blocks(leads: List[Lead]) -> Dict[str, List[Lead]]:
    blocks: Dict[str, List[Lead]] = {}
    for lead in leads:
        keys = set()
        # phone block
        if getattr(lead, "phone_normalized", None):
            digits = lead.phone_normalized
            if digits and len(digits) >= 6:
                keys.add(f"phone:{digits[-8:]}")
        if lead.block_email_domain and lead.company_name:
            keys.add(f"domain:{lead.block_email_domain}")
        if lead.block_name_key:
            keys.add(f"name:{lead.block_name_key}")

        if not keys:
            keys.add(f"unblocked:{lead.id}")  # isolated singleton block

        for k in keys:
            blocks.setdefault(k, []).append(lead)
    return blocks


def find_dedup_candidates(leads: List[Lead]) -> List[DupCandidate]:
    blocks = _build_blocks(leads)
    seen_pairs = set()
    candidates: List[DupCandidate] = []

    for block_key, members in blocks.items():
        if len(members) < 2 or len(members) > 200:
            # Skip oversized blocks (e.g. a very generic company token) -
            # a block this big means the key wasn't discriminating enough
            # to be a useful candidate generator; cap keeps this tractable.
            continue

        texts = [_comparison_string(l) for l in members]
        if not any(texts):
            continue

        vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), min_df=1)
        try:
            matrix = vectorizer.fit_transform(texts)
        except ValueError:
            continue
        sims = cosine_similarity(matrix)

        for i, j in combinations(range(len(members)), 2):
            a, b = members[i], members[j]
            pair_key = tuple(sorted((a.id, b.id)))
            if pair_key in seen_pairs:
                continue

            score = float(sims[i][j])
            reasons = []

            if a.email and b.email and a.email.strip().lower() == b.email.strip().lower():
                score = max(score, 0.97)
                reasons.append("identical email")
            if (
                a.phone_normalized
                and b.phone_normalized
                and a.phone_normalized[-8:] == b.phone_normalized[-8:]
                and len(a.phone_normalized) >= 6
            ):
                score = min(1.0, score + 0.25)
                reasons.append("matching phone number")
            if (
                a.company_name
                and b.company_name
                and a.company_name.strip().lower() == b.company_name.strip().lower()
            ):
                score = min(1.0, score + 0.05)
                reasons.append("same company")
            if score >= SIMILARITY_THRESHOLD and "name/company/email similarity" not in reasons:
                reasons.append(f"name/company/email similarity ({score:.2f})")

            if score >= SIMILARITY_THRESHOLD:
                seen_pairs.add(pair_key)
                candidates.append(
                    DupCandidate(
                        lead_a_id=a.id, lead_b_id=b.id, confidence=round(score, 3), reasons=reasons
                    )
                )

    candidates.sort(key=lambda c: c.confidence, reverse=True)
    return candidates


def group_candidates(candidates: List[DupCandidate]) -> List[dict]:
    """Union-find to merge pairwise candidates into clusters for display."""
    parent: Dict[int, int] = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    for c in candidates:
        union(c.lead_a_id, c.lead_b_id)

    clusters: Dict[int, List[DupCandidate]] = {}
    for c in candidates:
        root = find(c.lead_a_id)
        clusters.setdefault(root, []).append(c)

    result = []
    for root, pairs in clusters.items():
        member_ids = sorted({p.lead_a_id for p in pairs} | {p.lead_b_id for p in pairs})
        max_conf = max(p.confidence for p in pairs)
        all_reasons = sorted({r for p in pairs for r in p.reasons})
        result.append(
            {
                "lead_ids": member_ids,
                "confidence": max_conf,
                "reasons": all_reasons,
                "pair_count": len(pairs),
            }
        )
    result.sort(key=lambda g: g["confidence"], reverse=True)
    return result
