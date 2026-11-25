"""Lossless JSON numbers for evidence, its index, and its handoffs."""
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


def _invalid_number(token: str) -> None:
    raise ValueError(f"not a finite JSON number: {token}")


def _decimal_number(token: str) -> Decimal | float:
    # Keep ordinary numbers and legacy checkpoint hashes when the standard
    # encoder preserves their exact decimal value (including spellings like 1.00).
    number = float(token)
    if repr(number) == token:
        return number
    try:
        exact = Decimal(token)
    except InvalidOperation as exc:
        raise ValueError(f"decimal outside supported exponent range: {token}") from exc
    return number if exact == Decimal(repr(number)) else exact


def loads(text: str | bytes) -> Any:
    return json.loads(text, parse_float=_decimal_number, parse_constant=_invalid_number)


def read(path: Path) -> Any:
    return loads(path.read_text(encoding="utf-8"))


def dumps(value: Any, level: int = 0) -> str:
    """Write Decimal leaves as JSON numbers and keep the existing two-space layout."""
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError(f"not a finite JSON number: {value}")
        return str(value)
    if not isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, allow_nan=False)
    if isinstance(value, dict):
        opening, closing = "{", "}"
        items = (json.dumps(key, ensure_ascii=False) + ": " + dumps(item, level + 1)
                 for key, item in value.items())
    else:
        opening, closing = "[", "]"
        items = (dumps(item, level + 1) for item in value)
    if not value:
        return opening + closing
    separator = "\n" + "  " * (level + 1)
    return opening + separator + ("," + separator).join(items) + "\n" + "  " * level + closing


def is_number(value: Any) -> bool:
    return type(value) in (int, float, Decimal)


def equal(left: Any, right: Any) -> bool:
    """JSON booleans and numbers are distinct, also inside arrays and objects."""
    if is_number(left) and is_number(right):
        return Decimal(str(left)) == Decimal(str(right))
    if type(left) is not type(right):
        return False
    if isinstance(left, list):
        return len(left) == len(right) and all(equal(a, b) for a, b in zip(left, right))
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(equal(left[key], right[key]) for key in left)
    return left == right
