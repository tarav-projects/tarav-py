from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any


DEFAULT_MARKDOWN_EXCLUDES = (
    ".git",
    ".venv",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    "node_modules",
)

_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)\s*$")


@dataclass(frozen=True)
class MarkdownScanConfig:
    root: Path
    targets: tuple[Path, ...]
    excludes: tuple[str, ...]
    min_level: int = 1
    max_level: int = 6
    recursive: bool = True
    include_content: bool = False


@dataclass(frozen=True)
class _Heading:
    start_line: int
    level: int
    title: str


def _normalize_rel(rel: PurePosixPath) -> str:
    value = rel.as_posix()
    return "" if value == "." else value


def _should_exclude(rel_path: PurePosixPath, patterns: tuple[str, ...]) -> bool:
    rel_value = _normalize_rel(rel_path)
    rel_parts = set(rel_path.parts)

    for raw_pattern in patterns:
        pattern = raw_pattern.strip().strip("/")
        if not pattern:
            continue

        if rel_value == pattern or rel_value.startswith(f"{pattern}/"):
            return True

        # A bare directory name excludes that folder anywhere in the tree.
        if "/" not in pattern and pattern in rel_parts:
            return True

        if rel_value and PurePosixPath(rel_value).match(pattern):
            return True
    return False


def _sanitize_heading_title(raw_title: str) -> str:
    title = raw_title.strip()
    # Allow markdown's optional trailing heading marker hashes.
    title = re.sub(r"[ \t]+#+[ \t]*$", "", title)
    return title.strip()


def _discover_markdown_files(config: MarkdownScanConfig) -> list[Path]:
    discovered: set[Path] = set()

    for target in config.targets:
        if target.is_file():
            rel_target = PurePosixPath(target.relative_to(config.root).as_posix())
            if target.suffix.lower() == ".md" and not _should_exclude(rel_target, config.excludes):
                discovered.add(target)
            continue

        if not target.is_dir():
            continue

        if config.recursive:
            for dirpath, dirnames, filenames in os.walk(target):
                current = Path(dirpath)
                rel_current = PurePosixPath(
                    _normalize_rel(PurePosixPath(current.relative_to(config.root).as_posix()))
                )
                if _should_exclude(rel_current, config.excludes):
                    dirnames[:] = []
                    continue

                pruned: list[str] = []
                for dirname in dirnames:
                    rel_dir = PurePosixPath(
                        _normalize_rel(
                            PurePosixPath((current / dirname).relative_to(config.root).as_posix())
                        )
                    )
                    if not _should_exclude(rel_dir, config.excludes):
                        pruned.append(dirname)
                dirnames[:] = pruned

                for filename in filenames:
                    if not filename.lower().endswith(".md"):
                        continue
                    file_path = current / filename
                    rel_file = PurePosixPath(file_path.relative_to(config.root).as_posix())
                    if not _should_exclude(rel_file, config.excludes):
                        discovered.add(file_path)
        else:
            for child in target.iterdir():
                if not child.is_file() or child.suffix.lower() != ".md":
                    continue
                rel_file = PurePosixPath(child.relative_to(config.root).as_posix())
                if not _should_exclude(rel_file, config.excludes):
                    discovered.add(child)

    return sorted(discovered, key=lambda path: path.relative_to(config.root).as_posix())


def _extract_headings(lines: list[str]) -> tuple[list[_Heading], bool]:
    headings: list[_Heading] = []
    in_fence = False
    fence_char = ""
    fence_len = 0

    def _fence_run(stripped_line: str) -> tuple[str, int]:
        if not stripped_line:
            return ("", 0)
        char = stripped_line[0]
        if char not in ("`", "~"):
            return ("", 0)
        count = 0
        for candidate in stripped_line:
            if candidate == char:
                count += 1
            else:
                break
        return (char, count)

    for line_no, line in enumerate(lines, start=1):
        stripped = line.lstrip()
        run_char, run_len = _fence_run(stripped)

        if not in_fence and run_len >= 3:
            in_fence = True
            fence_char = run_char
            fence_len = run_len
            continue

        if in_fence:
            if run_char == fence_char and run_len >= fence_len and stripped[run_len:].strip() == "":
                in_fence = False
                fence_char = ""
                fence_len = 0
            continue

        match = _HEADING_RE.match(line)
        if not match:
            continue
        level = len(match.group(1))
        title = _sanitize_heading_title(match.group(2))
        headings.append(_Heading(start_line=line_no, level=level, title=title))
    return headings, in_fence


