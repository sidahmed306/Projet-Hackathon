"""Tests for the money helpers (app/money.py)."""

import pytest

from app.money import from_cents, to_cents


@pytest.mark.parametrize(
    "text, cents",
    [
        ("749.00", 74900),
        ("749", 74900),
        ("79.5", 7950),
        ("39.99", 3999),
        ("0.01", 1),
        ("0", 0),
        ("0.00", 0),
        ("1899.00", 189900),
    ],
)
def test_to_cents_valid(text, cents):
    assert to_cents(text) == cents


@pytest.mark.parametrize(
    "text",
    ["-5", "-0.01", "10.999", "0.001", "abc", "", "12,50", "NaN", "Infinity", "1.2.3"],
)
def test_to_cents_rejects_invalid(text):
    with pytest.raises(ValueError):
        to_cents(text)


def test_to_cents_rejects_non_string():
    # A float like 0.1 is never exact, so we refuse it.
    with pytest.raises(ValueError):
        to_cents(0.1)


@pytest.mark.parametrize(
    "cents, text",
    [(74900, "749.00"), (7950, "79.50"), (5, "0.05"), (0, "0.00"), (189900, "1899.00")],
)
def test_from_cents(cents, text):
    assert from_cents(cents) == text


def test_round_trip():
    for text in ["749.00", "39.99", "0.01", "1249.00"]:
        assert from_cents(to_cents(text)) == text
