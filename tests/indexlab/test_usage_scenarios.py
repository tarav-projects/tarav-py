from __future__ import annotations

from dataclasses import replace

from tarav.indexlab import (
    EvidenceNeighborhood,
    IndexLabWorkspace,
    IndexRecord,
    Operation,
    RecordContext,
    RecordStore,
    SupportSet,
    UserTouchMock,
    lint_records,
    project_records,
)


def _support(session: str, user, agent=None) -> SupportSet:
    return SupportSet(
        neighborhoods=(
            EvidenceNeighborhood(
                session=session,
                grounding=(user.ref,),
                context=() if agent is None else (agent.ref,),
            ),
        )
    )


def _record(
    record_id: str,
    context: RecordContext,
    operation: str,
    parameters: dict[str, object],
    support: SupportSet,
) -> IndexRecord:
    return IndexRecord(
        id=record_id,
        ordinal=0,
        context=context,
        operation=Operation(type=operation, parameters=parameters),
        support=support,
    )


def _append_base(
    store: RecordStore,
    source: UserTouchMock,
) -> tuple[IndexRecord, IndexRecord, SupportSet]:
    touched = source.add_turn("chat-a", "user", "The Index is a semantic tape.")
    writer = source.add_turn("chat-a", "agent", "I can capture that as one line.")
    support = _support("chat-a", touched, writer)
    context = source.record_context("chat-a", writer.turn_ref)
    block, line = store.append_many(
        (
            _record(
                "record-block-a",
                context,
                "block.create",
                {
                    "block_id": "block-a1",
                    "isoblock_id": "isoblock-a",
                    "name": "Recording.Kernel",
                },
                support,
            ),
            _record(
                "record-line-a",
                context,
                "line.capture",
                {
                    "line_id": "line-a1",
                    "isoline_id": "isoline-a",
                    "block_id": "block-a1",
                    "label": "^semantic-tape",
                    "text": "The Index is a semantic tape.",
                },
                support,
            ),
        )
    )
    return block, line, support


def test_self_chat_capture_is_context_bounded_and_verified(tmp_path) -> None:
    source = UserTouchMock()
    store = RecordStore(IndexLabWorkspace.initialize(tmp_path / "self-chat"))
    block, line, _ = _append_base(store, source)

    report = lint_records(store.list(), source=source)
    projection = project_records(store.list())

    assert report.verified
    assert block.context.session == line.context.session == "chat-a"
    assert line.support.neighborhoods[0].session == line.context.session
    assert projection.block("block-a1").line_ids == ("line-a1",)


def test_external_chat_capture_separates_producer_context_from_touch(tmp_path) -> None:
    source = UserTouchMock()
    touched = source.add_turn("chat-a", "user", "Records annotate chat contexts.")
    explanation = source.add_turn("chat-a", "agent", "That separates placement and support.")
    instruction = source.add_turn("chat-b", "user", "Capture the result from Chat A.")
    writer = source.add_turn("chat-b", "agent", "I loaded Chat A and captured it.")
    context = RecordContext(
        session="chat-b",
        horizon=writer.turn_ref,
        agent_sources=(
            {
                "type": "chat.read",
                "session": "chat-a",
                "horizon": explanation.turn_ref.to_dict(),
            },
        ),
    )
    store = RecordStore(IndexLabWorkspace.initialize(tmp_path / "external-chat"))
    store.append_many(
        (
            _record(
                "record-block",
                source.record_context("chat-b", writer.turn_ref),
                "block.create",
                {
                    "block_id": "block-a",
                    "isoblock_id": "isoblock-a",
                    "name": "Record.Context",
                },
                _support("chat-b", instruction, writer),
            ),
            _record(
                "record-line",
                context,
                "line.capture",
                {
                    "line_id": "line-a",
                    "isoline_id": "isoline-a",
                    "block_id": "block-a",
                    "label": "^context-support-split",
                    "text": "Records annotate chat contexts.",
                },
                _support("chat-a", touched, explanation),
            ),
        )
    )

    report = lint_records(store.list(), source=source)
    line_record = store.get("record-line")

    assert report.verified
    assert line_record is not None
    assert line_record.context.session == "chat-b"
    assert line_record.support.neighborhoods[0].session == "chat-a"
    assert line_record.context.agent_sources[0]["session"] == "chat-a"

    # Current machinery preserves but does not yet validate Agent.Context imports.
    missing_import = replace(line_record, context=replace(line_record.context, agent_sources=()))
    assert lint_records((store.list()[0], missing_import), source=source).verified


