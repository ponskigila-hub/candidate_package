import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.cleaning import clean_status, normalize_phone, parse_date, resolve_names, phone_block_key


def test_clean_status_normalizes_casing_and_whitespace():
    assert clean_status("New") == "New"
    assert clean_status("new") == "New"
    assert clean_status("NEW") == "New"
    assert clean_status(" New") == "New"
    assert clean_status("") is None
    assert clean_status(None) is None


def test_parse_date_handles_mixed_formats():
    assert parse_date("2026-06-02") is not None
    assert parse_date("6/4/2026") is not None
    assert parse_date("2026-05-20T00:00:00Z") is not None
    assert parse_date("not a date") is None
    assert parse_date("") is None


def test_resolve_names_prefers_explicit_first_last():
    first, last, full = resolve_names("Yuki", "Aina", None)
    assert (first, last, full) == ("Yuki", "Aina", "Yuki Aina")


def test_resolve_names_splits_full_name_when_only_full_given():
    first, last, full = resolve_names(None, None, "Wei Ming Malik")
    assert last == "Malik"
    assert first == "Wei Ming"
    assert full == "Wei Ming Malik"


def test_resolve_names_single_token_full_name():
    first, last, full = resolve_names(None, None, "Cher")
    assert first == "Cher"
    assert last is None


def test_resolve_names_all_missing_returns_none():
    assert resolve_names(None, None, None) == (None, None, None)


def test_normalize_phone_strips_non_digits():
    assert normalize_phone("+86 138 2424 7912") == "8613824247912"
    assert normalize_phone(None) is None
    assert normalize_phone("") is None


def test_phone_block_key_uses_last_eight_digits():
    key_a = phone_block_key("+86 138 2424 7912")
    key_b = phone_block_key("0138-2424-7912")  # same local number, no country code
    assert key_a == key_b
    assert phone_block_key("123") is None  # too short to be meaningful
