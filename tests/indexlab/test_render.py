from __future__ import annotations

import pytest

from tarav.indexlab import (
    EvidenceNeighborhood,
    IndexRecord,
    MessageRef,
    Operation,
    RecordContext,
    RenderError,
    SupportSet,
    TurnRef,
    project_records,
    render_kernel_writing,
)


def _record(
    ordinal: int,
    operation: str,
    parameters: dict[str, object],
    *,
    assertions: tuple[dict[str, object], ...] = (),
) -> IndexRecord:
    return IndexRecord(
        id=f"record-{ordinal}",
        ordinal=ordinal,
        context=RecordContext(
            session="chat-a",
            horizon=TurnRef(address=f"turn-{ordinal}", hash=f"turn-hash-{ordinal}"),
        ),
        operation=Operation(type=operation, parameters=parameters),
        support=SupportSet(
            neighborhoods=(
                EvidenceNeighborhood(
                    session="chat-a",
                    grounding=(
                        MessageRef(
                            address=f"message-{ordinal}",
                            hash=f"message-hash-{ordinal}",
                        ),
                    ),
                ),
            )
        ),
        assertions=assertions,
    )


def _projection():
    return project_records(
        (
            _record(
                1,
                "block.create",
                {
                    "block_id": "block-a",
                    "isoblock_id": "isoblock-a",
                    "name": "POI.Class.Documentation",
                },
            ),
            _record(
                2,
                "line.capture",
                {
                    "line_id": "line-a",
                    "isoline_id": "isoline-a",
                    "block_id": "block-a",
                    "label": "^poi-documentation",
                    "text": "POI documentation must be sufficient.",
                },
                assertions=({"type": "index.line.type", "value": "CT"},),
            ),
            _record(
                3,
                "line.capture",
                {
                    "line_id": "line-b",
                    "isoline_id": "isoline-b",
                    "block_id": "block-a",
                    "label": "^poi-untyped",
                    "text": "An unfinished line remains visible.",
                },
            ),
            _record(
                4,
                "line.capture",
                {
                    "line_id": "line-c",
                    "isoline_id": "isoline-c",
                    "block_id": "block-a",
                    "label": "^poi-conflict",
                    "text": "A conflicting type remains visible.",
                },
                assertions=(
                    {"type": "index.line.type", "value": "DC"},
                    {"type": "index.line.type", "value": "CT"},
                ),
            ),
            _record(
                5,
                "block.create",
                {
                    "block_id": "block-empty",
                    "isoblock_id": "isoblock-empty",
                    "name": "Empty.WIP.Block",
                },
            ),
        )
    )


def test_render_projection_as_kernel_writing() -> None:
    assert render_kernel_writing(_projection()) == (
        "****\n"
        "## POI.Class.Documentation\n\n"
        "- [CT] POI documentation must be sufficient. ^poi-documentation\n"
        "- [--] An unfinished line remains visible. ^poi-untyped\n"
        "- [??] A conflicting type remains visible. ^poi-conflict\n\n"
        "****\n"
        "## Empty.WIP.Block"
    )


def test_render_one_exact_block_by_name_or_id() -> None:
    projection = _projection()
    expected = "****\n## Empty.WIP.Block"

    assert render_kernel_writing(projection, block="Empty.WIP.Block") == expected
    assert render_kernel_writing(projection, block="block-empty") == expected


def test_render_block_selector_fails_closed_when_absent_or_ambiguous() -> None:
    projection = _projection()

    with pytest.raises(RenderError, match="does not resolve"):
        render_kernel_writing(projection, block="Absent.Block")

    records = (
        _record(
            1,
            "block.create",
            {
                "block_id": "block-one",
                "isoblock_id": "isoblock-one",
                "name": "Repeated.Block",
            },
        ),
        _record(
            2,
            "block.create",
            {
                "block_id": "block-two",
                "isoblock_id": "isoblock-two",
                "name": "Repeated.Block",
            },
        ),
    )
    ambiguous = project_records(records)
    with pytest.raises(RenderError, match="resolves to 2"):
        render_kernel_writing(ambiguous, block="Repeated.Block")