def test_support_add_grows_exact_line_without_new_wording_edition(tmp_path) -> None:
    source = UserTouchMock()
    store = RecordStore(IndexLabWorkspace.initialize(tmp_path / "support-add"))
    _, captured, original_support = _append_base(store, source)
    confirmation = source.add_turn("chat-b", "user", "Yes, that semantic tape model still fits.")
    response = source.add_turn("chat-b", "agent", "I will add this support to the exact line.")
    added_support = _support("chat-b", confirmation, response)
    store.append(
        _record(
            "record-support-add",
            source.record_context("chat-b", response.turn_ref),
            "support.add",
            {"line_id": "line-a1"},
            added_support,
        )
    )

    projection = project_records(store.list())
    line = projection.line("line-a1")

    assert lint_records(store.list(), source=source).verified
    assert len(projection.lines) == 1
    assert line.id == captured.operation.parameters["line_id"]
    assert line.text == captured.operation.parameters["text"]
    assert line.support.neighborhoods == (
        *original_support.neighborhoods,
        *added_support.neighborhoods,
    )
    assert projection.isoline_support("isoline-a") == line.support


def test_block_evolution_carries_content_only_through_same_isoblock(tmp_path) -> None:
    source = UserTouchMock()
    store = RecordStore(IndexLabWorkspace.initialize(tmp_path / "block-evolution"))
    _, _, line_support = _append_base(store, source)
    rename_touch = source.add_turn("chat-b", "user", "Rename it Index.Recording.Kernel.")
    rename_writer = source.add_turn("chat-b", "agent", "The semantic frame is unchanged.")
    rename_support = _support("chat-b", rename_touch, rename_writer)
    store.append(
        _record(
            "record-block-rename",
            source.record_context("chat-b", rename_writer.turn_ref),
            "block.rename",
            {
                "block_id": "block-a1",
                "new_block_id": "block-a2",
                "isoblock_id": "isoblock-a",
                "name": "Index.Recording.Kernel",
            },
            rename_support,
        )
    )

    projection = project_records(store.list())

    assert lint_records(store.list(), source=source).verified
    assert projection.block("block-a1").active is False
    assert projection.block("block-a2").line_ids == ("line-a1",)
    assert projection.line("line-a1").block_id == "block-a2"
    assert projection.block("block-a2").isoblock_id == "isoblock-a"
    assert projection.block_support("block-a2") == line_support
    assert rename_support.neighborhoods[0] not in line_support.neighborhoods


def test_line_reblock_preserves_exact_line_and_operation_support_boundary(tmp_path) -> None:
    source = UserTouchMock()
    store = RecordStore(IndexLabWorkspace.initialize(tmp_path / "line-reblock"))
    _, captured, line_support = _append_base(store, source)
    destination_touch = source.add_turn("chat-b", "user", "Create a Semantic.Units block.")
    destination_writer = source.add_turn("chat-b", "agent", "The destination now exists.")
    destination_support = _support("chat-b", destination_touch, destination_writer)
    store.append(
        _record(
            "record-block-b",
            source.record_context("chat-b", destination_writer.turn_ref),
            "block.create",
            {
                "block_id": "block-b1",
                "isoblock_id": "isoblock-b",
                "name": "Semantic.Units",
            },
            destination_support,
        )
    )
    move_touch = source.add_turn("chat-c", "user", "That exact line belongs in Semantic.Units.")
    move_writer = source.add_turn("chat-c", "agent", "I will reblock the existing line.")
    move_support = _support("chat-c", move_touch, move_writer)
    store.append(
        _record(
            "record-reblock",
            source.record_context("chat-c", move_writer.turn_ref),
            "line.reblock",
            {
                "line_id": "line-a1",
                "isoline_id": "isoline-a",
                "block_id": "block-b1",
            },
            move_support,
        )
    )

    projection = project_records(store.list())

    assert lint_records(store.list(), source=source).verified
    assert store.get(captured.id) == captured
    assert projection.block("block-a1").line_ids == ()
    assert projection.block("block-b1").line_ids == ("line-a1",)
    assert projection.line("line-a1").isoline_id == "isoline-a"
    assert projection.line("line-a1").support == line_support
    assert move_support.neighborhoods[0] not in line_support.neighborhoods


