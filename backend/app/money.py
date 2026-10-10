"""Money helpers.

In the database, amounts are stored as INTEGER CENTS (749.00 -> 74900).
In the API, amounts are strings with exactly 2 decimals ("749.00").
We parse with Decimal, never float, to avoid rounding errors (0.1 + 0.2 != 0.3 with floats).
"""

from decimal import Decimal, InvalidOperation


def to_cents(text: str) -> int:
    """Convert a money string like "749.00" or "79.5" to cents (74900, 7950).

    Raises ValueError if the text is not a number, is negative,
    or has more than 2 decimals.
    """
    if not isinstance(text, str):
        raise ValueError("Amount must be a string")
    try:
        value = Decimal(text.strip())
    except InvalidOperation:
        raise ValueError("Amount is not a number") from None
    if not value.is_finite():
        # Decimal accepts "NaN" and "Infinity": these are not amounts.
        raise ValueError("Amount is not a number")
    if value < 0:
        raise ValueError("Amount must not be negative")
    # The exponent tells how many decimals there are: "10.999" has exponent -3.
    if value.as_tuple().exponent < -2:
        raise ValueError("Amount must have at most 2 decimals")
    return int(value * 100)


def from_cents(cents: int) -> str:
    """Convert cents to a string with exactly 2 decimals (74900 -> "749.00")."""
    return str((Decimal(cents) / 100).quantize(Decimal("0.01")))
