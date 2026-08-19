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
from pathlib import Path, PurePosixPath

from tarav.index.model.nodes import BlockHeading, KernelLine
from tarav.index.model.parser import parse_index_file

from .authority import (
    AGENT_HOME_NAME,
    DEFAULT_USER_HOME,
    HOMES_DIR_NAME,
    assert_agent_writable,
)
from .config import Geography, TaravIndexError
from .record.identity import split_statement
from .record.store import normalize_label
from .scope import LineScope, annotation_scope, block_scope, resolve_scope_surface

ROUTER_NAME = "000-INDEX.md"
DEFAULT_CHAPTER = "design"
SKW_SURFACE_PREFIX = "skw:"

HOMES_FILE = "homes.json"
HOMES_SCHEMA = "tarav.homes.v1"

HEAD_SURFACES_FILE = "head-surfaces.json"
HEAD_SURFACES_SCHEMA = "tarav.head-surfaces.v1"

#: Chapters are the promoted surface; appendix is depth, not current design.
DEFAULT_HEAD_PATTERNS: tuple[str, ...] = ("skills/*/homes/*/chapters/*.md",)


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


def _depot_and_chapter(surface: str) -> tuple[str, str]:
    """`skills/<depot>/homes/<home>/chapters/NNN-<chapter>.md` → (depot, chapter)."""

    parts = Path(surface).parts
    depot = parts[1] if len(parts) > 1 else "unknown"
    stem = Path(surface).stem
    chapter = stem.split("-", 1)[1] if "-" in stem else stem
    return depot, chapter


def read_block_lines(path: Path, surface: str, *, kind: str = "chapter") -> list[SurfaceLine]:
    """Kernel lines from an `Index.Native.Surface`, scoped by `Block.Path`.

    ``kind`` must be passed: with the parser's default of ``"unknown"`` every kernel line is
    classified as plain text and the surface silently reads as empty. Blocks are also
    separator-anchored — a `## Concept` without its `****` yields no kernel lines.
    """

    document = parse_index_file(path, surface_kind=kind)
    depot, chapter = _depot_and_chapter(surface)
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


def surface_kind_for(surface: str) -> str:
    if surface.startswith(SKW_SURFACE_PREFIX):
        return "skw"
    if "/appendix/" in surface:
        return "appendix"
    return "chapter"


def read_surface(path: Path, surface: str, *, kind: str | None = None) -> list[SurfaceLine]:
    """Read index lines from a surface of any hosting kind."""

    resolved = kind or surface_kind_for(surface)
    if resolved == "skw":
        return read_annotation_lines(path, surface)
    return read_block_lines(path, surface, kind=resolved)


def resolve_surface_path(surface: str, root: Path) -> Path:
    if surface.startswith(SKW_SURFACE_PREFIX):
        return root / surface[len(SKW_SURFACE_PREFIX) :]
    return root / surface


def discover_surfaces(scopes: Geography, root: Path) -> list[str]:
    """Every index surface reachable in this project, recorded or not.

    Discovery is independent of the store on purpose: a surface the index has never heard of
    is exactly the case worth finding.
    """

    surfaces: list[str] = []

    skills = root / "skills"
    if skills.exists():
        for pattern in ("*/homes/*/chapters/*.md", "*/homes/*/appendix/*.md"):
            surfaces.extend(str(p.relative_to(root)) for p in sorted(skills.glob(pattern)))

    for python in sorted(root.rglob("*.py")):
        if any(part in {".venv", "__pycache__", "node_modules", ".git"} for part in python.parts):
            continue
        try:
            if "$kw:" in python.read_text("utf-8", errors="ignore"):
                surfaces.append(f"{SKW_SURFACE_PREFIX}{python.relative_to(root)}")
        except OSError:
            continue

    return surfaces


