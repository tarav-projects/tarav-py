# $kw: --from Project.Discovery.System
from __future__ import annotations

from tarav._core.errors import CliError


def validate_string_for_path(value: str, *, field_name: str = "value") -> str:
    normalized = str(value).strip()
    if not normalized:
        raise CliError(f"{field_name} must not be empty")

    if "/" in normalized or "\\" in normalized:
        raise CliError(f"{field_name} must not contain path separators")

    if normalized in {".", ".."}:
        raise CliError(f"{field_name} must not be '.' or '..'")

    if "\x00" in normalized:
        raise CliError(f"{field_name} must not contain null bytes")

    return normalized
