# $kw: ^agentos-stdlib-mdblocks-core --from Agent.Navigable.Codebase --note [DF] reusable mdblocks behavior lives beneath the Python stdlib namespace matching its CLI --supp ^c20260811-62u
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tarav._core.scan import iter_target_files
from tarav.surfaces.markdown import MarkdownNormalModel


BLOCK_SEPARATOR = "****"
DEFAULT_MIN_HEADING_LEVEL = 2
DEFAULT_MAX_HEADING_LEVEL = 6
HARD_MAX_BLOCK_LINES = 25


@dataclass(frozen=True)
class MarkdownScanConfig:
    root: Path
    targets: tuple[Path, ...]
    excludes: tuple[str, ...]
    min_level: int = DEFAULT_MIN_HEADING_LEVEL
    max_level: int = DEFAULT_MAX_HEADING_LEVEL
    start_line: int | None = None
    end_line: int | None = None
    recursive: bool = True
    include_content: bool = False


@dataclass(frozen=True)
class _Heading:
    start_line: int
    level: int
    title: str


@dataclass(frozen=True)
class _ScanWindow:
    start_line: int
    end_line: int
    lines: list[str]


@dataclass
class _BlockScanState:
    rel_path: str
    source_lines: list[str]
    include_content: bool
    min_level: int
    max_level: int
    heading_by_line: dict[int, _Heading]
    separator_lines: frozenset[int]
    fenced_lines: frozenset[int]
    blocks: list[dict[str, Any]] = field(default_factory=list)
    semantic_separator_lines: set[int] = field(default_factory=set)
    orphan_separator_lines: list[int] = field(default_factory=list)
    waiting_separator_line: int | None = None
    waiting_separator_is_semantic: bool = False
    active_heading: _Heading | None = None
    active_open_separator_line: int | None = None

    def consume(self, line_no: int) -> None:
        if line_no in self.fenced_lines:
            return
        if line_no in self.separator_lines:
            self._consume_separator(line_no)
            return
        if self.active_heading is not None or self.waiting_separator_line is None:
            return
        heading = self.heading_by_line.get(line_no)
        if heading is not None and self.min_level <= heading.level <= self.max_level:
            self._open_block(heading)
        elif self.source_lines[line_no - 1].strip():
            self._drop_waiting_separator()

    def finish(self, end_line: int) -> None:
        if self.active_heading is not None:
            self._close_active_block(end_line=end_line, close_separator_line=None)
        if self.waiting_separator_line is not None:
            self._drop_waiting_separator()

    def _consume_separator(self, line_no: int) -> None:
        if self.active_heading is not None:
            self._close_active_block(
                end_line=line_no - 1,
                close_separator_line=line_no,
            )
            self.waiting_separator_line = line_no
            self.waiting_separator_is_semantic = True
            return
        self._drop_waiting_separator()
        self.waiting_separator_line = line_no

    def _open_block(self, heading: _Heading) -> None:
        assert self.waiting_separator_line is not None
        self.semantic_separator_lines.add(self.waiting_separator_line)
        self.active_heading = heading
        self.active_open_separator_line = self.waiting_separator_line
        self.waiting_separator_line = None
        self.waiting_separator_is_semantic = False

    def _close_active_block(
        self,
        *,
        end_line: int,
        close_separator_line: int | None,
    ) -> None:
        assert self.active_heading is not None
        assert self.active_open_separator_line is not None
        self.blocks.append(
            _build_block_payload(
                rel_path=self.rel_path,
                source_lines=self.source_lines,
                heading=self.active_heading,
                open_separator_line=self.active_open_separator_line,
                close_separator_line=close_separator_line,
                end_line=end_line,
                include_content=self.include_content,
                index=len(self.blocks) + 1,
            )
        )
        if close_separator_line is not None:
            self.semantic_separator_lines.add(close_separator_line)
        self.active_heading = None
        self.active_open_separator_line = None

    def _drop_waiting_separator(self) -> None:
        if (
            self.waiting_separator_line is not None
            and not self.waiting_separator_is_semantic
        ):
            self.orphan_separator_lines.append(self.waiting_separator_line)
        self.waiting_separator_line = None
        self.waiting_separator_is_semantic = False


def validate_markdown_level_range(min_level: int, max_level: int) -> None:
    if min_level < DEFAULT_MIN_HEADING_LEVEL or min_level > DEFAULT_MAX_HEADING_LEVEL:
        raise ValueError(
            f"--min-level must be between {DEFAULT_MIN_HEADING_LEVEL} and {DEFAULT_MAX_HEADING_LEVEL}"
        )
    if max_level < DEFAULT_MIN_HEADING_LEVEL or max_level > DEFAULT_MAX_HEADING_LEVEL:
        raise ValueError(
            f"--max-level must be between {DEFAULT_MIN_HEADING_LEVEL} and {DEFAULT_MAX_HEADING_LEVEL}"
        )
    if min_level > max_level:
        raise ValueError("--min-level cannot be greater than --max-level")


