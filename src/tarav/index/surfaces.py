# $kw: --from Index.Surface --note [CT] index lines attach to any skw annotation through the same mechanism as the markdown index
"""Index surfaces — where entries are materialized.

An index's data is **distributed across surfaces**. Two hosting kinds today, and the model
treats them identically because their scopes are addresses in one grammar:

- an `Index.Native.Surface` — a chapter under a home, hosting kernel lines directly;
- an ordinary `Product.Surface` — hosting lines inside a `Skw.Annotation`.

Parsing for both comes from the shared kernels (`tarav.index_model.parser`, `tarav.skillware.model`).
Neither changed, so neither is rewritten.

There is no landing API. Agents edit these files with ordinary file primitives; the linter
checks conformance afterwards.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from tarav.index_model.nodes import BlockHeading, KernelLine
from tarav.index_model.parser import parse_depot, parse_index_file
from tarav.index_model.label import parse_citation, split_trailing_address
from tarav.surfaces.markdown import normalize_markdown

from .config import Geography, TaravIndexError
from .record.identity import split_statement
from .record.store import normalize_label
from .scope import LineScope, annotation_scope, block_scope, resolve_scope_surface

ROUTER_NAME = "000-INDEX.md"
DEFAULT_CHAPTER = "design"
SKW_SURFACE_PREFIX = "skw:"

HOMES_FILE = "homes.json"
HOMES_SCHEMA = "tarav.homes.v1"
DEFAULT_USER_HOME = "ceo"


class SurfaceError(TaravIndexError):
    """Raised when a surface cannot be resolved or read."""


@dataclass(frozen=True, slots=True)
class SurfaceLine:
    """One index line as it appears on a surface, with the scope that groups it."""

    scope: LineScope
    line_type: str | None
    body: str
    labels: tuple[str, ...]
    lineno: int

    @property
    def label(self) -> str | None:
        """The line's public id as it appears to a reader."""

        return self.labels[0] if self.labels else None

    @property
    def typed(self) -> bool:
        return self.line_type is not None


def _depot_and_chapter(path: Path, surface: str) -> tuple[str, str]:
    """Derive a block address from the nearest structurally marked Index depot."""

    for parent in path.parents:
        if (parent / ROUTER_NAME).is_file():
            relative = path.relative_to(parent)
            chapter = relative.parts[0] if len(relative.parts) > 1 else path.stem
            return parent.name, chapter

    parts = Path(surface).parts
    depot = parts[1] if len(parts) > 1 else "unknown"
    stem = Path(surface).stem
    chapter = stem.split("-", 1)[1] if "-" in stem else stem
    return depot, chapter


def read_block_lines(
    path: Path, surface: str, *, kind: str = "chapter"
) -> list[SurfaceLine]:
    """Kernel lines from an `Index.Native.Surface`, scoped by `Block.Path`.

    ``kind`` must be passed: with the parser's default of ``"unknown"`` every kernel line is
    classified as plain text and the surface silently reads as empty. Blocks are also
    separator-anchored — a `## Concept` without its `****` yields no kernel lines.
    """

    document = parse_index_file(path, surface_kind=kind)
    depot, chapter = _depot_and_chapter(path, surface)
    lines: list[SurfaceLine] = []
    concept = ""

    for node in document.nodes:
        if isinstance(node, BlockHeading):
            concept = str(node.parsed.get("title") or node.src.lstrip("# ").strip())
        elif isinstance(node, KernelLine) and concept:
            line_type, body = split_statement(node.src)
            labels = tuple(
                normalize_label(str(span.parsed.get("anchor") or span.src))
                for span in node.spans
                if span.kind == "anchor"
            )
            lines.append(
                SurfaceLine(
                    scope=block_scope(depot, chapter, concept),
                    line_type=line_type,
                    body=body,
                    labels=labels,
                    lineno=node.start_line,
                )
            )
    return lines


def read_annotation_lines(path: Path, surface: str) -> list[SurfaceLine]:
    """Index lines hosted by `Skw.Annotation` blocks, scoped by `Locator.Name`.

    Skw itself is unchanged — its `$kw` language and its `build|check|bless|status` surface
    stay in the shared kernels. What is new is only that the typed `--note`/`--supp` lines it already
    carries are index lines, scoped by the attachment point they annotate.
    """

    from tarav.skillware.model import parse_skw_code

    file_path = surface.removeprefix(SKW_SURFACE_PREFIX)
    try:
        source = parse_skw_code(path.read_text("utf-8"))
    except (OSError, ValueError, SyntaxError):
        return []

    lines: list[SurfaceLine] = []
    for note in source.notes:
        if not note.text.strip():
            continue
        lines.append(
            SurfaceLine(
                scope=annotation_scope(file_path, note.address),
                line_type=note.type,
                body=" ".join(note.text.split()),
                labels=(normalize_label(note.anchor),) if note.anchor else (),
                lineno=note.line,
            )
        )
    return lines


