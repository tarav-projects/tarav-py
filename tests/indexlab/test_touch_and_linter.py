from __future__ import annotations

from tarav.indexlab import (
    ChatlasTouchSource,
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
) -> IndexRecord:
    return IndexRecord(
        id=record_id,
        ordinal=ordinal,
        context=context,
        operation=Operation(type=operation, parameters=parameters),
        support=support,
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
    )

    report = lint_records((block, line), source=source)

    assert report.verified
    assert report.findings == ()


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
        for finding in report.findings
        if finding.poi_class == "IndexLab.Linter/Context.Unresolved"
    } == {"blocked"}
    assert all("resolution" not in finding.to_dict() for finding in report.findings)


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
    assert {finding.status for finding in report.findings} == {"blocked"}


def test_chatlas_adapter_resolves_public_normal_model(monkeypatch) -> None:
    user_address = "a" * 64
    user_hash = "b" * 64
    agent_address = "c" * 64
    agent_hash = "d" * 64
    user_turn_address = "e" * 64
    user_turn_hash = "f" * 64
    agent_turn_address = "1" * 64
    agent_turn_hash = "2" * 64
    model = {
        "session": {"identity_hash": "chat-a"},
        "annotations": {
            "chat_messages": [
                {
                    "message_address": user_address,
                    "message_hash": user_hash,
                    "side": "user",
                    "text": "Touched.",
                },
                {
                    "message_address": agent_address,
                    "message_hash": agent_hash,
                    "side": "agent",
                    "text": "Captured.",
                },
            ],
            "chat_turns": [
                {
                    "turn_address": user_turn_address,
                    "turn_hash": user_turn_hash,
                    "side": "user",
                    "message_addresses": [user_address],
                },
                {
                    "turn_address": agent_turn_address,
                    "turn_hash": agent_turn_hash,
                    "side": "agent",
                    "message_addresses": [agent_address],
                },
            ],
        },
    }
    calls: list[dict[str, object]] = []

    def fake_compute_normal_model(**kwargs):
        calls.append(kwargs)
        return model

    monkeypatch.setattr(
        "tarav.indexlab.touch.compute_normal_model",
        fake_compute_normal_model,
    )
    source = ChatlasTouchSource()

    context = source.resolve_context(
        RecordContext(
            session="chat-a",
            horizon=TurnRef(address=agent_turn_address, hash=agent_turn_hash),
        )
    )
    message = source.resolve_message(
        "chat-a",
        MessageRef(address=user_address, hash=user_hash),
    )

    assert context.standing == "MATCHED"
    assert context.value is not None
    assert context.value.visible_message_addresses == (user_address, agent_address)
    assert message.standing == "MATCHED"
    assert message.value is not None and message.value.side == "user"
    assert calls == [{"identity_hash": "chat-a", "chatlas_root": None}]


def _chatlas_model(*, turn_shape: str, side: str = "user") -> dict[str, object]:
    """Build one Normal Model fixture in either published turn shape.

    `message_refs` is what finalized Chatlas turns actually carry; the
    `message_addresses` projection only appears in older fixtures. Both are
    exercised so the production branch is not left to the fallback path.
    """

    user_address = "a" * 64
    agent_address = "c" * 64

    def turn(address: str, digest: str, member: str) -> dict[str, object]:
        payload: dict[str, object] = {"turn_address": address, "turn_hash": digest}
        if turn_shape == "message_refs":
            payload["message_refs"] = [{"message_address": member}]
        else:
            payload["message_addresses"] = [member]
        return payload

    return {
        "session": {"identity_hash": "chat-a"},
        "annotations": {
            "chat_messages": [
                {
                    "message_address": user_address,
                    "message_hash": "b" * 64,
                    "side": side,
                    "text": "Touched.",
                },
                {
                    "message_address": agent_address,
                    "message_hash": "d" * 64,
                    "side": "agent",
                    "text": "Captured.",
                },
            ],
            "chat_turns": [
                turn("e" * 64, "f" * 64, user_address),
                turn("1" * 64, "2" * 64, agent_address),
            ],
        },
    }


def _chatlas_source(monkeypatch, model: dict[str, object]) -> ChatlasTouchSource:
    monkeypatch.setattr(
        "tarav.indexlab.touch.compute_normal_model",
        lambda **_: model,
    )
    return ChatlasTouchSource()


def test_chatlas_adapter_reads_finalized_message_refs_turn_shape(monkeypatch) -> None:
    source = _chatlas_source(monkeypatch, _chatlas_model(turn_shape="message_refs"))

    context = source.resolve_context(
        RecordContext(
            session="chat-a",
            horizon=TurnRef(address="1" * 64, hash="2" * 64),
        )
    )
    message = source.resolve_message(
        "chat-a",
        MessageRef(address="a" * 64, hash="b" * 64),
    )

    assert context.standing == "MATCHED"
    assert context.value is not None
    assert context.value.visible_message_addresses == ("a" * 64, "c" * 64)
    assert message.standing == "MATCHED"
    assert message.value is not None
    assert message.value.side == "user"
    assert message.value.turn_ordinal == 1


def test_chatlas_adapter_reports_malformed_material_apart_from_absence(monkeypatch) -> None:
    source = _chatlas_source(
        monkeypatch,
        _chatlas_model(turn_shape="message_refs", side="system"),
    )

    present_but_broken = source.resolve_message(
        "chat-a",
        MessageRef(address="a" * 64, hash="b" * 64),
    )
    genuinely_absent = source.resolve_message(
        "chat-a",
        MessageRef(address="9" * 64, hash="8" * 64),
    )

    assert present_but_broken.standing == "MALFORMED"
    assert present_but_broken.detail is not None
    assert genuinely_absent.standing == "MISSING"
    assert genuinely_absent.detail is None


def test_malformed_support_material_is_not_reported_as_a_dangling_reference(
    monkeypatch,
) -> None:
    source = _chatlas_source(
        monkeypatch,
        _chatlas_model(turn_shape="message_refs", side="system"),
    )
    record = _record(
        "record-malformed",
        1,
        RecordContext(session="chat-a", horizon=TurnRef(address="1" * 64, hash="2" * 64)),
        "block.create",
        {"block_id": "block", "isoblock_id": "isoblock", "name": "Block"},
        SupportSet(
            neighborhoods=(
                EvidenceNeighborhood(
                    session="chat-a",
                    grounding=(MessageRef(address="a" * 64, hash="b" * 64),),
                ),
            )
        ),
    )

    report = lint_records((record,), source=source)
    classes = {finding.poi_class for finding in report.findings}

    assert "IndexLab.Linter/Support.Malformed" in classes
    assert "IndexLab.Linter/Support.Unresolved" not in classes
    assert report.clean is True
    assert report.verified is False


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