@dataclass(frozen=True, slots=True)
class HeadSurfaces:
    """Which surfaces carry the index HEAD.

    A line is in the HEAD if it is on a `HEAD.Surface` — that is what *promoted* means,
    stated positively. Nothing on a record says "I am current design"; the standing comes
    from where the line actually is, which git tracks and a reader can diff.

    That makes this set the **trust root**, so it is declared project-tier state rather than
    inferred from a path. Inferred, an agent would make anything current design by creating a
    file; declared, widening it is a diff a human reads.
    """

    patterns: tuple[str, ...] = DEFAULT_HEAD_PATTERNS

    def contains(self, surface: str) -> bool:
        if surface.startswith(SKW_SURFACE_PREFIX):
            return False
        path = PurePosixPath(surface)
        if f"{HOMES_DIR_NAME}/{AGENT_HOME_NAME}" in surface:
            # The agent home is where unpromoted material lives, so it is never a
            # HEAD.Surface. Promotion means moving the line to a home that carries
            # promoted content, and that move is what the landing gate licenses.
            return False
        return any(path.match(pattern) for pattern in self.patterns)

    def to_json(self) -> dict[str, object]:
        return {"schema": HEAD_SURFACES_SCHEMA, "patterns": list(self.patterns)}


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


def load_homes(geo: Geography) -> Homes:
    path = homes_path(geo)
    if not path.exists():
        return Homes()
    try:
        payload = json.loads(path.read_text("utf-8"))
        return Homes(serialized_only=frozenset(str(h) for h in payload.get("serialized_only", ())))
    except (OSError, ValueError):
        raise SurfaceError(f"malformed homes declaration at {path}") from None


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


def head_surfaces_path(geo: Geography) -> Path:
    return geo.project_tier / HEAD_SURFACES_FILE


def load_head_surfaces(geo: Geography) -> HeadSurfaces:
    """Read the declaration, falling back to the default so a fresh project still works."""

    path = head_surfaces_path(geo)
    if not path.exists():
        return HeadSurfaces()
    try:
        payload = json.loads(path.read_text("utf-8"))
        patterns = tuple(str(p) for p in payload.get("patterns", ()))
    except (OSError, ValueError):
        raise SurfaceError(f"malformed HEAD.Surface declaration at {path}") from None
    return HeadSurfaces(patterns=patterns or DEFAULT_HEAD_PATTERNS)


def write_head_surfaces(geo: Geography, patterns: tuple[str, ...] | None = None) -> Path:
    """Declare the HEAD.Surface set. Idempotent; `init` calls it with the default."""

    declared = HeadSurfaces(patterns=patterns or DEFAULT_HEAD_PATTERNS)
    path = head_surfaces_path(geo)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(declared.to_json(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return path


@dataclass(frozen=True, slots=True)
class ProjectIndex:
    """One depot rooted at ``skills/<depot>/``."""

    root: Path
    depot: str
    home: str = DEFAULT_USER_HOME

    @property
    def depot_root(self) -> Path:
        return self.root / "skills" / self.depot

    @property
    def home_root(self) -> Path:
        return self.depot_root / "homes" / self.home

    @property
    def chapters_dir(self) -> Path:
        return self.home_root / "chapters"

    @property
    def appendix_dir(self) -> Path:
        return self.home_root / "appendix"

    def chapter_path(self, chapter: str = DEFAULT_CHAPTER) -> Path:
        matches = sorted(self.chapters_dir.glob(f"*-{chapter}.md"))
        return matches[0] if matches else self.chapters_dir / f"100-{chapter}.md"

    def ensure_layout(self) -> Path:
        """Create the depot and both homes. Idempotent."""

        self.chapters_dir.mkdir(parents=True, exist_ok=True)
        self.appendix_dir.mkdir(parents=True, exist_ok=True)
        agent_home = self.depot_root / "homes" / "agent"
        agent_home.mkdir(parents=True, exist_ok=True)
        marker = agent_home / ".tarav.index"
        if not marker.exists():
            marker.write_text(
                "# agent home\n"
                "# serialized only: the Agent.Chromosome carries no authored prose surfaces\n",
                encoding="utf-8",
            )
        return self.depot_root

    def assert_writable(self) -> None:
        assert_agent_writable(self.home_root)


__all__ = [
    "DEFAULT_CHAPTER",
    "DEFAULT_HEAD_PATTERNS",
    "HEAD_SURFACES_FILE",
    "ROUTER_NAME",
    "SKW_SURFACE_PREFIX",
    "HeadSurfaces",
    "Homes",
    "ProjectIndex",
    "SurfaceError",
    "SurfaceLine",
    "discover_surfaces",
    "head_surfaces_path",
    "homes_path",
    "load_head_surfaces",
    "load_homes",
    "read_annotation_lines",
    "read_block_lines",
    "read_surface",
    "resolve_surface_path",
    "scope_home",
    "surface_kind_for",
    "write_head_surfaces",
]
