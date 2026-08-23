from __future__ import annotations

from dataclasses import replace

import pytest

from tarav.indexlab import (
    EvidenceNeighborhood,
    IndexRecord,
    MessageRef,
    Operation,
    ProjectionError,
    RecordContext,
    SupportSet,
    TurnRef,
    fold_records,
    project_records,
)


def _support(label: str) -> SupportSet:
    return SupportSet(
        neighborhoods=(
            EvidenceNeighborhood(
                session="chat-a",
                grounding=(MessageRef(address=f"message-{label}", hash=f"hash-{label}"),),
            ),
        )
    )


def _record(
    ordinal: int,
    operation: str,
    parameters: dict[str, object],
    *,
    support: str | None = None,
) -> IndexRecord:
    return IndexRecord(
        id=f"record-{ordinal}",
        ordinal=ordinal,
        context=RecordContext(
            session="chat-a",
            horizon=TurnRef(address=f"turn-{ordinal}", hash=f"turn-hash-{ordinal}"),
        ),
        operation=Operation(type=operation, parameters=parameters),
        support=_support(support or str(ordinal)),
    )


def _base_records() -> tuple[IndexRecord, ...]:
    return (
        _record(
            1,
            "block.create",
            {
                "block_id": "block-a1",
                "isoblock_id": "isoblock-a",
                "name": "Recording.Kernel",
            },
        ),
        _record(
            2,
            "line.capture",
            {
                "line_id": "line-a1",
                "isoline_id": "isoline-a",
                "block_id": "block-a1",
                "label": "^line-a",
                "text": "The index is a sequence of records.",
            },
        ),
    )


def test_capture_projects_lines_inside_their_semantic_block() -> None:
    projection = project_records(_base_records())

    block = projection.block("block-a1")
    line = projection.line("line-a1")

    assert block.name == "Recording.Kernel"
    assert block.line_ids == ("line-a1",)
    assert line.block_id == block.id
    assert projection.line_by_label("^line-a") == line
    assert line.text == "The index is a sequence of records."
    assert projection.isoline_support("isoline-a") == _support("2")


def test_support_add_targets_exact_wording_and_accumulates_on_isoline() -> None:
    records = _base_records() + (
        _record(
            3,
            "support.add",
            {"line_id": "line-a1"},
            support="additional",
        ),
    )

    projection = project_records(records)

    assert projection.line("line-a1").support == SupportSet(
        neighborhoods=(
            *_support("2").neighborhoods,
            *_support("additional").neighborhoods,
        )
    )
    assert projection.isoline_support("isoline-a") == projection.line(
        "line-a1"
    ).support


def test_block_rename_creates_equivalent_edition_and_carries_membership() -> None:
    records = _base_records() + (
        _record(
            3,
            "block.rename",
            {
                "block_id": "block-a1",
                "new_block_id": "block-a2",
                "isoblock_id": "isoblock-a",
                "name": "Index.Recording.Kernel",
            },
        ),
    )

    projection = project_records(records)

    assert tuple(block.id for block in projection.blocks) == ("block-a2",)
    assert projection.block("block-a2").line_ids == ("line-a1",)
    assert projection.line("line-a1").block_id == "block-a2"
    assert projection.block("block-a2").isoblock_id == "isoblock-a"


def test_reblock_creates_equivalent_line_edition_in_destination() -> None:
    records = _base_records() + (
        _record(
            3,
            "block.create",
            {
                "block_id": "block-b1",
                "isoblock_id": "isoblock-b",
                "name": "Semantic.Units",
            },
        ),
        _record(
            4,
            "line.reblock",
            {
                "line_id": "line-a1",
                "isoline_id": "isoline-a",
                "block_id": "block-b1",
            },
        ),
    )

    projection = project_records(records)

    assert projection.block("block-a1").line_ids == ()
    assert projection.block("block-b1").line_ids == ("line-a1",)
    assert projection.line("line-a1").text == "The index is a sequence of records."
    assert projection.line("line-a1").isoline_id == "isoline-a"
    assert projection.isoline_support("isoline-a") == _support("2")


def test_later_context_can_group_existing_lines_under_one_isoline() -> None:
    records = _base_records() + (
        _record(
            3,
            "line.capture",
            {
                "line_id": "line-b1",
                "isoline_id": "isoline-b",
                "block_id": "block-a1",
                "label": "^line-b",
                "text": "Touched.Index is an ordered record surface.",
            },
        ),
        _record(
            4,
            "isoline.group",
            {
                "line_ids": ["line-a1", "line-b1"],
                "isoline_id": "isoline-grouped",
            },
        ),
    )

    projection = project_records(records)

    assert projection.line("line-a1").isoline_id == "isoline-grouped"
    assert projection.line("line-b1").isoline_id == "isoline-grouped"
    assert projection.isoline_support("isoline-grouped") == SupportSet(
        neighborhoods=(
            *_support("2").neighborhoods,
            *_support("3").neighborhoods,
        )
    )