def validate_markdown_scan_window(start_line: int | None, end_line: int | None) -> None:
    if start_line is not None and start_line < 1:
        raise ValueError("--start-line must be >= 1")
    if end_line is not None and end_line < 1:
        raise ValueError("--end-line must be >= 1")
    if start_line is not None and end_line is not None and start_line > end_line:
        raise ValueError("--start-line cannot be greater than --end-line")


def _validate_scan_config(config: MarkdownScanConfig) -> None:
    validate_markdown_level_range(config.min_level, config.max_level)
    validate_markdown_scan_window(config.start_line, config.end_line)


def _discover_markdown_files(config: MarkdownScanConfig) -> list[Path]:
    discovered: set[Path] = set()

    for target in config.targets:
        for file_path in iter_target_files(
            root=config.root,
            target=target,
            excludes=config.excludes,
            recursive=config.recursive,
        ):
            if file_path.suffix.lower() == ".md":
                discovered.add(file_path)

    return sorted(discovered, key=lambda path: path.relative_to(config.root).as_posix())


def _extract_headings_and_separators(
    model: MarkdownNormalModel,
    *,
    start_line: int,
    end_line: int,
) -> tuple[list[_Heading], list[int], bool, frozenset[int]]:
    fenced_lines = model.fenced_line_numbers()
    headings = [
        _Heading(
            start_line=heading.span.start_line,
            level=heading.level,
            title=heading.text,
        )
        for heading in model.headings
        if start_line <= heading.span.start_line <= end_line
    ]
    separators = [
        line.span.start_line
        for line in model.lines
        if start_line <= line.span.start_line <= end_line
        and line.span.start_line not in fenced_lines
        and line.text.strip() == BLOCK_SEPARATOR
    ]
    has_unclosed_fence = any(
        fence.end is None
        and fence.start.start_line <= end_line
        and len(model.lines) >= start_line
        for fence in model.fences
    )
    return headings, separators, has_unclosed_fence, fenced_lines


def _count_preamble_nonempty_lines(
    lines: list[str], first_anchor_local_line: int | None
) -> int:
    if first_anchor_local_line is None or first_anchor_local_line <= 1:
        return 0

    start_index = 0
    limit_index = first_anchor_local_line - 1

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
        if stripped and stripped != BLOCK_SEPARATOR:
            count += 1
    return count


def _build_block_payload(
    *,
    rel_path: str,
    source_lines: list[str],
    heading: _Heading,
    open_separator_line: int,
    close_separator_line: int | None,
    end_line: int,
    include_content: bool,
    index: int,
) -> dict[str, Any]:
    start_line = heading.start_line
    block_end = max(start_line, end_line)
    body_start = start_line + 1
    has_body = body_start <= block_end
    body_end = block_end if has_body else body_start - 1

    block_data: dict[str, Any] = {
        "index": index,
        "id": f"{rel_path}#L{start_line}-L{block_end}",
        "path": rel_path,
        "link": f"{rel_path}#L{start_line}",
        "path_line": f"{rel_path}:{start_line}",
        "title": heading.title,
        "level": heading.level,
        "start_line": start_line,
        "end_line": block_end,
        "body_start_line": body_start,
        "body_end_line": body_end,
        "has_body": has_body,
        "separator_open_line": open_separator_line,
        "separator_close_line": close_separator_line,
        "parent": None,
    }

    if include_content:
        block_data["content"] = "\n".join(
            source_lines[start_line - 1 : block_end]
        ).rstrip("\n")

    return block_data


def _resolve_scan_window(
    source_lines: list[str],
    start_line: int | None,
    end_line: int | None,
) -> _ScanWindow:
    line_count = len(source_lines)
    effective_start = max(1, start_line if start_line is not None else 1)
    effective_end = min(end_line if end_line is not None else line_count, line_count)
    if (
        line_count
        and effective_start <= line_count
        and effective_start <= effective_end
    ):
        lines = source_lines[effective_start - 1 : effective_end]
    else:
        lines = []
        effective_start = min(effective_start, line_count + 1)
        effective_end = max(effective_start - 1, 0)
    return _ScanWindow(effective_start, effective_end, lines)


def _assign_block_parents(blocks: list[dict[str, Any]]) -> None:
    for index, block in enumerate(blocks):
        parent = next(
            (
                candidate
                for candidate in reversed(blocks[:index])
                if int(candidate["level"]) < int(block["level"])
            ),
            None,
        )
        if parent is not None:
            block["parent"] = {
                "title": parent["title"],
                "level": parent["level"],
                "start_line": parent["start_line"],
                "path_line": parent["path_line"],
                "link": parent["link"],
            }


