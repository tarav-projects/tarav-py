# $kw: --from Closure.Parser --from Floor.Model
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tarav._core.scan import DEFAULT_SCAN_EXCLUDES
from tarav.surfaces.markdown import (
    MarkdownFence,
    MarkdownHeading,
    MarkdownNormalModel,
    normalize_markdown,
)

from .label import CITATION_BODY
from .nodes import (
    BlankLine,
    BlockHeading,
    CodeFence,
    Diagnostic,
    IndexDepotModel,
    IndexDocument,
    IndexSurfaceKind,
    InlineSpan,
    KernelLine,
    MetaHeading,
    MetaLine,
    Node,
    RouterEntry,
    Separator,
    Text,
)


_CONCEPT_SEGMENT = r"[A-Z][A-Za-z0-9]*"
_DOTTED_CONCEPT = rf"{_CONCEPT_SEGMENT}(?:\.{_CONCEPT_SEGMENT})+"
_CONCEPT_PARAM = r"(?:[A-Za-z][\w\-.]*|<[A-Z][A-Za-z0-9]*>)"
_TYPE_SIGIL = r"::?"
_CONCEPT_REF = rf"{_DOTTED_CONCEPT}(?:{_TYPE_SIGIL}{_CONCEPT_PARAM})*"
_BLOCK_PATH_SEGMENT = rf"(?:{_CONCEPT_REF}|{_CONCEPT_SEGMENT})"
BLOCK_PATH_RE = re.compile(rf"^{_CONCEPT_REF}(?:/{_BLOCK_PATH_SEGMENT})*$")
APPENDIX_FILENAME_RE = re.compile(
    rf"^(?P<concept>{_CONCEPT_REF})-appendix(?:-(?P<page>[2-9][0-9]*))?\.md$"
)
AGENDIX_FILENAME_RE = re.compile(rf"^(?:{_CONCEPT_REF}|Unassigned)-agendix\.md$")
ISSUE_FILENAME_RE = re.compile(r"^[1-9][0-9]{2}-issues\.md$")
INDEX_FILENAME_RE = re.compile(
    r"^(?P<number>[1-9][0-9]{2})-(?P<chapter>[a-z0-9][a-z0-9-]*)\.md$"
)
ROUTER_ENTRY_RE = re.compile(r"^-\s+`(?P<file>[^`]+\.md)`\s+[—-]\s+(?P<concepts>.+)$")
APPENDIX_ROUTE_ANNOTATION_RE = re.compile(r"\[\+(?P<count>[1-9][0-9]*)\]$")
TYPE_BRACKET_RE = re.compile(r"^- \[(?P<source>AS:)?(?P<act>[A-Z]{2})\] ")
TYPE_BRACKET_CANDIDATE_RE = re.compile(r"^- \[[^\]]+\]")
#: Kept as a name because many modules import it; the grammar itself lives in `label`.
ANCHOR_RE = re.compile(rf"\^(?P<anchor>{CITATION_BODY})\b")
BACKTICK_RE = re.compile(r"`([^`]+)`")
META_HEADING_RE = re.compile(r"^###\s+meta\s*$")


def parse_index_file(
    source: str | Path,
    *,
    path: Path | None = None,
    surface_kind: IndexSurfaceKind = "unknown",
) -> IndexDocument:
    source_path: Path | None = None
    if isinstance(source, Path):
        source_path = source
        text = source.read_text(encoding="utf-8")
    elif "\n" not in source and (candidate := Path(source)).exists():
        source_path = candidate
        text = candidate.read_text(encoding="utf-8")
    else:
        text = source
    document_path = path or source_path
    document = IndexDocument(path=document_path, surface_kind=surface_kind)
    model = normalize_markdown(text)
    if surface_kind == "router" or (
        document_path is not None and document_path.name == "000-INDEX.md"
    ):
        document.nodes.extend(_parse_router(model, document_path))
        return document
    document.nodes.extend(_parse_index_surface(model, document_path))
    return document


def parse_depot(root: str | Path) -> IndexDepotModel:
    depot_root = Path(root).resolve()
    documents: list[IndexDocument] = []
    router = depot_root / "000-INDEX.md"
    if router.is_file():
        documents.append(parse_index_file(router, surface_kind="router"))
    for path in _surface_files(depot_root):
        documents.append(
            parse_index_file(path, surface_kind=_classify_surface(depot_root, path))
        )
    return IndexDepotModel(root=depot_root, documents=tuple(documents))