def _count_preamble_nonempty_lines(lines: list[str], first_heading_line: int | None) -> int:
    if first_heading_line is None or first_heading_line <= 1:
        return 0

    start_index = 0
    limit_index = first_heading_line - 1

    if lines and lines[0].strip() == "---":
        front_matter_closed = False
        for index in range(1, limit_index):
            if lines[index].strip() == "---":
                start_index = index + 1
                front_matter_closed = True
                break
        if not front_matter_closed:
            return 0

    count = 0
    for line in lines[start_index:limit_index]:
        stripped = line.strip()
        if stripped and stripped != "***":
            count += 1
    return count


def _parse_file_blocks(
    root: Path,
    file_path: Path,
    min_level: int,
    max_level: int,
    include_content: bool,
) -> dict[str, Any]:
    text = file_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    rel_path = file_path.relative_to(root).as_posix()

    headings, has_unclosed_fence = _extract_headings(lines)
    blocks: list[dict[str, Any]] = []

    for index, heading in enumerate(headings):
        next_boundary = len(lines)
        for candidate in headings[index + 1 :]:
            if candidate.level <= heading.level:
                next_boundary = candidate.start_line - 1
                break

        parent_heading: _Heading | None = None
        for candidate in reversed(headings[:index]):
            if candidate.level < heading.level:
                parent_heading = candidate
                break

        if not (min_level <= heading.level <= max_level):
            continue

        start_line = heading.start_line
        end_line = max(start_line, next_boundary)
        body_start = start_line + 1
        has_body = body_start <= end_line
        body_end = end_line if has_body else body_start - 1

        block_data: dict[str, Any] = {
            "index": len(blocks) + 1,
            "id": f"{rel_path}#L{start_line}-L{end_line}",
            "path": rel_path,
            "link": f"{rel_path}#L{start_line}",
            "path_line": f"{rel_path}:{start_line}",
            "title": heading.title,
            "level": heading.level,
            "start_line": start_line,
            "end_line": end_line,
            "body_start_line": body_start,
            "body_end_line": body_end,
            "has_body": has_body,
            "parent": None
            if parent_heading is None
            else {
                "title": parent_heading.title,
                "level": parent_heading.level,
                "start_line": parent_heading.start_line,
                "path_line": f"{rel_path}:{parent_heading.start_line}",
                "link": f"{rel_path}#L{parent_heading.start_line}",
            },
        }

        if include_content:
            block_data["content"] = "\n".join(lines[start_line - 1 : end_line]).rstrip("\n")

        blocks.append(block_data)

    first_heading_line = headings[0].start_line if headings else None

    return {
        "path": rel_path,
        "absolute_path": str(file_path),
        "line_count": len(lines),
        "heading_count": len(headings),
        "block_count": len(blocks),
        "first_heading_line": first_heading_line,
        "preamble_nonempty_line_count": _count_preamble_nonempty_lines(lines, first_heading_line),
        "has_unclosed_fence": has_unclosed_fence,
        "blocks": blocks,
    }


def scan_markdown_blocks(config: MarkdownScanConfig) -> list[dict[str, Any]]:
    files = _discover_markdown_files(config)
    parsed: list[dict[str, Any]] = []
    for file_path in files:
        parsed.append(
            _parse_file_blocks(
                root=config.root,
                file_path=file_path,
                min_level=config.min_level,
                max_level=config.max_level,
                include_content=config.include_content,
            )
        )
    return parsed