def _parse_file_blocks(
    root: Path,
    file_path: Path,
    min_level: int,
    max_level: int,
    config_start_line: int | None,
    config_end_line: int | None,
    include_content: bool,
) -> dict[str, Any]:
    text = file_path.read_text(encoding="utf-8")
    model = MarkdownNormalModel.from_text(text)
    source_lines = [line.text for line in model.lines]
    rel_path = file_path.relative_to(root).as_posix()
    source_line_count = len(source_lines)
    window = _resolve_scan_window(source_lines, config_start_line, config_end_line)

    headings, separator_lines, has_unclosed_fence, fenced_lines = (
        _extract_headings_and_separators(
            model,
            start_line=window.start_line,
            end_line=window.end_line,
        )
    )
    state = _BlockScanState(
        rel_path=rel_path,
        source_lines=source_lines,
        include_content=include_content,
        min_level=min_level,
        max_level=max_level,
        heading_by_line={heading.start_line: heading for heading in headings},
        separator_lines=frozenset(separator_lines),
        fenced_lines=fenced_lines,
    )
    for line_no in range(window.start_line, window.end_line + 1):
        state.consume(line_no)
    state.finish(window.end_line)
    _assign_block_parents(state.blocks)

    first_anchor_line = int(state.blocks[0]["start_line"]) if state.blocks else None
    first_anchor_local_line = (
        (first_anchor_line - window.start_line + 1)
        if first_anchor_line is not None
        else None
    )

    return {
        "path": rel_path,
        "absolute_path": str(file_path),
        "line_count": source_line_count,
        "scanned_line_count": len(window.lines),
        "heading_count": len(headings),
        "block_count": len(state.blocks),
        "scan_start_line": window.start_line,
        "scan_end_line": window.end_line,
        "first_heading_line": headings[0].start_line if headings else None,
        "first_block_line": first_anchor_line,
        "preamble_nonempty_line_count": _count_preamble_nonempty_lines(
            window.lines,
            first_anchor_local_line,
        ),
        "separator": BLOCK_SEPARATOR,
        "separator_count": len(separator_lines),
        "separator_lines": separator_lines,
        "semantic_separator_count": len(state.semantic_separator_lines),
        "semantic_separator_lines": sorted(state.semantic_separator_lines),
        "orphan_separator_count": len(state.orphan_separator_lines),
        "orphan_separator_lines": sorted(set(state.orphan_separator_lines)),
        "has_unclosed_fence": has_unclosed_fence,
        "blocks": state.blocks,
    }


def scan_markdown_blocks(config: MarkdownScanConfig) -> list[dict[str, Any]]:
    _validate_scan_config(config)
    files = _discover_markdown_files(config)
    parsed: list[dict[str, Any]] = []
    for file_path in files:
        parsed.append(
            _parse_file_blocks(
                root=config.root,
                file_path=file_path,
                min_level=config.min_level,
                max_level=config.max_level,
                config_start_line=config.start_line,
                config_end_line=config.end_line,
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
    _validate_scan_config(config)
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
        start_line=config.start_line,
        end_line=config.end_line,
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


def lint_markdown_blocks(
    config: MarkdownScanConfig,
) -> dict[str, Any]:
    _validate_scan_config(config)
    lint_config = MarkdownScanConfig(
        root=config.root,
        targets=config.targets,
        excludes=config.excludes,
        min_level=config.min_level,
        max_level=config.max_level,
        start_line=config.start_line,
        end_line=config.end_line,
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
            fence_line = (
                int(file_data["line_count"])
                if int(file_data["line_count"]) > 0
                else None
            )
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
                    code="preamble_text_before_first_block",
                    path=file_path,
                    line=1,
                    message="File contains non-empty text before the first block anchor.",
                    details={"nonempty_line_count": preamble_nonempty},
                )
            )

        for separator_line in file_data.get("orphan_separator_lines", []):
            file_issues.append(
                _make_lint_issue(
                    severity="error",
                    code="separator_outside_block_semantics",
                    path=file_path,
                    line=int(separator_line),
                    message=(
                        "`****` separator is outside block semantics (not consumed as a block "
                        "opening/closing boundary)."
                    ),
                )
            )

        seen_titles: dict[tuple[int, str], int] = {}

        for block in blocks:
            start_line = int(block["start_line"])
            end_line = int(block["end_line"])
            level = int(block["level"])
            title = str(block["title"]).strip()

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
            if line_span > HARD_MAX_BLOCK_LINES:
                file_issues.append(
                    _make_lint_issue(
                        severity="error",
                        code="block_too_long",
                        path=file_path,
                        line=start_line,
                        message=(
                            f"Block spans {line_span} lines; hard limit is {HARD_MAX_BLOCK_LINES}."
                        ),
                        details={
                            "line_span": line_span,
                            "max_block_lines": HARD_MAX_BLOCK_LINES,
                            "end_line": end_line,
                        },
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
        warning_count = sum(
            1 for issue in file_issues if issue["severity"] == "warning"
        )
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
        "max_block_lines": HARD_MAX_BLOCK_LINES,
        "files": file_reports,
        "issues": all_issues,
    }
