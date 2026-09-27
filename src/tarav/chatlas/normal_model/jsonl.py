from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Iterator, Pattern

from tarav.l0._core.errors import CliError

from .model import JsonObject


@dataclass(frozen=True, slots=True)
class JsonlCandidateScan:
    literals: tuple[str, ...] = ()
    pattern: Pattern[str] | None = None

    def accepts(self, line: str) -> bool:
        return all(literal in line for literal in self.literals) and (
            self.pattern is None or self.pattern.search(line) is not None
        )


def iter_jsonl_objects(
    path: Path,
    *,
    scan: JsonlCandidateScan | None = None,
) -> Iterator[JsonObject]:
    try:
        handle = path.open("r", encoding="utf-8")
    except OSError as exc:
        raise CliError(f"Chatlas cannot read JSONL collection {path}") from exc
    with handle:
        for line_number, line in enumerate(handle, start=1):
            if scan is not None and not scan.accepts(line):
                continue
            yield _decode_object(path, line_number=line_number, line=line)


def read_jsonl_object_lines(
    path: Path,
    line_numbers: set[int],
) -> dict[int, JsonObject]:
    if not line_numbers or any(number < 1 for number in line_numbers):
        return {}
    selected: dict[int, JsonObject] = {}
    try:
        handle = path.open("r", encoding="utf-8")
    except OSError as exc:
        raise CliError(f"Chatlas cannot read JSONL source {path}") from exc
    with handle:
        for line_number, line in enumerate(handle, start=1):
            if line_number not in line_numbers:
                continue
            selected[line_number] = _decode_object(
                path,
                line_number=line_number,
                line=line,
            )
            if len(selected) == len(line_numbers):
                break
    missing = sorted(line_numbers - set(selected))
    if missing:
        raise CliError(f"Chatlas JSONL source {path} has no lines {missing}")
    return selected


def serialized_json_string(value: str) -> str | None:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if any(0xD800 <= ord(character) <= 0xDFFF for character in encoded):
        return None
    return encoded


def address_pattern(field: str, values: set[str]) -> Pattern[str] | None:
    if not values:
        return None
    alternatives = "|".join(re.escape(value) for value in sorted(values))
    return re.compile(rf'"{re.escape(field)}":"(?:{alternatives})"')


def _decode_object(path: Path, *, line_number: int, line: str) -> JsonObject:
    try:
        value = json.loads(line)
    except json.JSONDecodeError as exc:
        raise CliError(
            f"Chatlas JSONL collection {path} has invalid JSON at line {line_number}"
        ) from exc
    if not isinstance(value, dict):
        raise CliError(
            f"Chatlas JSONL collection {path} line {line_number} is not an object"
        )
    return value


__all__ = [
    "JsonlCandidateScan",
    "address_pattern",
    "iter_jsonl_objects",
    "read_jsonl_object_lines",
    "serialized_json_string",
]