# $kw: Index.Capture/Live.Markdown --from Floor.Model --note [DC] explicit live-Markdown capture consumes Tarav's native Markdown model and adds only the heading-scoped Index interpretation ^c20260821-43u
def read_markdown_heading_lines(
    path: Path,
    surface: str,
    block: str,
) -> list[SurfaceLine]:
    """Index-shaped bullets under one ordinary Markdown heading.

    A Capture.Manifest may target a live design artifact before the project's default
    evaluator discovers that surface kind. The native Markdown parser supplies host facts;
    this Index adapter supplies the domain interpretation and explicit locator scope.
    """

    scope = annotation_scope(surface, block)
    model = normalize_markdown(path.read_text(encoding="utf-8"))
    headings = [heading for heading in model.headings if heading.text == block]
    if len(headings) != 1:
        raise SurfaceError(
            f"Markdown capture target {surface} has {len(headings)} headings named {block!r}"
        )
    heading = headings[0]
    next_heading = next(
        (
            candidate
            for candidate in model.headings
            if candidate.span.start_line > heading.span.start_line
            and candidate.level <= heading.level
        ),
        None,
    )
    end_line = (
        next_heading.span.start_line
        if next_heading is not None
        else len(model.lines) + 1
    )
    fenced = model.fenced_line_numbers()
    lines: list[SurfaceLine] = []
    for source in model.lines:
        lineno = source.span.start_line
        if not (heading.span.start_line < lineno < end_line) or lineno in fenced:
            continue
        if not source.text.lstrip().startswith("- "):
            continue
        line_type, body = split_statement(source.text)
        _without_address, address = split_trailing_address(source.text)
        citation = parse_citation(address) if address is not None else None
        labels = (normalize_label(address),) if citation is not None else ()
        lines.append(
            SurfaceLine(
                scope=scope,
                line_type=line_type,
                body=body,
                labels=labels,
                lineno=lineno,
            )
        )
    return lines


def surface_kind_for(surface: str) -> str:
    if surface.startswith(SKW_SURFACE_PREFIX):
        return "skw"
    if "/appendix/" in surface:
        return "appendix"
    if "/agendix/" in surface:
        return "agendix"
    if "/issues/" in surface:
        return "issues"
    return "chapter"


def read_surface(
    path: Path, surface: str, *, kind: str | None = None
) -> list[SurfaceLine]:
    """Read index lines from a surface of any hosting kind."""

    resolved = kind or surface_kind_for(surface)
    if resolved == "skw":
        return read_annotation_lines(path, surface)
    return read_block_lines(path, surface, kind=resolved)


def resolve_surface_path(surface: str, root: Path) -> Path:
    if surface.startswith(SKW_SURFACE_PREFIX):
        return root / surface[len(SKW_SURFACE_PREFIX) :]
    return root / surface


# $kw: Index.Evaluator/Surface.Discovery --from Skw.Touched.Index --note [DC] markdown chapters and skw-annotated code are discovered by the one pass, because index lines attach to any skw annotation through the same mechanism as the markdown index ^c20260729-173u
# --note [CT] a surface outside these patterns is not reported as unchecked, it is absent from the run — discovery scope sits upstream of every verdict ^c20260819-25u
# --note [DC] The default Index evaluator derives project identity from .tarav/project.json and resolves evidence and surfaces structurally, without evaluator manifests. ^c20260821-1u
def discover_surfaces(scopes: Geography, root: Path) -> list[str]:
    """Every index surface reachable in this project, recorded or not.

    Discovery is independent of the store on purpose: a surface the index has never heard of
    is exactly the case worth finding.
    """

    surfaces: list[str] = []

    for router in sorted(root.rglob(ROUTER_NAME)):
        relative = router.relative_to(root)
        if any(
            part in {".venv", "node_modules", ".git", "_DEPRECATED"}
            for part in relative.parts
        ):
            continue
        depot = parse_depot(router.parent)
        surfaces.extend(
            str(document.path.relative_to(root))
            for document in depot.documents
            if document.path is not None and document.path.name != ROUTER_NAME
        )

    # Code is not a self-discovering Index corpus. Skillware owns the configured
    # host-language floor and adapts each selected file through Tarav's native
    # surface parser. Index consumes that model; it neither globs Python nor
    # recognizes `$kw` machinery independently.
    from tarav.skillware._build_core import SkillwareError, load_project_skw_config
    from tarav.skillware._code_surfaces import (
        DEFAULT_CODE_BACKENDS,
        expand_code_surfaces,
    )

    try:
        config = load_project_skw_config(root)
        targets = expand_code_surfaces(
            root,
            config.code_surfaces,
            backends=DEFAULT_CODE_BACKENDS,
        )
        for target in targets:
            backend = DEFAULT_CODE_BACKENDS.get(target.language)
            if backend is None:  # guarded by expand_code_surfaces
                continue
            model = backend.model(
                target.path.read_text(encoding="utf-8", errors="replace")
            )
            if model.annotations.machinery_spans:
                relative = target.path.relative_to(root)
                surfaces.append(f"{SKW_SURFACE_PREFIX}{relative}")
    except (OSError, SkillwareError) as exc:
        raise SurfaceError(f"cannot discover configured Skw surfaces: {exc}") from exc

    return sorted(set(surfaces))