def test_projection_rejects_missing_targets_and_duplicate_exact_ids() -> None:
    missing = _record(1, "support.add", {"line_id": "absent"})
    duplicate = replace(
        _base_records()[1],
        id="record-3",
        ordinal=3,
    )

    with pytest.raises(ProjectionError, match="absent"):
        project_records((missing,))
    with pytest.raises(ProjectionError, match="line-a1 already exists"):
        project_records(_base_records() + (duplicate,))


# The Index is a WIP.Surface, so an incomplete line is recordable: a real line
# may carry no citation yet, and refusing it would let the kernel's shape decide
# what counts as Index data. What it may not do is claim someone else's label.
def test_a_line_may_carry_no_label_but_never_a_duplicate_one() -> None:
    unlabelled = _record(
        2,
        "line.capture",
        {
            "line_id": "line-a1",
            "isoline_id": "isoline-a",
            "block_id": "block-a1",
            "text": "Missing citation.",
        },
    )
    malformed_label = _record(
        2,
        "line.capture",
        {
            "line_id": "line-a2",
            "isoline_id": "isoline-a",
            "block_id": "block-a1",
            "label": "line-a",
            "text": "Label without its sigil.",
        },
    )
    duplicate_label = _record(
        3,
        "line.capture",
        {
            "line_id": "line-b1",
            "isoline_id": "isoline-b",
            "block_id": "block-a1",
            "label": "^line-a",
            "text": "Duplicate citation.",
        },
    )

    projection = project_records((_base_records()[0], unlabelled))
    assert projection.lines[0].label is None
    assert projection.lines[0].text == "Missing citation."

    with pytest.raises(ProjectionError, match="must begin with"):
        project_records((_base_records()[0], malformed_label))
    with pytest.raises(ProjectionError, match=r"label \^line-a already exists"):
        project_records(_base_records() + (duplicate_label,))


def test_semantic_no_op_records_are_rejected() -> None:
    duplicate_support = _record(
        3,
        "support.add",
        {"line_id": "line-a1"},
        support="2",
    )
    same_block = _record(
        3,
        "line.reblock",
        {
            "line_id": "line-a1",
            "isoline_id": "isoline-a",
            "block_id": "block-a1",
        },
    )

    with pytest.raises(ProjectionError, match="contribute new support"):
        project_records(_base_records() + (duplicate_support,))
    with pytest.raises(ProjectionError, match="destination must differ"):
        project_records(_base_records() + (same_block,))


def _bad(record_id: str, ordinal: int, block_id: str) -> IndexRecord:
    return IndexRecord(
        id=record_id,
        ordinal=ordinal,
        context=RecordContext(
            session="chat-a",
            horizon=TurnRef(address="turn-1", hash="hash-turn-1"),
        ),
        operation=Operation(
            type="line.capture",
            parameters={
                "line_id": f"line-{record_id}",
                "isoline_id": f"isoline-{record_id}",
                "block_id": block_id,
                "label": f"^{record_id}",
                "text": "orphan line",
            },
        ),
        support=SupportSet(
            neighborhoods=(
                EvidenceNeighborhood(
                    session="chat-a",
                    grounding=(MessageRef(address="message-1", hash="hash-1"),),
                ),
            )
        ),
    )


def test_fold_collects_every_broken_record_not_only_the_first() -> None:
    records = (_bad("r1", 1, "absent-block"), _bad("r2", 2, "also-absent"))

    projection, errors = fold_records(records)

    assert [error.record_id for error in errors] == ["r1", "r2"]
    assert projection.lines == ()


def test_fold_error_carries_its_record_identity_structurally() -> None:
    _, errors = fold_records((_bad("r1", 1, "absent-block"),))

    assert errors[0].record_id == "r1"
    assert errors[0].to_dict()["record_id"] == "r1"


def test_project_records_still_raises_on_the_first_broken_record() -> None:
    with pytest.raises(ProjectionError) as excinfo:
        project_records((_bad("r1", 1, "absent-block"), _bad("r2", 2, "also-absent")))

    assert excinfo.value.record_id == "r1"


def test_a_rejected_record_leaves_no_partial_mutation_behind() -> None:
    """A record that fails midway must not half-apply into the projection."""

    good = IndexRecord(
        id="r-block",
        ordinal=1,
        context=RecordContext(
            session="chat-a",
            horizon=TurnRef(address="turn-1", hash="hash-turn-1"),
        ),
        operation=Operation(
            type="block.create",
            parameters={"block_id": "b1", "isoblock_id": "iso-b1", "name": "Block"},
        ),
        support=SupportSet(
            neighborhoods=(
                EvidenceNeighborhood(
                    session="chat-a",
                    grounding=(MessageRef(address="message-1", hash="hash-1"),),
                ),
            )
        ),
    )
    # Captures into b1, then fails its own label rule: the block must not keep
    # a dangling line id.
    partial = _bad("r-partial", 2, "b1")
    partial = IndexRecord(
        id=partial.id,
        ordinal=partial.ordinal,
        context=partial.context,
        operation=Operation(
            type="line.capture",
            parameters={**partial.operation.parameters, "label": "missing-caret"},
        ),
        support=partial.support,
    )

    projection, errors = fold_records((good, partial))

    assert [error.record_id for error in errors] == ["r-partial"]
    assert projection.block("b1").line_ids == ()
