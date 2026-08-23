# $kw: ^indexlab-resolver --from User.Touched --from Index.Primary.Surface --note [DC] one resolver folds the record stream once and serves every consumer, because a consumer that folds for itself would end up holding a private projection that can disagree with the linter's --note [CT] a citation resolves to a record and never to a file offset, so an anchor that no longer names a live line is a resolution failure rather than a stale byte range
"""Reading the Index as what it is: a collection of `Index.Record`s.

Every consumer that used to open Markdown chapters reads through here instead. The
record stream is the `Index.Primary.Surface`; this folds it into the current semantic
projection and answers the three questions consumers actually ask — *what blocks exist*,
*what does this block say*, and *what does this citation refer to*.

`Line.Type` lives on a record assertion rather than inside the line text. The kernel keeps
assertions opaque, but a reader that understands a particular assertion key may read it,
and `line_type` is exactly such a key.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from tarav._core.project import find_agentos_project_root

from .model import IndexRecord
from .projection import (
    ProjectedBlock,
    ProjectedLine,
    SemanticProjection,
    project_records,
)
from .workspace import IndexLibrary, RecordStore, WorkspaceError


PROJECT_MARKER = ".tarav/project.json"

#: Assertion key carrying a line's `Line.Type` code.
LINE_TYPE_KEY = "line_type"
#: No assertion states a type.
UNTYPED = "UNTYPED"
#: Assertions state more than one type, which is a finding rather than an answer.
CONFLICTED = "CONFLICTED"


class IndexResolutionError(LookupError):
    """A block, line, or citation does not resolve against the record corpus."""


@dataclass(frozen=True, slots=True)
class IndexPointer:
    """Where a project's Index records live."""

    library: Path
    workspace: str

    @classmethod
    def from_project(cls, project_root: Path | str) -> IndexPointer:
        root = Path(project_root)
        marker = root / PROJECT_MARKER
        try:
            data = json.loads(marker.read_text("utf-8"))
        except (OSError, ValueError) as exc:
            raise IndexResolutionError(f"unreadable project marker: {marker}") from exc
        pointer = data.get("index")
        if not isinstance(pointer, dict):
            raise IndexResolutionError(
                f"{marker} declares no Index pointer; add an 'index' object naming "
                "its library and workspace"
            )
        library = pointer.get("library")
        workspace = pointer.get("workspace")
        if not isinstance(library, str) or not isinstance(workspace, str):
            raise IndexResolutionError(
                f"{marker} Index pointer needs 'library' and 'workspace'"
            )
        return cls(library=(root / library).resolve(), workspace=workspace)

    @classmethod
    def for_path(cls, start: Path | str) -> IndexPointer:
        """The Index pointer of the nearest enclosing project."""
        root = find_agentos_project_root(start)
        if root is None:
            raise IndexResolutionError(f"not inside a tarav project: {start}")
        return cls.from_project(root)


# $kw: --note [DC] disagreeing assertions report CONFLICTED instead of letting the first one win, because silently picking a winner would hide exactly the contradiction the linter exists to surface
def line_type(line: ProjectedLine) -> str:
    """The line's `Line.Type`: `UNTYPED` when unstated, `CONFLICTED` when disputed."""
    stated = {
        value
        for assertion in line.assertions
        if isinstance(value := assertion.get(LINE_TYPE_KEY), str) and value.strip()
    }
    if not stated:
        return UNTYPED
    if len(stated) > 1:
        return CONFLICTED
    return stated.pop()


