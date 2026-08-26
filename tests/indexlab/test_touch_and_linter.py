from __future__ import annotations

from dataclasses import replace

import pytest

from tarav._core.errors import CliError
from tarav.indexlab import (
    CHECK_REGISTRY,
    EvidenceNeighborhood,
    IndexWorkspace,
    IndexRecord,
    MessageRef,
    Operation,
    RecordContext,
    RecordStore,
    SupportSet,
    TurnRef,
    UserTouchMock,
    lint_records,
    lint_store,
)


def _record(
    record_id: str,
    ordinal: int,
    context: RecordContext,
    operation: str,
    parameters: dict[str, object],
    support: SupportSet,
    assertions: tuple[dict[str, object], ...] = (),
) -> IndexRecord:
    return IndexRecord(
        id=record_id,
        ordinal=ordinal,
        context=context,
        operation=Operation(type=operation, parameters=parameters),
        support=support,
        assertions=assertions,
    )


def test_mock_lints_self_chat_and_external_capture() -> None:
    source = UserTouchMock()
    touched = source.add_turn("chat-a", "user", "The index is a semantic tape.")
    explanation = source.add_turn("chat-a", "agent", "A record projects that touch.")
    producer = source.add_turn("chat-b", "user", "Capture what we found in chat A.")
    writer = source.add_turn("chat-b", "agent", "I will create the line record.")

    block = _record(
        "record-1",
        1,
        source.record_context("chat-a", explanation.turn_ref),
        "block.create",
        {
            "block_id": "block-a",
            "isoblock_id": "isoblock-a",
            "name": "Recording.Kernel",
        },
        SupportSet(
            neighborhoods=(
                EvidenceNeighborhood(
                    session="chat-a",
                    grounding=(touched.ref,),
                    context=(explanation.ref,),
                ),
            )
        ),
    )
    line = _record(
        "record-2",
        2,
        source.record_context("chat-b", writer.turn_ref),
        "line.capture",
        {
            "line_id": "line-a",
            "isoline_id": "isoline-a",
            "block_id": "block-a",
            "label": "^semantic-tape",
            "text": "The index is a semantic tape.",
        },
        SupportSet(
            neighborhoods=(
                EvidenceNeighborhood(
                    session="chat-a",
                    grounding=(touched.ref,),
                    context=(explanation.ref,),
                ),
                EvidenceNeighborhood(
                    session="chat-b",
                    grounding=(producer.ref,),
                    context=(writer.ref,),
                ),
            )
        ),
        ({"line_type": "DF"},),
    )

    report = lint_records((block, line), source=source)

    assert report.verified
    assert report.findings == ()

    targeted = lint_records((block, line), source=source, subjects=("record-2",))
    assert targeted.verified
    assert targeted.execution["records_loaded"] == 2
    assert targeted.execution["records_selected"] == 1


def test_registry_discovers_every_managed_poi_class() -> None:
    assert set().union(*(check.poi_classes() for check in CHECK_REGISTRY)) == {
        "IndexLab.Linter/Context.Amended",
        "IndexLab.Linter/Context.Malformed",
        "IndexLab.Linter/Context.Unresolved",
        "IndexLab.Linter/Line.Unlabelled",
        "IndexLab.Linter/Line.Untyped",
        "IndexLab.Linter/Projection.Invalid",
        "IndexLab.Linter/Tripwire.Hit",
        "IndexLab.Linter/Record.Unloadable",
        "IndexLab.Linter/Support.Amended",
        "IndexLab.Linter/Support.ContextSide",
        "IndexLab.Linter/Support.Empty",
        "IndexLab.Linter/Support.GroundingSide",
        "IndexLab.Linter/Support.Malformed",
        "IndexLab.Linter/Support.NeighborhoodEmpty",
        "IndexLab.Linter/Support.OutsideVisibleContext",
        "IndexLab.Linter/Support.Unresolved",
    }