def test_later_grouping_preserves_capture_records_and_unions_line_support(tmp_path) -> None:
    source = UserTouchMock()
    store = RecordStore(IndexLabWorkspace.initialize(tmp_path / "isoline-group"))
    _, first, first_support = _append_base(store, source)
    second_touch = source.add_turn("chat-b", "user", "Touched.Index is an ordered record surface.")
    second_writer = source.add_turn("chat-b", "agent", "I will capture that exact wording.")
    second_support = _support("chat-b", second_touch, second_writer)
    second = store.append(
        _record(
            "record-line-b",
            source.record_context("chat-b", second_writer.turn_ref),
            "line.capture",
            {
                "line_id": "line-b1",
                "isoline_id": "isoline-b",
                "block_id": "block-a1",
                "label": "^ordered-record-surface",
                "text": "Touched.Index is an ordered record surface.",
            },
            second_support,
        )
    )
    grouping_touch = source.add_turn("chat-c", "user", "Those two lines mean the same thing.")
    grouping_writer = source.add_turn("chat-c", "agent", "I will group the exact lines.")
    grouping_support = _support("chat-c", grouping_touch, grouping_writer)
    store.append(
        _record(
            "record-isoline-group",
            source.record_context("chat-c", grouping_writer.turn_ref),
            "isoline.group",
            {
                "line_ids": ["line-a1", "line-b1"],
                "isoline_id": "isoline-grouped",
            },
            grouping_support,
        )
    )

    projection = project_records(store.list())

    assert lint_records(store.list(), source=source).verified
    assert store.get(first.id) == first
    assert store.get(second.id) == second
    assert projection.line("line-a1").isoline_id == "isoline-grouped"
    assert projection.line("line-b1").isoline_id == "isoline-grouped"
    assert projection.isoline_support("isoline-grouped").neighborhoods == (
        *first_support.neighborhoods,
        *second_support.neighborhoods,
    )
    assert grouping_support.neighborhoods[0] not in (
        *first_support.neighborhoods,
        *second_support.neighborhoods,
    )


def test_bad_indexing_correction_and_semantic_evolution_remain_distinct(tmp_path) -> None:
    source = UserTouchMock()
    store = RecordStore(IndexLabWorkspace.initialize(tmp_path / "bad-indexing"))
    _, captured, valid_support = _append_base(store, source)
    future_touch = source.add_turn("chat-a", "user", "This happened after capture.")
    bad = replace(captured, support=_support("chat-a", future_touch))
    store.replace(bad)

    bad_report = lint_records(store.list(), source=source)
    assert {
        finding.poi_class for finding in bad_report.findings
    } == {"IndexLab.Linter/Support.OutsideVisibleContext"}

    repaired = replace(bad, support=valid_support)
    store.replace(repaired)
    assert lint_records(store.list(), source=source).verified
    assert store.get(captured.id) == repaired

    destination_touch = source.add_turn("chat-b", "user", "Create the destination block.")
    destination_writer = source.add_turn("chat-b", "agent", "Destination created.")
    destination_support = _support("chat-b", destination_touch, destination_writer)
    store.append(
        _record(
            "record-block-b",
            source.record_context("chat-b", destination_writer.turn_ref),
            "block.create",
            {
                "block_id": "block-b1",
                "isoblock_id": "isoblock-b",
                "name": "Semantic.Units",
            },
            destination_support,
        )
    )
    move_touch = source.add_turn("chat-c", "user", "The old placement was valid; move it now.")
    move_writer = source.add_turn("chat-c", "agent", "This is semantic evolution.")
    store.append(
        _record(
            "record-reblock",
            source.record_context("chat-c", move_writer.turn_ref),
            "line.reblock",
            {
                "line_id": "line-a1",
                "isoline_id": "isoline-a",
                "block_id": "block-b1",
            },
            _support("chat-c", move_touch, move_writer),
        )
    )

    projection = project_records(store.list())

    assert lint_records(store.list(), source=source).verified
    assert store.get("record-line-a") == repaired
    assert store.get("record-reblock") is not None
    assert projection.line("line-a1").block_id == "block-b1"
