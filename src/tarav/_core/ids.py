# $kw: --from CPU.Program
from __future__ import annotations

from uuid import UUID, uuid4

from tarav._core.errors import CliError


def generate_uuid4_string() -> str:
    return str(uuid4())


def generate_uuid4_hex() -> str:
    return uuid4().hex


def validate_uuid_string(value: str, *, field_name: str = "value") -> str:
    normalized = str(value).strip()
    if not normalized:
        raise CliError(f"{field_name} must not be empty")

    try:
        parsed = UUID(normalized)
    except ValueError as exc:
        raise CliError(f"invalid {field_name} (expected UUID): {normalized}") from exc
    return str(parsed)


def normalize_or_generate_uuid(value: str | None, *, field_name: str = "value") -> str:
    if value is None:
        return generate_uuid4_string()
    return validate_uuid_string(value, field_name=field_name)
