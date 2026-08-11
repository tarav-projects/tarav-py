# $kw: --from Chatlas.Time.Interface
from __future__ import annotations

from agentos._core.errors import CliError


def parse_duration_seconds(value: str, *, field_name: str) -> int:
    text = value.strip().lower()
    if not text:
        raise CliError(f"{field_name} must not be empty")
    unit = text[-1]
    number_text = text[:-1] if unit.isalpha() else text
    try:
        amount = int(number_text)
    except ValueError as exc:
        raise CliError(f"invalid {field_name} value: {value}") from exc
    if amount < 0:
        raise CliError(f"{field_name} must be non-negative")
    if unit == "w":
        return amount * 7 * 24 * 60 * 60
    if unit == "d":
        return amount * 24 * 60 * 60
    if unit == "h":
        return amount * 60 * 60
    if unit == "m":
        return amount * 60
    if unit == "s" or not unit.isalpha():
        return amount
    raise CliError(f"unsupported {field_name} unit: {unit}")


__all__ = ["parse_duration_seconds"]