def test_tripwires_find_every_literal_occurrence_and_keep_stable_subjects() -> None:
    source = UserTouchMock()
    touched = source.add_turn("chat-a", "user", "Exercise the linter.")
    writer = source.add_turn("chat-a", "agent", "I will place a probe.")
    support = SupportSet(
        neighborhoods=(
            EvidenceNeighborhood(
                session="chat-a",
                grounding=(touched.ref,),
                context=(writer.ref,),
            ),
        )
    )
    first = _record(
        "record-1",
        1,
        source.record_context("chat-a", writer.turn_ref),
        "block.create",
        {"block_id": "block-1", "isoblock_id": "iso-1", "name": "banana"},
        support,
    )
    second = _record(
        "record-2",
        2,
        source.record_context("chat-a", writer.turn_ref),
        "block.create",
        {"block_id": "block-2", "isoblock_id": "iso-2", "name": "banana"},
        support,
    )

    report = lint_records(
        (first, second),
        source=source,
        check=("tripwire",),
        tripwires=("ana", "nan"),
    )
    assert len(report.findings) == 6
    assert {finding.subject["field_path"] for finding in report.findings} == {
        "/operation/parameters/name"
    }
    assert {finding.subject["tripwire"] for finding in report.findings} == {
        "ana",
        "nan",
    }
    ana = [
        finding
        for finding in report.findings
        if finding.subject["record_id"] == "record-1"
        and finding.subject["tripwire"] == "ana"
    ]
    assert [finding.subject["occurrence"] for finding in ana] == [1, 2]
    assert [finding.operands["offset"] for finding in ana] == [1, 3]

    moved = replace(
        first,
        operation=Operation(
            type="block.create",
            parameters={
                "block_id": "block-1",
                "isoblock_id": "iso-1",
                "name": "prefix banana",
            },
        ),
    )
    moved_hits = lint_records(
        (moved,), source=source, check=("tripwire",), tripwires=("ana",)
    ).findings
    assert [finding.identity for finding in moved_hits] == [
        finding.identity for finding in ana
    ]

    targeted = lint_records(
        (first, second),
        source=source,
        check=("tripwire",),
        tripwires=("ana",),
        subjects=("record-2",),
    )
    assert {finding.subject["record_id"] for finding in targeted.findings} == {
        "record-2"
    }

    automatic = lint_records((first,), source=source, tripwires=("ana",))
    assert "tripwire" in {result.name for result in automatic.results}

    with pytest.raises(CliError, match="requires at least one"):
        lint_records((first,), source=source, check=("tripwire",))
    with pytest.raises(CliError, match="must not be empty"):
        lint_records((first,), source=source, tripwires=("",))


def test_linter_finds_wrong_sides_and_same_chat_support_after_horizon() -> None:
    source = UserTouchMock()
    user = source.add_turn("chat-a", "user", "First touch.")
    agent = source.add_turn("chat-a", "agent", "First response.")
    future = source.add_turn("chat-a", "user", "Later touch.")
    record = _record(
        "record-1",
        1,
        source.record_context("chat-a", agent.turn_ref),
        "block.create",
        {
            "block_id": "block-a",
            "isoblock_id": "isoblock-a",
            "name": "Bad.Support",
        },
        SupportSet(
            neighborhoods=(
                EvidenceNeighborhood(
                    session="chat-a",
                    grounding=(agent.ref, future.ref),
                    context=(user.ref,),
                ),
            )
        ),
    )

    report = lint_records((record,), source=source)

    assert {finding.poi_class for finding in report.findings} == {
        "IndexLab.Linter/Support.ContextSide",
        "IndexLab.Linter/Support.GroundingSide",
        "IndexLab.Linter/Support.OutsideVisibleContext",
    }
    assert {finding.status for finding in report.findings} == {"failed"}


def test_linter_surfaces_bad_indexing_without_prescribing_repair() -> None:
    source = UserTouchMock()
    writer = source.add_turn("chat-a", "agent", "Unresolvable claim.")
    empty = _record(
        "record-1",
        1,
        source.record_context("chat-a", writer.turn_ref),
        "support.add",
        {"line_id": "absent"},
        SupportSet(neighborhoods=()),
    )
    missing_source = _record(
        "record-2",
        2,
        RecordContext(
            session="unknown-chat",
            horizon=TurnRef(address="unknown-turn", hash="unknown-hash"),
        ),
        "block.create",
        {
            "block_id": "block-a",
            "isoblock_id": "isoblock-a",
            "name": "Unknown.Context",
        },
        SupportSet(
            neighborhoods=(
                EvidenceNeighborhood(
                    session="unknown-chat",
                    grounding=(MessageRef(address="unknown", hash="unknown"),),
                ),
            )
        ),
    )

    report = lint_records((empty, missing_source), source=source)

    assert "IndexLab.Linter/Support.Empty" in {
        finding.poi_class for finding in report.findings
    }
    assert "IndexLab.Linter/Projection.Invalid" in {
        finding.poi_class for finding in report.findings
    }
    assert {
        finding.status
        for finding in report.blocked
        if finding.poi_class == "IndexLab.Linter/Context.Unresolved"
    } == {"blocked"}
    assert all("resolution" not in finding.operands for finding in report.findings)


def test_blocked_run_is_clean_but_not_verified() -> None:
    record = _record(
        "record-1",
        1,
        RecordContext(
            session="unavailable-chat",
            horizon=TurnRef(address="turn", hash="hash"),
        ),
        "block.create",
        {
            "block_id": "block-a",
            "isoblock_id": "isoblock-a",
            "name": "Unavailable.Source",
        },
        SupportSet(
            neighborhoods=(
                EvidenceNeighborhood(
                    session="unavailable-chat",
                    grounding=(MessageRef(address="message", hash="hash"),),
                ),
            )
        ),
    )

    report = lint_records((record,), source=UserTouchMock())

    assert report.clean is True
    assert report.verified is False
    assert report.short_circuited is False
    assert {finding.status for finding in report.blocked} == {"blocked"}