@dataclass(frozen=True, slots=True)
class Homes:
    """Which homes carry `Index.Notes`.

    The `Serialized.Index` can host all of a record; `Index.Notes` hosts only its public part
    — literally the index lines — and exists for readers. A home may legitimately carry the
    serialized side alone, and for such a home "materialized on no surface" is the normal
    state rather than a defect.
    """

    #: Homes with no `Index.Notes`. Everything not listed carries notes.
    serialized_only: frozenset[str] = frozenset()

    def carries_notes(self, home: str) -> bool:
        return home not in self.serialized_only

    def to_json(self) -> dict[str, object]:
        return {"schema": HOMES_SCHEMA, "serialized_only": sorted(self.serialized_only)}


def homes_path(geo: Geography) -> Path:
    return geo.project_tier / HOMES_FILE


# $kw: --from Touched.Index.Record --note [CT] a home may carry the serialized record alone, so "materialized on no surface" is a normal state and not a defect ^c20260818-9u
def load_homes(geo: Geography) -> Homes:
    path = homes_path(geo)
    if not path.exists():
        return Homes()
    try:
        payload = json.loads(path.read_text("utf-8"))
        return Homes(
            serialized_only=frozenset(
                str(h) for h in payload.get("serialized_only", ())
            )
        )
    except (OSError, ValueError):
        raise SurfaceError(f"malformed homes declaration at {path}") from None


# $kw: --from Index.Head.Surface --note [DC] a scope names a depot and chapter but never a home, so the home is resolved from where the chapter is found ^c20260819-26u
def scope_home(scope: LineScope, root: Path) -> str | None:
    """The home a block scope resolves into, or ``None`` when it resolves nowhere."""

    path = resolve_scope_surface(scope, root)
    if path is None:
        return None
    parts = path.parts
    for index, part in enumerate(parts):
        if part == "homes" and index + 1 < len(parts):
            return parts[index + 1]
    return None


@dataclass(frozen=True, slots=True)
class ProjectIndex:
    """One structurally marked depot rooted at ``skills/<depot>/``."""

    root: Path
    depot: str
    home: str = DEFAULT_USER_HOME

    @property
    def depot_root(self) -> Path:
        return self.root / "skills" / self.depot

    @property
    def home_root(self) -> Path:
        return self.depot_root

    @property
    def chapters_dir(self) -> Path:
        return self.depot_root / DEFAULT_CHAPTER

    @property
    def appendix_dir(self) -> Path:
        return self.depot_root / "appendix"

    def chapter_path(self, chapter: str = DEFAULT_CHAPTER) -> Path:
        matches = sorted(self.chapters_dir.glob(f"*-{chapter}.md"))
        return matches[0] if matches else self.chapters_dir / f"100-{chapter}.md"

    def ensure_layout(self) -> Path:
        """Create the depot and both homes. Idempotent."""

        self.chapters_dir.mkdir(parents=True, exist_ok=True)
        self.appendix_dir.mkdir(parents=True, exist_ok=True)
        marker = self.depot_root / ROUTER_NAME
        if not marker.exists():
            marker.write_text(f"# {self.depot} Index\n", encoding="utf-8")
        return self.depot_root


__all__ = [
    "DEFAULT_CHAPTER",
    "ROUTER_NAME",
    "SKW_SURFACE_PREFIX",
    "Homes",
    "ProjectIndex",
    "SurfaceError",
    "SurfaceLine",
    "discover_surfaces",
    "homes_path",
    "load_homes",
    "read_annotation_lines",
    "read_block_lines",
    "read_markdown_heading_lines",
    "read_surface",
    "resolve_surface_path",
    "scope_home",
    "surface_kind_for",
]