def _parse_router(model: MarkdownNormalModel, path: Path | None) -> list[Node]:
    nodes: list[Node] = []
    fenced_lines = model.fenced_line_numbers()
    for source_line in model.lines:
        line_no = source_line.span.start_line
        line = source_line.text
        if line_no in fenced_lines:
            nodes.append(_plain_node(line, line_no, path))
            continue
        match = ROUTER_ENTRY_RE.match(line.strip())
        if match is None:
            nodes.append(_plain_node(line, line_no, path))
            continue
        nodes.append(
            RouterEntry(
                src=line,
                start_line=line_no,
                end_line=line_no,
                parsed={
                    "file": match.group("file"),
                    "concepts": [
                        _parse_router_concept(raw)
                        for raw in match.group("concepts").split(",")
                    ],
                },
                spans=_inline_spans(line, line_no),
                path=path,
            )
        )
    return nodes


def _parse_index_surface(model: MarkdownNormalModel, path: Path | None) -> list[Node]:
    state = _IndexSurfaceState(path=path)
    fence_by_start = {fence.start.start_line: fence for fence in model.fences}
    heading_by_line = {heading.span.start_line: heading for heading in model.headings}
    skip_through = 0

    for source_line in model.lines:
        line_no = source_line.span.start_line
        if line_no <= skip_through:
            continue
        fence = fence_by_start.get(line_no)
        if fence is not None:
            node, skip_through = _fence_node(model, fence, path)
            state.nodes.append(node)
            continue
        state.consume(
            line_no=line_no,
            line=source_line.text,
            heading=heading_by_line.get(line_no),
        )
    return state.nodes


def _fence_node(
    model: MarkdownNormalModel,
    fence: MarkdownFence,
    path: Path | None,
) -> tuple[Node, int]:
    start_line = fence.start.start_line
    end_line = fence.end.start_line if fence.end is not None else len(model.lines)
    source = "\n".join(item.text for item in model.lines[start_line - 1 : end_line])
    if fence.end is None:
        return (
            Diagnostic(
                src=source,
                start_line=start_line,
                end_line=max(start_line, end_line),
                reason="unclosed_code_fence",
                path=path,
            ),
            end_line,
        )
    return (
        CodeFence(
            src=source,
            start_line=start_line,
            end_line=end_line,
            parsed={"closed": True},
            path=path,
        ),
        end_line,
    )


@dataclass
class _IndexSurfaceState:
    path: Path | None
    nodes: list[Node] = field(default_factory=list)
    block_open: bool = False
    expect_heading: bool = False
    current_block: str | None = None
    in_meta: bool = False

    def consume(
        self,
        *,
        line_no: int,
        line: str,
        heading: MarkdownHeading | None,
    ) -> None:
        stripped = line.strip()
        if re.fullmatch(r"\*{4,}", stripped):
            self._separator(line_no, line)
        elif not stripped:
            self.nodes.append(
                BlankLine(
                    src=line,
                    start_line=line_no,
                    end_line=line_no,
                    path=self.path,
                )
            )
        elif heading is not None and heading.level == 2:
            self._block_heading(line_no, line, heading.text)
        elif META_HEADING_RE.match(line):
            self.in_meta = True
            self.nodes.append(
                MetaHeading(
                    src=line,
                    start_line=line_no,
                    end_line=line_no,
                    path=self.path,
                )
            )
        elif line.startswith("- ") and self.block_open and self.current_block:
            self._block_line(line_no, line)
        else:
            self.nodes.append(_plain_node(line, line_no, self.path))

    def _separator(self, line_no: int, line: str) -> None:
        self.block_open = True
        self.expect_heading = True
        self.current_block = None
        self.in_meta = False
        self.nodes.append(
            Separator(
                src=line,
                start_line=line_no,
                end_line=line_no,
                path=self.path,
            )
        )

    def _block_heading(self, line_no: int, line: str, heading: str) -> None:
        if not self.block_open or not self.expect_heading:
            self.nodes.append(
                Diagnostic(
                    src=line,
                    start_line=line_no,
                    end_line=line_no,
                    parsed={"heading": heading},
                    reason="heading_without_separator",
                    path=self.path,
                )
            )
        self.nodes.append(
            BlockHeading(
                src=line,
                start_line=line_no,
                end_line=line_no,
                parsed=_parse_block_path(heading),
                spans=_inline_spans(line, line_no),
                path=self.path,
            )
        )
        self.current_block = heading
        self.expect_heading = False
        self.in_meta = False

    def _block_line(self, line_no: int, line: str) -> None:
        node_cls = MetaLine if self.in_meta else KernelLine
        parsed = {"block_path": self.current_block}
        if node_cls is KernelLine:
            parsed.update(_parse_kernel_line(line))
        self.nodes.append(
            node_cls(
                src=line,
                start_line=line_no,
                end_line=line_no,
                parsed=parsed,
                spans=_inline_spans(line, line_no),
                path=self.path,
            )
        )


