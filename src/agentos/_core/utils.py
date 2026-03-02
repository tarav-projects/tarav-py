from __future__ import annotations

import argparse
import json
import subprocess
import sys
from bisect import bisect_right
from datetime import datetime, timezone
from pathlib import Path

from .errors import CliError


def _run_git(repo_dir: Path, *git_args: str) -> str:
    result = subprocess.run(
        ["git", *git_args],
        cwd=str(repo_dir),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        details = result.stderr.strip() or result.stdout.strip() or "git command failed"
        raise CliError(details)
    return result.stdout.strip()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def _build_writer_payload(args: argparse.Namespace) -> dict[str, str]:
    return {
        "agent": str(args.writer_agent),
        "skill": str(args.writer_skill),
        "version": str(args.writer_version),
    }


def _load_json_arg(json_value: str | None, file_value: str | None, *, field_name: str) -> object:
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


def _load_json_object_arg(
    json_value: str | None,
    file_value: str | None,
    *,
    field_name: str,
) -> dict[str, object]:
    if json_value is None and file_value is None:
        return {}
    payload = _load_json_arg(json_value, file_value, field_name=field_name)
    if not isinstance(payload, dict):
        raise CliError(f"{field_name} must be a JSON object")
    return payload


def _load_json_array_arg(
    json_value: str | None,
    file_value: str | None,
    *,
    field_name: str,
) -> list[object]:
    if json_value is None and file_value is None:
        return []
    payload = _load_json_arg(json_value, file_value, field_name=field_name)
    if not isinstance(payload, list):
        raise CliError(f"{field_name} must be a JSON array")
    return payload


def _load_json_input(input_path: str) -> object:
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


def _resolve_repo_root(repo_hint: str) -> Path:
    hint_path = Path(repo_hint).expanduser().resolve()
    if hint_path.is_file():
        hint_path = hint_path.parent
    if not hint_path.exists():
        raise CliError(f"repo path does not exist: {hint_path}")
    try:
        root = _run_git(hint_path, "rev-parse", "--show-toplevel")
    except CliError as exc:
        raise CliError(f"not a git repository: {hint_path} ({exc})") from exc
    return Path(root).resolve()


def _resolve_repo_file(repo_root: Path, file_path: str) -> Path:
    raw_path = Path(file_path).expanduser()
    resolved = raw_path.resolve() if raw_path.is_absolute() else (repo_root / raw_path).resolve()
    if not resolved.exists():
        raise CliError(f"file does not exist: {resolved}")
    if not resolved.is_file():
        raise CliError(f"path is not a file: {resolved}")
    try:
        resolved.relative_to(repo_root)
    except ValueError as exc:
        raise CliError(f"file is outside repository root: {resolved}") from exc
    return resolved


def _resolve_repo_relative_path(repo_root: Path, file_path: str) -> str:
    raw_path = Path(file_path).expanduser()
    resolved = raw_path.resolve() if raw_path.is_absolute() else (repo_root / raw_path).resolve()
    try:
        relative_path = resolved.relative_to(repo_root)
    except ValueError as exc:
        raise CliError(f"file is outside repository root: {resolved}") from exc
    return relative_path.as_posix()


def _validate_span(
    lines: list[str],
    start_line: int,
    end_line: int,
    start_column: int,
    end_column: int,
) -> None:
    if start_line < 1:
        raise CliError("start line must be >= 1")
    if end_line < start_line:
        raise CliError("end line must be >= start line")
    if end_line > len(lines):
        raise CliError(f"end line {end_line} exceeds file length {len(lines)}")
    if start_column < 1:
        raise CliError("start column must be >= 1")
    if end_column < 1:
        raise CliError("end column must be >= 1")

    start_line_len = len(lines[start_line - 1])
    end_line_len = len(lines[end_line - 1])
    if start_column > start_line_len + 1:
        raise CliError(
            f"start column {start_column} exceeds start line length+1 ({start_line_len + 1})"
        )
    if end_column > end_line_len + 1:
        raise CliError(f"end column {end_column} exceeds end line length+1 ({end_line_len + 1})")
    if start_line == end_line and end_column < start_column:
        raise CliError("end column must be >= start column when start line == end line")


def _extract_text_from_span(
    lines: list[str],
    start_line: int,
    end_line: int,
    start_column: int,
    end_column: int,
) -> str:
    if start_line == end_line:
        line = lines[start_line - 1]
        return line[start_column - 1 : end_column - 1]

    first = lines[start_line - 1][start_column - 1 :]
    middle = lines[start_line:end_line - 1]
    last = lines[end_line - 1][: end_column - 1]
    return "\n".join([first, *middle, last])


def _build_line_starts(text: str) -> list[int]:
    line_starts = [0]
    for idx, char in enumerate(text):
        if char == "\n":
            line_starts.append(idx + 1)
    return line_starts


def _offset_to_line_column(line_starts: list[int], offset: int) -> tuple[int, int]:
    if offset < 0:
        raise CliError("offset must be >= 0")
    line_index = bisect_right(line_starts, offset) - 1
    if line_index < 0:
        line_index = 0
    line_start = line_starts[line_index]
    return line_index + 1, (offset - line_start) + 1


def _find_fragment_span(
    full_text: str,
    fragment: str,
    occurrence: int,
    *,
    search_start: int = 0,
) -> tuple[int, int]:
    if not fragment:
        raise CliError("text fragment must not be empty")
    if occurrence < 1:
        raise CliError("occurrence must be >= 1")
    if search_start < 0:
        raise CliError("search start must be >= 0")

    current_occurrence = 0
    while True:
        match_index = full_text.find(fragment, search_start)
        if match_index == -1:
            break

        current_occurrence += 1
        if current_occurrence == occurrence:
            return match_index, match_index + len(fragment)
        search_start = match_index + len(fragment)

    raise CliError(f"fragment not found at occurrence {occurrence} (found {current_occurrence} matches)")


def _find_all_fragment_spans(full_text: str, fragment: str) -> list[tuple[int, int]]:
    if not fragment:
        raise CliError("text fragment must not be empty")

    matches: list[tuple[int, int]] = []
    search_start = 0
    while True:
        match_index = full_text.find(fragment, search_start)
        if match_index == -1:
            return matches
        matches.append((match_index, match_index + len(fragment)))
        search_start = match_index + len(fragment)
