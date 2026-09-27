# $kw: --from Usage.Surface
from __future__ import annotations

import json
import sys
from pathlib import Path

from tarav.l0._core.errors import CliError


def load_json_arg(json_value: str | None, file_value: str | None, *, field_name: str) -> object:
    if json_value is None and file_value is None:
        raise CliError(f"{field_name} source is missing")

    if json_value is not None:
        raw = json_value
    else:
        assert file_value is not None
        path = Path(file_value).expanduser()
        if not path.exists():
            raise CliError(f"{field_name} file does not exist: {path}")
        if not path.is_file():
            raise CliError(f"{field_name} file path is not a file: {path}")
        raw = path.read_text(encoding="utf-8")

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CliError(f"invalid JSON for {field_name}: {exc}") from exc


def load_json_object_arg(
    json_value: str | None,
    file_value: str | None,
    *,
    field_name: str,
) -> dict[str, object]:
    if json_value is None and file_value is None:
        return {}
    payload = load_json_arg(json_value, file_value, field_name=field_name)
    if not isinstance(payload, dict):
        raise CliError(f"{field_name} must be a JSON object")
    return payload


def load_json_array_arg(
    json_value: str | None,
    file_value: str | None,
    *,
    field_name: str,
) -> list[object]:
    if json_value is None and file_value is None:
        return []
    payload = load_json_arg(json_value, file_value, field_name=field_name)
    if not isinstance(payload, list):
        raise CliError(f"{field_name} must be a JSON array")
    return payload


def load_json_input(input_path: str) -> object:
    if input_path == "-":
        raw = sys.stdin.read()
    else:
        candidate = Path(input_path).expanduser()
        if not candidate.exists():
            raise CliError(f"input file does not exist: {candidate}")
        if not candidate.is_file():
            raise CliError(f"input path is not a file: {candidate}")
        raw = candidate.read_text(encoding="utf-8")

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CliError(f"invalid JSON input: {exc}") from exc
