"""Extract a structured {channel, detail} from free-text Notes.

Approach: rules/keyword-pattern pass first, LLM fallback second (only if
ANTHROPIC_API_KEY is set in the environment - otherwise falls back to a
"Other" / low-confidence rule result, never crashes).

Why rules-first rather than LLM-first:
  - Cost/latency: an LLM call per lead at ingest time is unnecessary when a
    large fraction of notes contain unambiguous, high-signal phrases
    ("scanned our QR code", "booked a demo via our website", "referred by").
    Regex on these is instant and free.
  - Determinism: rules are testable and auditable; for a CRM feature this
    matters (a rep should be able to see *why* a lead was tagged a channel).
  - The LLM fallback exists for the genuinely ambiguous remainder (vague
    notes, unusual phrasing) where a pattern match would be unreliable -
    that's where the marginal cost of a model call is actually justified.

This run does NOT use a paid LLM call (see README) - the fallback path is
implemented but stubbed to return a rule-based best-guess when no API key is
configured, so the endpoint always returns a usable result.
"""
import os
import re
from dataclasses import dataclass
from typing import Optional

VALID_CHANNELS = {
    "Website",
    "Event",
    "LinkedIn",
    "Organic Search",
    "Referral",
    "Manual/Sales",
    "Other",
}


@dataclass
class ExtractionResult:
    channel: str
    detail: str
    method: str  # "rule" | "llm" | "fallback"


# Explicit literal prefixes some reps use when logging notes manually
# ("Manual - added after inbound phone call", "Other - walked into our
# office"). These are the highest-confidence signal available and are
# checked before any pattern-matching.
_PREFIX_RULES = [
    (re.compile(r"^\s*Manual\s*-", re.I), "Manual/Sales"),
    (re.compile(r"^\s*Other\s*-", re.I), "Other"),
]

# Ordered rule list: (compiled pattern, channel)
_RULES = [
    (
        re.compile(r"\bscann?ed\b.*?\bQR\b|\bbooth\b|\btrade ?show\b|\bconference\b|\bexpo\b|\bmet (?:him|her|them) at\b",
                   re.I),
        "Event",
    ),
    (
        re.compile(r"\blinkedin\b", re.I),
        "LinkedIn",
    ),
    (
        re.compile(r"\breferr(ed|al)\b|\bintro(duced|duction)?\b.*\bby\b|\bwarm intro\b", re.I),
        "Referral",
    ),
    (
        re.compile(r"\bgoogled us\b|\borganic\b.*\bsearch\b|\bgoogle search\b|\bfound us (on|through) google\b|\bseo\b",
                   re.I),
        "Organic Search",
    ),
    (
        re.compile(
            r"\bbooked a demo\b.*\b(website|site|form)\b|\bfilled out\b.*\bform\b|\bcontact form\b"
            r"|\bwebsite\b.*\b(sign ?up|demo|form)\b|\b(book-a-demo|pricing|product tour|homepage|comparison-vs-\S+) page\b"
            r"|\bclicked a (google )?ad\b.*\bbook",
            re.I,
        ),
        "Website",
    ),
    (
        re.compile(
            r"\bcold (call|email|outreach)\b|\bsales rep\b|\breached out to\b|\bprospected\b"
            r"|\bmanually (added|entered)\b|\binbound phone call\b|\bwalked into our office\b",
            re.I,
        ),
        "Manual/Sales",
    ),
]

_EVENT_NAME_RE = re.compile(
    r"\bat (?:the )?([A-Z][\w&.\- ]{2,60}?)(?: booth| conference| event| expo|,|\.|$)"
)


def _extract_event_detail(text: str) -> str:
    m = _EVENT_NAME_RE.search(text)
    if m:
        name = m.group(1).strip()
        if "booth" in text.lower():
            return f"{name} — Booth"
        return name
    return "Event (unspecified)"


def _rule_based(text: str) -> Optional[ExtractionResult]:
    for prefix_pattern, channel in _PREFIX_RULES:
        if prefix_pattern.search(text):
            detail = text.split("-", 1)[1].strip() if "-" in text else channel
            return ExtractionResult(channel=channel, detail=detail, method="rule")

    for pattern, channel in _RULES:
        if pattern.search(text):
            if channel == "Event":
                detail = _extract_event_detail(text)
            elif channel == "Referral":
                m = re.search(r"referred by ([A-Z][\w .\-]{2,40})", text, re.I)
                detail = f"Referred by {m.group(1).strip()}" if m else "Referral (source unspecified)"
            elif channel == "LinkedIn":
                detail = "LinkedIn outreach/inbound"
            elif channel == "Organic Search":
                detail = "Organic Google search"
            elif channel == "Website":
                detail = "Website form/demo booking"
            elif channel == "Manual/Sales":
                detail = "Sales-initiated / manual entry"
            else:
                detail = channel
            return ExtractionResult(channel=channel, detail=detail, method="rule")
    return None


def _llm_fallback(text: str) -> ExtractionResult:
    """Would call an LLM if ANTHROPIC_API_KEY is configured. Falls back to a
    conservative 'Other' classification otherwise so the pipeline never
    blocks on missing credentials."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return ExtractionResult(
            channel="Other",
            detail=(text[:80] + "...") if len(text) > 80 else text or "No notes available",
            method="fallback",
        )
    try:
        import anthropic  # imported lazily; not a hard dependency

        client = anthropic.Anthropic(api_key=api_key)
        prompt = (
            "Classify this CRM lead note into exactly one channel from: "
            "Website, Event, LinkedIn, Organic Search, Referral, Manual/Sales, Other. "
            "Return strict JSON: {\"channel\": \"...\", \"detail\": \"...\"}.\n\n"
            f"Note: {text}"
        )
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=150,
            messages=[{"role": "user", "content": prompt}],
        )
        import json

        raw = resp.content[0].text
        raw = raw.strip().strip("`").replace("json\n", "")
        parsed = json.loads(raw)
        channel = parsed.get("channel", "Other")
        if channel not in VALID_CHANNELS:
            channel = "Other"
        return ExtractionResult(channel=channel, detail=parsed.get("detail", text[:80]), method="llm")
    except Exception:
        return ExtractionResult(
            channel="Other",
            detail=(text[:80] + "...") if len(text) > 80 else text or "No notes available",
            method="fallback",
        )


def extract_source(notes: Optional[str], original_source: Optional[str] = None) -> ExtractionResult:
    text = (notes or "").strip()
    if not text:
        # No notes to work with - fall back to Original Source if it's
        # non-generic, else Other.
        if original_source and original_source.strip().lower() not in {
            "", "offline sources", "unknown", "n/a",
        }:
            return ExtractionResult(channel="Other", detail=original_source.strip(), method="fallback")
        return ExtractionResult(channel="Other", detail="No source information", method="fallback")

    rule_result = _rule_based(text)
    if rule_result:
        return rule_result

    return _llm_fallback(text)
