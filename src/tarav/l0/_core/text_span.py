# $kw: --from CPU.Program
from __future__ import annotations

from bisect import bisect_right

from tarav.l0._core.errors import CliError


def validate_span(
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


def extract_text_from_span(
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


def build_line_starts(text: str) -> list[int]:
    line_starts = [0]
    for idx, char in enumerate(text):
        if char == "\n":
            line_starts.append(idx + 1)
    return line_starts


def offset_to_line_column(line_starts: list[int], offset: int) -> tuple[int, int]:
    if offset < 0:
        raise CliError("offset must be >= 0")
    line_index = bisect_right(line_starts, offset) - 1
    if line_index < 0:
        line_index = 0
    line_start = line_starts[line_index]
    return line_index + 1, (offset - line_start) + 1


def find_fragment_span(
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


def find_all_fragment_spans(full_text: str, fragment: str) -> list[tuple[int, int]]:
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
