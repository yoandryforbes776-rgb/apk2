from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.util import (
    key_fingerprint,
    mask_secret,
    model_equal,
    parse_retry_after,
    seconds_until_utc_midnight,
    split_provider_model,
    utc_day,
)


def test_parse_retry_after_variants():
    assert parse_retry_after(None) is None
    assert parse_retry_after("") is None
    assert parse_retry_after("30") == 30
    assert parse_retry_after("2.5s") == 2.5
    assert parse_retry_after("1m30s") == 90
    assert parse_retry_after("2 min") == 120
    assert abs(parse_retry_after("1500ms") - 1.5) < 1e-6
    assert parse_retry_after("1h") == 3600


def test_parse_retry_after_http_date_in_past_is_zero():
    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).strftime("%a, %d %b %Y %H:%M:%S GMT")
    assert parse_retry_after(past) == 0


def test_key_fingerprint_stable_and_short():
    a = key_fingerprint("groq", "sk-123")
    b = key_fingerprint("groq", "sk-123")
    assert a == b
    assert len(a) == 12
    assert key_fingerprint("other", "sk-123") != a


def test_mask_secret():
    assert mask_secret("") == ""
    assert mask_secret("abcdefghijklmnop").startswith("abcd")
    assert "…" in mask_secret("abcdefghijklmnop")
    assert "***" in mask_secret("short")


def test_model_helpers():
    assert split_provider_model("groq/llama-3.3-70b") == ("groq", "llama-3.3-70b")
    assert split_provider_model("llama-3.3-70b") == (None, "llama-3.3-70b")
    assert split_provider_model("meta-llama/Llama-3.3-70B-Instruct") == (
        "meta-llama",
        "Llama-3.3-70B-Instruct",
    )
    assert model_equal("groq/llama-3.3-70b", "llama-3.3-70b")
    assert not model_equal("llama-3.3-70b", "llama-3.3-70b-versatile")


def test_day_helpers():
    now = datetime.now(timezone.utc)
    assert utc_day(now.timestamp()) == now.strftime("%Y-%m-%d")
    remaining = seconds_until_utc_midnight(now.timestamp())
    assert 1 <= remaining <= 86401
