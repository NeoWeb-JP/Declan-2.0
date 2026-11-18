"""Shared validation for untrusted session timing metadata."""

from math import isfinite


def finite_number(value):
    """Accept finite int/float values without coercing booleans or huge integers."""
    if type(value) not in (int, float):
        return False
    try:
        return isfinite(value)
    except OverflowError:
        return False