def test_structural_tier_reports_unloadable_cargo_and_stops_the_run(tmp_path) -> None:
    """Corrupt cargo becomes a POI instead of an exception, and short-circuits.

    Linting on past it would examine a silently truncated corpus and report the
    remainder as clean.
    """

    store = RecordStore(
        IndexWorkspace.initialize(
            tmp_path / "lab",
            workspace_id="00000000-0000-4000-8000-000000000001",
        )
    )
    source = UserTouchMock()
    touched = source.add_turn("chat-a", "user", "Touched.")
    writer = source.add_turn("chat-a", "agent", "Captured.")
    store.append(
        _record(
            "record-good",
            0,
            source.record_context("chat-a", writer.turn_ref),
            "block.create",
            {"block_id": "b1", "isoblock_id": "iso-b1", "name": "Block"},
            SupportSet(
                neighborhoods=(
                    EvidenceNeighborhood(
                        session="chat-a",
                        grounding=(touched.ref,),
                        context=(writer.ref,),
                    ),
                )
            ),
        )
    )
    store._depot.insert({"id": "record-broken", "schema": "tarav.indexlab-record.v1"})

    report = lint_store(store, source=source)

    assert report.short_circuited is True
    assert report.verified is False
    assert [finding.poi_class for finding in report.findings] == [
        "IndexLab.Linter/Record.Unloadable"
    ]
    assert report.findings[0].subject["record_id"] == "record-broken"


def test_projection_findings_are_attributed_per_record(tmp_path) -> None:
    source = UserTouchMock()
    touched = source.add_turn("chat-a", "user", "Touched.")
    writer = source.add_turn("chat-a", "agent", "Captured.")
    support = SupportSet(
        neighborhoods=(
            EvidenceNeighborhood(
                session="chat-a",
                grounding=(touched.ref,),
                context=(writer.ref,),
            ),
        )
    )

    def orphan(record_id: str, ordinal: int) -> IndexRecord:
        return _record(
            record_id,
            ordinal,
            source.record_context("chat-a", writer.turn_ref),
            "line.capture",
            {
                "line_id": f"line-{record_id}",
                "isoline_id": f"iso-{record_id}",
                "block_id": "absent-block",
                "label": f"^{record_id}",
                "text": "orphan",
            },
            support,
        )

    report = lint_records((orphan("r1", 1), orphan("r2", 2)), source=source)
    projection = [
        finding
        for finding in report.findings
        if finding.poi_class == "IndexLab.Linter/Projection.Invalid"
    ]

    assert [finding.subject["record_id"] for finding in projection] == ["r1", "r2"]
    assert len({finding.identity for finding in projection}) == 2


# The Index is a WIP.Surface: an incomplete line records, and its incompleteness
# is reported rather than repaired.
def test_line_complete_reports_untyped_and_unlabelled_lines_separately() -> None:
    source = UserTouchMock()
    turn = source.add_turn("chat-a", "user", "Capture the legacy chapter lines.")
    context = source.record_context("chat-a", turn.turn_ref)

    def entry(ordinal, parameters, assertions):
        return IndexRecord(
            id=f"record-{ordinal}",
            ordinal=ordinal,
            context=context,
            operation=Operation(type="line.capture", parameters=parameters),
            support=SupportSet(neighborhoods=()),
            assertions=assertions,
        )

    block = _record(
        "record-1",
        1,
        context,
        "block.create",
        {"block_id": "block-a", "isoblock_id": "isoblock-a", "name": "d/design#Alpha"},
        SupportSet(neighborhoods=()),
    )
    complete = entry(
        2,
        {
            "line_id": "line-a",
            "isoline_id": "isoline-a",
            "block_id": "block-a",
            "label": "^c20260101-1u",
            "text": "a complete line",
        },
        ({"line_type": "DF"},),
    )
    incomplete = entry(
        3,
        {
            "line_id": "line-b",
            "isoline_id": "isoline-b",
            "block_id": "block-a",
            "text": "pre-fence legacy: no type, no label",
        },
        ({"line_type": "UNTYPED"},),
    )

    report = lint_records(
        (block, complete, incomplete), source=source, check=("line-complete",)
    )
    reported = sorted(
        (finding.poi_class, finding.subject["record_id"]) for finding in report.findings
    )
    assert reported == [
        ("IndexLab.Linter/Line.Unlabelled", "record-3"),
        ("IndexLab.Linter/Line.Untyped", "record-3"),
    ]
