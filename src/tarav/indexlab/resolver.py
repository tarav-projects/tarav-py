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

from .model import IndexRecord
from .projection import (
    ProjectedBlock,
    ProjectedLine,
    SemanticProjection,
    project_records,
)
from .workspace import IndexLibrary, RecordStore, WorkspaceError


PROJECT_MARKER = ".tarav/project.json"
UNTYPED = "UNTYPED"


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


def line_type(line: ProjectedLine) -> str:
    """The line's `Line.Type`, or `UNTYPED` when no assertion carries one."""
    for assertion in line.assertions:
        value = assertion.get("line_type")
        if isinstance(value, str) and value:
            return value
    return UNTYPED


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
