"""Shared JSON boundary validation; v1 numbers came from JavaScript JSON.parse."""

from typing import Any


def json_integer(value: Any) -> bool:
    """Accept integral JSON numbers, including decimal/exponent forms, excluding booleans."""
    return type(value) is int or (type(value) is float and value.is_integer())
