"""The Index read as records: blocks by name, line types, citations."""

from __future__ import annotations

import json

import pytest

from tarav.indexlab import (
    IndexPointer,
    IndexResolutionError,
    IndexResolver,
    line_type,
)
from tarav.indexlab.model import (
    IndexRecord,
    Operation,
    RecordContext,
    SupportSet,
    TurnRef,
)


def _context() -> RecordContext:
    return RecordContext(session="s-1", horizon=TurnRef(address="t-1", hash="0" * 16))


def _record(
    ordinal: int,
    operation: str,
    parameters: dict[str, object],
    assertions: tuple[dict[str, object], ...] = (),
) -> IndexRecord:
    return IndexRecord(
        id=f"rec_{ordinal}",
        ordinal=ordinal,
        context=_context(),
        operation=Operation(type=operation, parameters=parameters),
        support=SupportSet(neighborhoods=()),
        assertions=assertions,
    )


def _corpus() -> tuple[IndexRecord, ...]:
    return (
        _record(
            1,
            "block.create",
            {"block_id": "b1", "isoblock_id": "ib1", "name": "depot/design#Alpha"},
        ),
        _record(
            2,
            "line.capture",
            {
                "line_id": "l1",
                "isoline_id": "il1",
                "block_id": "b1",
                "label": "^c20260101-1u",
                "text": "alpha says a thing",
            },
            ({"line_type": "DF"},),
        ),
        _record(
            3,
            "line.capture",
            {
                "line_id": "l2",
                "isoline_id": "il1",
                "block_id": "b1",
                "label": "^c20260101-1u~2",
                "text": "alpha repeats elsewhere",
            },
            ({"line_type": "CT"},),
        ),
        _record(
            4,
            "line.capture",
            {
                "line_id": "l3",
                "isoline_id": "il2",
                "block_id": "b1",
                "label": "^c20260101-9u",
                "text": "no assertion carries a type",
            },
            ({"migrated_by": "test"},),
        ),
    )


def test_blocks_resolve_by_name() -> None:
    resolver = IndexResolver.from_records(_corpus())
    assert resolver.has_block("depot/design#Alpha")
    assert resolver.block_names() == ("depot/design#Alpha",)
    assert len(resolver.lines("depot/design#Alpha")) == 3


def test_unknown_block_names_a_lookup_failure() -> None:
    resolver = IndexResolver.from_records(_corpus())
    with pytest.raises(IndexResolutionError, match="unknown Index block"):
        resolver.block("depot/design#Missing")


def test_line_type_reads_the_assertion_and_falls_back_to_untyped() -> None:
    resolver = IndexResolver.from_records(_corpus())
    types = [line_type(line) for line in resolver.lines("depot/design#Alpha")]
    assert types == ["DF", "CT", "UNTYPED"]


# A citation names one semantic line, and that line may be projected several times.
def test_citation_resolves_to_every_projection_of_its_isoline() -> None:
    resolver = IndexResolver.from_records(_corpus())
    lines = resolver.resolve_citation("c20260101-1u")
    assert {line.text for line in lines} == {
        "alpha says a thing",
        "alpha repeats elsewhere",
    }
    assert resolver.resolve_citation("^c20260101-1u") == lines


def test_unresolvable_citation_is_a_failure_not_an_empty_answer() -> None:
    resolver = IndexResolver.from_records(_corpus())
    with pytest.raises(IndexResolutionError, match="resolves to no Index.Record"):
        resolver.resolve_citation("c20990101-1u")


def test_project_pointer_names_the_library_and_workspace(tmp_path) -> None:
    marker = tmp_path / ".tarav" / "project.json"
    marker.parent.mkdir()
    marker.write_text(
        json.dumps({"index": {"library": "lib", "workspace": "ws"}}), "utf-8"
    )
    pointer = IndexPointer.from_project(tmp_path)
    assert pointer.workspace == "ws"
    assert pointer.library == (tmp_path / "lib").resolve()


def test_project_without_an_index_pointer_says_so(tmp_path) -> None:
    marker = tmp_path / ".tarav" / "project.json"
    marker.parent.mkdir()
    marker.write_text(json.dumps({"class": "agentos.project"}), "utf-8")
    with pytest.raises(IndexResolutionError, match="declares no Index pointer"):
        IndexPointer.from_project(tmp_path)