# $kw: --note [DC] the resolver holds a projection and not a store, so it cannot be used to write; readers and writers stay separable without a permission flag
class IndexResolver:
    """The Index as a collection of records, folded once and read many times."""

    def __init__(self, projection: SemanticProjection) -> None:
        self._projection = projection
        self._by_name: dict[str, ProjectedBlock] = {}
        for block in projection.blocks:
            self._by_name.setdefault(block.name, block)

    @classmethod
    def from_records(cls, records: tuple[IndexRecord, ...]) -> IndexResolver:
        return cls(project_records(records))

    @classmethod
    def open(cls, pointer: IndexPointer) -> IndexResolver:
        try:
            workspace = IndexLibrary.open(pointer.library).resolve(pointer.workspace)
        except WorkspaceError as exc:
            raise IndexResolutionError(str(exc)) from exc
        return cls.from_records(RecordStore(workspace).list())

    @classmethod
    def for_project(cls, project_root: Path | str) -> IndexResolver:
        return cls.open(IndexPointer.from_project(project_root))

    @classmethod
    def for_path(cls, start: Path | str) -> IndexResolver:
        return cls.open(IndexPointer.for_path(start))

    @property
    def projection(self) -> SemanticProjection:
        return self._projection

    def blocks(self) -> tuple[ProjectedBlock, ...]:
        return self._projection.blocks

    def block_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._by_name))

    def has_block(self, name: str) -> bool:
        return name in self._by_name

    def block(self, name: str) -> ProjectedBlock:
        try:
            return self._by_name[name]
        except KeyError as exc:
            raise IndexResolutionError(f"unknown Index block: {name}") from exc

    def lines(self, name: str) -> tuple[ProjectedLine, ...]:
        block = self.block(name)
        return tuple(self._projection.line(line_id) for line_id in block.line_ids)

    # $kw: --note [DC] an alias declaration states a name *for* the block rather than content *of* it, so it stays in the corpus and out of any body a consumer materializes
    def content_lines(self, name: str) -> tuple[ProjectedLine, ...]:
        """The block's lines minus its metadata declarations."""
        return tuple(
            line
            for line in self.lines(name)
            if not any(item.get("kind") == "alias" for item in line.assertions)
        )

    # $kw: --note [DC] an alias is carried by an ordinary line's assertion rather than a block field, so reading it costs one pass over the block and the kernel stays unaware of the key
    def aliases(self, name: str) -> tuple[str, ...]:
        """Alternate names this block answers to."""
        found: list[str] = []
        for line in self.lines(name):
            for assertion in line.assertions:
                if assertion.get("kind") != "alias":
                    continue
                values = assertion.get("aliases")
                if isinstance(values, list):
                    found.extend(item for item in values if isinstance(item, str))
        return tuple(dict.fromkeys(found))

    # $kw: --note [DC] a bare Dotted.Name prefers a chapter block over one written on a product surface, because a chapter block is the concept's declared home and a product-surface block is a local use of it
    # $kw: --note [DC] an alias that collides with a canonical concept loses to it, because a name that resolves two ways is worse than an alias that does not resolve
    def blocks_by_locator(self, locator: str) -> tuple[ProjectedBlock, ...]:
        """Every block a locator could mean, so a caller can report ambiguity."""
        block = self._by_name.get(locator)
        if block is not None:
            return (block,)
        if "#" not in locator:
            named = tuple(
                candidate
                for candidate in self._projection.blocks
                if candidate.name.partition("#")[2] == locator
            )
            homes = tuple(
                candidate for candidate in named if not candidate.name.startswith("@")
            )
            if homes:
                return homes
            if named:
                return named
        return tuple(
            candidate
            for candidate in self._projection.blocks
            if locator in self.aliases(candidate.name)
        )

    def block_by_locator(self, locator: str) -> ProjectedBlock | None:
        """A block by full address, else by bare concept name, else by alias."""
        matches = self.blocks_by_locator(locator)
        return matches[0] if len(matches) == 1 else None

    # $kw: --note [DC] a citation carries no `~n` occurrence suffix, so it resolves to the isoline and returns every projection of that one semantic line rather than arbitrarily picking one
    def resolve_citation(self, anchor: str) -> tuple[ProjectedLine, ...]:
        """Every projection of the line an anchor cites."""
        label = anchor if anchor.startswith("^") else f"^{anchor}"
        base = label.split("~", 1)[0]
        matches = tuple(
            line
            for line in self._projection.lines
            if line.label == base or line.label.startswith(f"{base}~")
        )
        if not matches:
            raise IndexResolutionError(f"citation resolves to no Index.Record: {label}")
        return matches
