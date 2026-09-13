"""Normalization helpers for the messy CRM export.

Design decisions (documented here since they affect both the API and dedup):

- Name handling: some rows have Full Name only, some have First/Last only,
  some have both (occasionally inconsistent). We always derive a canonical
  `full_name` and best-effort `first_name`/`last_name`, preferring explicit
  First/Last when present (more structured) and falling back to splitting
  Full Name on whitespace (last token = last name, rest = first name). This
  is imperfect for multi-word surnames but is a reasonable, explainable
  default for a scoped exercise.
- Status: stripped of whitespace and title-cased for consistent filtering
  ("New", " New", "NEW", "new" -> "New").
- Dates: parsed with dateutil, which tolerates the mixed formats seen in the
  file (ISO, US slash format, ISO-with-time). Unparseable dates become None
  rather than raising, so a handful of bad rows don't kill the whole load.
- Phone: digits-only normalization for blocking (dedup) purposes. We keep
  the last 8 digits as the blocking key fragment, since country-code
  formatting is inconsistent (+86 138..., +33 6...) but the local number is
  usually stable across duplicate entries.
- Email domain: lowercased, used as one dedup blocking signal.
- We do NOT attempt to fix/guess missing values in sparse columns (Annual
  Revenue, GDPR consent, etc.) - they're irrelevant to this task's scope and
  guessing would fabricate data.
"""
import re
from datetime import datetime
from typing import Optional

from dateutil import parser as dateparser


def clean_status(raw: Optional[str]) -> Optional[str]:
    if not raw or not str(raw).strip():
        return None
    return str(raw).strip().title()


def parse_date(raw: Optional[str]) -> Optional[datetime]:
    if not raw or not str(raw).strip():
        return None
    try:
        return dateparser.parse(str(raw).strip())
    except (ValueError, OverflowError):
        return None


def normalize_phone(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    digits = re.sub(r"\D", "", str(raw))
    return digits or None


def phone_block_key(raw: Optional[str]) -> Optional[str]:
    """Last 8 digits of a normalized phone number, used for dedup blocking."""
    digits = normalize_phone(raw)
    if not digits or len(digits) < 6:
        return None
    return digits[-8:]


def email_domain(raw: Optional[str]) -> Optional[str]:
    if not raw or "@" not in str(raw):
        return None
    return str(raw).strip().lower().split("@")[-1]


def resolve_names(first: Optional[str], last: Optional[str], full: Optional[str]):
    """Return (first_name, last_name, full_name) with a canonical full_name
    always populated when any name data exists."""
    first = (first or "").strip() or None
    last = (last or "").strip() or None
    full = (full or "").strip() or None

    if first or last:
        canonical_full = " ".join(p for p in [first, last] if p)
        if not first and full:
            # Have last name + full name but no first: try to derive first name
            pass
        return first, last, canonical_full or full

    if full:
        parts = full.split()
        if len(parts) == 1:
            return parts[0], None, full
        return " ".join(parts[:-1]), parts[-1], full

    return None, None, None


def name_block_key(full_name: Optional[str], company: Optional[str]) -> Optional[str]:
    """Coarse blocking key: first letter of first name + last name (lowercased,
    alpha-only) + first alnum token of company. Deliberately loose - it's a
    *candidate generator*, not a match decision. False positives here are
    cheap (filtered out by scoring); false negatives are the real risk, so we
    keep this permissive.
    """
    if not full_name:
        return None
    tokens = re.sub(r"[^a-zA-Z\s]", "", full_name.lower()).split()
    if not tokens:
        return None
    last = tokens[-1]
    first_initial = tokens[0][0] if tokens[0] else ""
    company_key = ""
    if company:
        company_clean = re.sub(r"[^a-zA-Z0-9\s]", "", company.lower())
        company_tokens = [
            t for t in company_clean.split() if t not in {"inc", "co", "llc", "ltd", "corp", "group"}
        ]
        if company_tokens:
            company_key = company_tokens[0]
    return f"{first_initial}{last}|{company_key}"
