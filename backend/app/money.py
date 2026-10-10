"""Money helpers.

In the database, amounts are stored as INTEGER CENTS (749.00 -> 74900).
In the API, amounts are strings with exactly 2 decimals ("749.00").
We parse with Decimal, never float, to avoid rounding errors (0.1 + 0.2 != 0.3 with floats).
"""

import re
from decimal import Decimal

# Only plain amounts: digits, optionally a dot and 1 or 2 digits ("799", "799.5", "0.99").
# [0-9] (not \d) so only ASCII digits are accepted.
AMOUNT_PATTERN = re.compile(r"[0-9]+(\.[0-9]{1,2})?")


def to_cents(text: str) -> int:
    """Convert a money string like "749.00" or "79.5" to cents (74900, 7950).

    Only plain amounts are accepted (spaces around are ignored).
    Anything else raises ValueError: "-1", "+5", "1e2", "1_000", "5.", ".5",
    "799,00", "NaN", "10.999", "" ...
    """
    if not isinstance(text, str):
        raise ValueError("Amount must be a string")
    text = text.strip()
    if not AMOUNT_PATTERN.fullmatch(text):
        raise ValueError("Amount must look like 799 or 799.00 (no sign, at most 2 decimals)")
    return int(Decimal(text) * 100)


def from_cents(cents: int) -> str:
    """Convert cents to a string with exactly 2 decimals (74900 -> "749.00")."""
    return str((Decimal(cents) / 100).quantize(Decimal("0.01")))