def collect_block_links(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    for file_data in files:
        for block in file_data["blocks"]:
            links.append(
                {
                    "id": block["id"],
                    "path": block["path"],
                    "path_line": block["path_line"],
                    "link": block["link"],
                    "title": block["title"],
                    "level": block["level"],
                    "start_line": block["start_line"],
                    "end_line": block["end_line"],
                }
            )
    return links


def _iter_blocks(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for file_data in files:
        blocks.extend(file_data["blocks"])
    return blocks


def _tokenize_query(query: str) -> list[str]:
    terms = re.findall(r"[A-Za-z0-9_]+", query)
    if terms:
        return terms
    trimmed = query.strip()
    return [trimmed] if trimmed else []


def _count_substring(text: str, needle: str, case_sensitive: bool) -> int:
    if not needle:
        return 0
    if case_sensitive:
        return text.count(needle)
    return text.casefold().count(needle.casefold())


def _score_block_lexical(
    block: dict[str, Any],
    *,
    query: str,
    terms: list[str],
    case_sensitive: bool,
) -> tuple[int, dict[str, Any]]:
    title = str(block["title"])
    path = str(block["path"])
    content = str(block.get("content", ""))

    title_phrase = _count_substring(title, query, case_sensitive)
    path_phrase = _count_substring(path, query, case_sensitive)
    content_phrase = _count_substring(content, query, case_sensitive)

    title_term_hits = 0
    path_term_hits = 0
    content_term_hits = 0
    for term in terms:
        title_term_hits += _count_substring(title, term, case_sensitive)
        path_term_hits += _count_substring(path, term, case_sensitive)
        content_term_hits += _count_substring(content, term, case_sensitive)

    score = (
        (title_phrase * 120)
        + (path_phrase * 60)
        + (content_phrase * 25)
        + (title_term_hits * 24)
        + (path_term_hits * 10)
        + (content_term_hits * 4)
    )

    if case_sensitive:
        exact_title_match = title.strip() == query.strip()
    else:
        exact_title_match = title.strip().casefold() == query.strip().casefold()
    if exact_title_match:
        score += 300

    details = {
        "mode": "lexical",
        "title_phrase_hits": title_phrase,
        "path_phrase_hits": path_phrase,
        "content_phrase_hits": content_phrase,
        "title_term_hits": title_term_hits,
        "path_term_hits": path_term_hits,
        "content_term_hits": content_term_hits,
        "exact_title_match": exact_title_match,
    }
    return score, details


def _score_block_regex(
    block: dict[str, Any],
    *,
    pattern: re.Pattern[str],
) -> tuple[int, dict[str, Any]]:
    title = str(block["title"])
    path = str(block["path"])
    content = str(block.get("content", ""))

    title_matches = len(list(pattern.finditer(title)))
    path_matches = len(list(pattern.finditer(path)))
    content_matches = len(list(pattern.finditer(content)))

    score = (title_matches * 140) + (path_matches * 70) + (content_matches * 20)
    details = {
        "mode": "regex",
        "title_regex_matches": title_matches,
        "path_regex_matches": path_matches,
        "content_regex_matches": content_matches,
    }
    return score, details


def find_markdown_blocks(
    config: MarkdownScanConfig,
    *,
    query: str,
    top_k: int = 5,
    use_regex: bool = False,
    case_sensitive: bool = False,
) -> dict[str, Any]:
    query_text = query.strip()
    if not query_text:
        raise ValueError("--query cannot be empty")
    if top_k < 1:
        raise ValueError("--top-k must be >= 1")

    scan_config = MarkdownScanConfig(
        root=config.root,
        targets=config.targets,
        excludes=config.excludes,
        min_level=config.min_level,
        max_level=config.max_level,
        recursive=config.recursive,
        include_content=True,
    )
    files = scan_markdown_blocks(scan_config)
    blocks = _iter_blocks(files)

    regex_pattern: re.Pattern[str] | None = None
    terms: list[str] = []
    if use_regex:
        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            regex_pattern = re.compile(query_text, flags=flags)
        except re.error as exc:
            raise ValueError(f"invalid regex pattern: {exc}") from exc
    else:
        terms = _tokenize_query(query_text)

    matches: list[dict[str, Any]] = []
    for block in blocks:
        if regex_pattern is not None:
            score, details = _score_block_regex(block, pattern=regex_pattern)
        else:
            score, details = _score_block_lexical(
                block,
                query=query_text,
                terms=terms,
                case_sensitive=case_sensitive,
            )

        if score <= 0:
            continue

        matches.append(
            {
                "id": block["id"],
                "path": block["path"],
                "path_line": block["path_line"],
                "link": block["link"],
                "title": block["title"],
                "level": block["level"],
                "start_line": block["start_line"],
                "end_line": block["end_line"],
                "score": score,
                "details": details,
            }
        )

    matches.sort(
        key=lambda match: (
            -int(match["score"]),
            str(match["path"]),
            int(match["start_line"]),
            str(match["title"]),
        )
    )

    return {
        "query": query_text,
        "regex": use_regex,
        "case_sensitive": case_sensitive,
        "top_k": top_k,
        "scanned_file_count": len(files),
        "scanned_block_count": len(blocks),
        "match_count": len(matches),
        "matches": matches[:top_k],
    }


def _make_lint_issue(
    *,
    severity: str,
    code: str,
    path: str,
    message: str,
    line: int | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    issue: dict[str, Any] = {
        "severity": severity,
        "code": code,
        "path": path,
        "message": message,
    }
    if line is not None:
        issue["line"] = line
        issue["path_line"] = f"{path}:{line}"
        issue["link"] = f"{path}#L{line}"
    if details:
        issue["details"] = details
    return issue


def _is_block_separator_line(value: str) -> bool:
    return value.strip() == "***"


def _separator_lines(lines: list[str]) -> list[int]:
    return [index + 1 for index, line in enumerate(lines) if _is_block_separator_line(line)]


def _separator_pairs(separator_lines: list[int]) -> list[tuple[int, int]]:
    pairs: list[tuple[int, int]] = []
    for index in range(0, len(separator_lines) - 1, 2):
        pairs.append((separator_lines[index], separator_lines[index + 1]))
    return pairs


def _is_line_inside_separator_pairs(line: int, pairs: list[tuple[int, int]]) -> bool:
    for start, end in pairs:
        if start < line < end:
            return True
    return False


def _nearest_separator_bounds(line: int, separator_lines: list[int]) -> tuple[int | None, int | None]:
    before: int | None = None
    after: int | None = None
    for separator_line in separator_lines:
        if separator_line < line:
            before = separator_line
            continue
        if separator_line > line:
            after = separator_line
            break
    return before, after


def _lint_separator_block_flatness(
    *,
    lines: list[str],
    block_start_line: int,
    block_end_line: int,
    path: str,
) -> dict[str, Any] | None:
    # Inspect text between separators, excluding the separator lines themselves.
    inner_start = block_start_line + 1
    inner_end = block_end_line - 1
    if inner_start > inner_end:
        return None

    segment = lines[inner_start - 1 : inner_end]
    headings, _ = _extract_headings(segment)
    if len(headings) <= 1:
        return None

    level_counts: dict[int, int] = {}
    for heading in headings:
        level_counts[heading.level] = level_counts.get(heading.level, 0) + 1

    # "Flat" means headings in the separator block stay at one level.
    if len(level_counts) == 1:
        return None

    first_heading = headings[0]
    return _make_lint_issue(
        severity="warning",
        code="nonflat_separator_block",
        path=path,
        line=inner_start + first_heading.start_line - 1,
        message=(
            "Content between `***` separators is not flat: multiple heading levels were found."
        ),
        details={
            "separator_start_line": block_start_line,
            "separator_end_line": block_end_line,
            "heading_levels": sorted(level_counts.keys()),
            "heading_count": len(headings),
        },
    )


def lint_markdown_blocks(config: MarkdownScanConfig, max_block_lines: int = 30) -> dict[str, Any]:
    lint_config = MarkdownScanConfig(
        root=config.root,
        targets=config.targets,
        excludes=config.excludes,
        min_level=config.min_level,
        max_level=config.max_level,
        recursive=config.recursive,
        include_content=False,
    )
    files = scan_markdown_blocks(lint_config)

    file_reports: list[dict[str, Any]] = []
    all_issues: list[dict[str, Any]] = []

    for file_data in files:
        file_path = file_data["path"]
        blocks = sorted(file_data["blocks"], key=lambda item: int(item["start_line"]))
        file_issues: list[dict[str, Any]] = []
        lines: list[str] = []
        absolute_path = file_data.get("absolute_path")
        if isinstance(absolute_path, str):
            try:
                lines = Path(absolute_path).read_text(encoding="utf-8").splitlines()
            except OSError:
                lines = []

        if file_data["heading_count"] == 0:
            file_issues.append(
                _make_lint_issue(
                    severity="warning",
                    code="no_headings",
                    path=file_path,
                    message="File has no markdown headings.",
                )
            )

        if file_data.get("has_unclosed_fence", False):
            fence_line = int(file_data["line_count"]) if int(file_data["line_count"]) > 0 else None
            file_issues.append(
                _make_lint_issue(
                    severity="error",
                    code="unclosed_code_fence",
                    path=file_path,
                    line=fence_line,
                    message="File appears to contain an unclosed fenced code block.",
                )
            )

        preamble_nonempty = int(file_data.get("preamble_nonempty_line_count", 0))
        if preamble_nonempty > 0:
            file_issues.append(
                _make_lint_issue(
                    severity="warning",
                    code="preamble_text_before_first_heading",
                    path=file_path,
                    line=1,
                    message="File contains non-empty text before the first heading.",
                    details={"nonempty_line_count": preamble_nonempty},
                )
            )

        if lines:
            separator_lines = _separator_lines(lines)
            separator_pairs = _separator_pairs(separator_lines)

            if len(separator_lines) % 2 != 0:
                file_issues.append(
                    _make_lint_issue(
                        severity="warning",
                        code="unpaired_block_separator",
                        path=file_path,
                        line=separator_lines[-1],
                        message=(
                            "Unpaired `***` separator found; separators should come in open/close pairs."
                        ),
                    )
                )

            for block_start, block_end in separator_pairs:
                issue = _lint_separator_block_flatness(
                    lines=lines,
                    block_start_line=block_start,
                    block_end_line=block_end,
                    path=file_path,
                )
                if issue is not None:
                    file_issues.append(issue)

        seen_titles: dict[tuple[int, str], int] = {}
        previous_level: int | None = None

        for block in blocks:
            start_line = int(block["start_line"])
            end_line = int(block["end_line"])
            level = int(block["level"])
            title = str(block["title"]).strip()

            if previous_level is not None and level > previous_level + 1:
                file_issues.append(
                    _make_lint_issue(
                        severity="warning",
                        code="heading_level_jump",
                        path=file_path,
                        line=start_line,
                        message=f"Heading level jumps from h{previous_level} to h{level}.",
                    )
                )
            previous_level = level

            if not title:
                file_issues.append(
                    _make_lint_issue(
                        severity="error",
                        code="empty_heading_title",
                        path=file_path,
                        line=start_line,
                        message="Heading title is empty after markdown sanitization.",
                    )
                )

            line_span = end_line - start_line + 1
            if max_block_lines > 0 and line_span > max_block_lines:
                file_issues.append(
                    _make_lint_issue(
                        severity="warning",
                        code="block_too_long",
                        path=file_path,
                        line=start_line,
                        message=f"Block spans {line_span} lines; threshold is {max_block_lines}.",
                        details={
                            "line_span": line_span,
                            "max_block_lines": max_block_lines,
                            "end_line": end_line,
                        },
                    )
                )

            if lines:
                if not _is_line_inside_separator_pairs(start_line, separator_pairs):
                    before_separator, after_separator = _nearest_separator_bounds(
                        start_line, separator_lines
                    )
                    details: dict[str, Any] = {}
                    if before_separator is not None:
                        details["nearest_separator_before_line"] = before_separator
                    if after_separator is not None:
                        details["nearest_separator_after_line"] = after_separator
                    file_issues.append(
                        _make_lint_issue(
                            severity="warning",
                            code="missing_block_separators",
                            path=file_path,
                            line=start_line,
                            message=(
                                "Heading is not inside a `*** ... ***` block separator pair."
                            ),
                            details=details,
                        )
                    )

            if title:
                dedupe_key = (level, title.casefold())
                first_seen_line = seen_titles.get(dedupe_key)
                if first_seen_line is None:
                    seen_titles[dedupe_key] = start_line
                else:
                    file_issues.append(
                        _make_lint_issue(
                            severity="warning",
                            code="duplicate_heading_title_same_level",
                            path=file_path,
                            line=start_line,
                            message="Heading title duplicates an earlier heading at the same level.",
                            details={
                                "first_seen_line": first_seen_line,
                                "heading_level": level,
                                "title": title,
                            },
                        )
                    )

        error_count = sum(1 for issue in file_issues if issue["severity"] == "error")
        warning_count = sum(1 for issue in file_issues if issue["severity"] == "warning")
        file_reports.append(
            {
                "path": file_path,
                "heading_count": int(file_data["heading_count"]),
                "block_count": int(file_data["block_count"]),
                "issue_count": len(file_issues),
                "error_count": error_count,
                "warning_count": warning_count,
                "issues": file_issues,
            }
        )
        all_issues.extend(file_issues)

    total_errors = sum(1 for issue in all_issues if issue["severity"] == "error")
    total_warnings = sum(1 for issue in all_issues if issue["severity"] == "warning")
    return {
        "file_count": len(files),
        "issue_count": len(all_issues),
        "error_count": total_errors,
        "warning_count": total_warnings,
        "max_block_lines": max_block_lines,
        "files": file_reports,
        "issues": all_issues,
    }
