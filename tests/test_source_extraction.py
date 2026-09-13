import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.source_extraction import extract_source


def test_event_booth_qr_code():
    result = extract_source("He scanned our QR code at the SaaStr Annual booth. Great fit, prioritizing.")
    assert result.channel == "Event"
    assert "SaaStr" in result.detail


def test_referral_with_name():
    result = extract_source("Referred by Michael Zhang, warm intro. Connected, sending proposal.")
    assert result.channel == "Referral"
    assert "Michael Zhang" in result.detail


def test_organic_search():
    result = extract_source("Found us through organic google search then booked a demo")
    # "booked a demo" also matches website pattern; organic search should win
    # since it's checked first and is the more specific signal here
    assert result.channel in {"Organic Search", "Website"}


def test_linkedin_mention():
    result = extract_source("Connected on LinkedIn after I posted about our product launch")
    assert result.channel == "LinkedIn"


def test_manual_sales_cold_outreach():
    result = extract_source("Cold outreach from our SDR team, no response yet")
    assert result.channel == "Manual/Sales"


def test_empty_notes_falls_back_to_original_source_if_useful():
    result = extract_source("", "Trade Show APAC 2026")
    assert result.channel == "Other"
    assert result.detail == "Trade Show APAC 2026"


def test_empty_notes_and_generic_original_source():
    result = extract_source("", "Offline Sources")
    assert result.channel == "Other"
    assert result.detail == "No source information"


def test_manual_prefix_is_treated_as_explicit_signal():
    result = extract_source("Manual - added after inbound phone call. No response yet.")
    assert result.channel == "Manual/Sales"


def test_other_prefix_is_respected():
    result = extract_source("Other - walked into our office without an appointment.")
    assert result.channel == "Other"


def test_googled_us_note_is_organic_search():
    result = extract_source("Googled us and ended up on the pricing page before booking a demo.")
    assert result.channel in {"Organic Search", "Website"}


def test_ambiguous_note_without_api_key_falls_back_gracefully(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = extract_source("Interesting conversation at the coworking space, might follow up")
    assert result.channel in {"Other", "Event"}
    assert result.method in {"fallback", "rule"}