def _plain_node(line: str, line_no: int, path: Path | None) -> Node:
    if line.strip() == "":
        return BlankLine(src=line, start_line=line_no, end_line=line_no, path=path)
    return Text(
        src=line,
        start_line=line_no,
        end_line=line_no,
        spans=_inline_spans(line, line_no),
        path=path,
    )


def _parse_kernel_line(line: str) -> dict[str, Any]:
    match = TYPE_BRACKET_RE.match(line)
    if match is None:
        return {}
    return {
        "act": match.group("act"),
        "source": "AS" if match.group("source") else None,
    }


def _parse_block_path(path: str) -> dict[str, Any]:
    root, *segments = path.split("/")
    root_name, *params = re.split(_TYPE_SIGIL, root)
    return {
        "path": path,
        "root": root_name,
        "params": params,
        "segments": segments,
        "valid": bool(BLOCK_PATH_RE.fullmatch(path)),
    }


def _parse_router_concept(raw_concept: str) -> dict[str, Any]:
    raw = raw_concept.strip().strip("`")
    concept = raw.split(" — ", 1)[0].strip()
    plus_n = None
    annotation = APPENDIX_ROUTE_ANNOTATION_RE.search(concept)
    if annotation is not None:
        plus_n = int(annotation.group("count"))
        concept = concept[: annotation.start()].strip()
    return {"concept": concept, "plus_n": plus_n, "raw": raw}


def _inline_spans(src: str, base_line: int) -> list[InlineSpan]:
    spans: list[InlineSpan] = []
    type_match = TYPE_BRACKET_CANDIDATE_RE.match(src)
    if type_match is not None:
        parsed: dict[str, Any] = {}
        typed = TYPE_BRACKET_RE.match(src)
        if typed is not None:
            parsed = {
                "act": typed.group("act"),
                "source": "AS" if typed.group("source") else None,
            }
        spans.append(
            _span(
                "type_bracket",
                src,
                base_line,
                type_match.start() + 2,
                type_match.end(),
                parsed,
            )
        )
    for match in BACKTICK_RE.finditer(src):
        body = match.group(1)
        kind = (
            "file_mention"
            if _is_file_mention(body)
            else "concept_cite"
            if _is_concept_like(body)
            else ""
        )
        if kind:
            spans.append(
                _span(kind, src, base_line, match.start(), match.end(), {"value": body})
            )
    for match in ANCHOR_RE.finditer(src):
        spans.append(
            _span(
                "anchor",
                src,
                base_line,
                match.start(),
                match.end(),
                {"anchor": match.group("anchor")},
            )
        )
    return sorted(spans, key=lambda span: (span.start, span.end))


def _span(
    kind: str,
    src: str,
    base_line: int,
    start: int,
    end: int,
    parsed: dict[str, Any] | None = None,
) -> InlineSpan:
    return InlineSpan(
        kind=kind,
        src=src[start:end],
        start=start,
        end=end,
        line=base_line,
        column=start + 1,
        parsed=dict(parsed or {}),
    )


def _is_file_mention(value: str) -> bool:
    return "/" in value or value.endswith(
        (".md", ".py", ".json", ".jsonl", ".toml", ".txt")
    )


def _is_concept_like(value: str) -> bool:
    return bool(re.search(rf"\b{_CONCEPT_SEGMENT}\.{_CONCEPT_SEGMENT}", value))


def _surface_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(root.rglob("*.md")):
        if path.name in {"000-INDEX.md", "AGENTS.md"}:
            continue
        rel_parts = set(path.relative_to(root).parts)
        if any(part in DEFAULT_SCAN_EXCLUDES for part in rel_parts):
            continue
        if _classify_surface(root, path) == "unknown":
            continue
        files.append(path)
    return files


def _classify_surface(root: Path, path: Path) -> IndexSurfaceKind:
    rel = path.relative_to(root)
    if path.name == "000-INDEX.md" and len(rel.parts) == 1:
        return "router"
    if (
        len(rel.parts) == 2
        and rel.parts[0] == "issues"
        and ISSUE_FILENAME_RE.fullmatch(path.name)
    ):
        return "issues"
    if len(rel.parts) == 2 and INDEX_FILENAME_RE.fullmatch(path.name):
        match = INDEX_FILENAME_RE.fullmatch(path.name)
        if match and match.group("chapter") == rel.parts[0]:
            return "chapter"
    if (
        len(rel.parts) == 2
        and rel.parts[0] == "appendix"
        and APPENDIX_FILENAME_RE.fullmatch(path.name)
    ):
        return "appendix"
    if (
        len(rel.parts) == 2
        and rel.parts[0] == "agendix"
        and AGENDIX_FILENAME_RE.fullmatch(path.name)
    ):
        return "agendix"
    return "unknown"
