# $kw: ^test-anchory-event-addressing --from Chatlas.Session.Model.Tests --from Session.Event.Tape --note [CT] anchory boundary tests use stable turn identity and sequence-based event neighborhoods ^c20260728-16u
from __future__ import annotations

from pathlib import Path

import pytest

import tarav.chatlas.anchory as anchory_module
from tarav.chatlas import chatlas_anchory_depot
from tarav.chatlas.normal_turn import normal_turn_ref
from tarav.chatlas.normalization.session_model.events import compute_event_hash


def test_chatlas_anchory_depot_uses_explicit_chatlas_root(tmp_path: Path) -> None:
    assert chatlas_anchory_depot(tmp_path).root == (tmp_path / "anchory").resolve()


def test_chatlas_anchory_depot_uses_default_chatlas_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    default_root = tmp_path / "default-chatlas"
    monkeypatch.setattr(anchory_module, "default_chatlas_root", lambda: default_root)

    assert chatlas_anchory_depot().root == (default_root / "anchory").resolve()


def test_ensure_chatlas_namespace_writes_meta_once(tmp_path: Path) -> None:
    from tarav.chatlas.anchory import CHATLAS_NAMESPACE, ensure_chatlas_namespace

    depot = chatlas_anchory_depot(tmp_path)
    ensure_chatlas_namespace(depot)
    meta = depot.namespace_meta(CHATLAS_NAMESPACE)
    assert meta is not None
    assert meta["prefix"] == "c"
    ensure_chatlas_namespace(depot)
    assert depot.namespace_meta(CHATLAS_NAMESPACE) == meta


def _support_record(member_count: int) -> dict[str, object]:
    return {
        "app": "chatlas",
        "schema": "chatlas.support-set.v3",
        "hint": f"fixture with {member_count} support members",
        "members": [
            {
                "session": f"{index + 1:064x}",
                "turn_id": f"turn-{index + 1}",
                "turn_hash": f"{index + 1:064x}",
                "at": f"2026-07-18T08:51:{index:02d}.000Z",
            }
            for index in range(member_count)
        ],
    }


def test_chatlas_anchory_stats_summarizes_support_member_cardinality(
    tmp_path: Path,
) -> None:
    from tarav.chatlas.anchory import (
        CHATLAS_NAMESPACE,
        build_line_anchor_dossier,
        build_line_relationships,
        chatlas_anchory_stats,
    )

    depot = chatlas_anchory_depot(tmp_path)
    for index, member_count in enumerate((1, 2, 5)):
        depot.register(
            _support_record(member_count),
            anchor=f"c20260718-{index}u",
            namespace=CHATLAS_NAMESPACE,
        )
    dossier_anchor = "c20260718-3u"
    depot.register(
        build_line_anchor_dossier(
            anchor=dossier_anchor,
            line_content="- [CT] dossier-backed line",
            relationships=build_line_relationships(_support_record(2)["members"]),
        ),
        anchor=dossier_anchor,
        namespace=CHATLAS_NAMESPACE,
    )

    payload = chatlas_anchory_stats(chatlas_root=tmp_path)

    assert payload == {
        "anchor_count": 4,
        "support_turn_count": 10,
        "min": 1,
        "max": 5,
        "mean": pytest.approx(2.5),
        "population_stddev": pytest.approx(1.5),
        "distribution": {"1": 1, "2": 2, "5": 1},
    }


def test_chatlas_anchory_stats_has_explicit_empty_values(tmp_path: Path) -> None:
    from tarav.chatlas.anchory import chatlas_anchory_stats

    assert chatlas_anchory_stats(chatlas_root=tmp_path) == {
        "anchor_count": 0,
        "support_turn_count": 0,
        "min": None,
        "max": None,
        "mean": None,
        "population_stddev": None,
        "distribution": {},
    }


def test_chatlas_anchory_stats_does_not_resolve_member_metadata(tmp_path: Path) -> None:
    from tarav.chatlas.anchory import CHATLAS_NAMESPACE, chatlas_anchory_stats

    chatlas_anchory_depot(tmp_path).register(
        {
            "app": "chatlas",
            "schema": "chatlas.support-set.v3",
            "hint": "historical member with incomplete metadata",
            "members": [{"session": "a" * 64, "turn_id": "turn-1"}],
        },
        anchor="c20260718-0u",
        namespace=CHATLAS_NAMESPACE,
    )

    assert chatlas_anchory_stats(chatlas_root=tmp_path)["support_turn_count"] == 1


def test_chatlas_anchory_sessions_reports_invalid_records_and_unindexed_members(
    tmp_path: Path,
) -> None:
    from tarav.chatlas.anchory import (
        CHATLAS_NAMESPACE,
        chatlas_anchory_sessions,
    )

    depot = chatlas_anchory_depot(tmp_path)
    depot.register(
        _support_record(1),
        anchor="c20260718-0u",
        namespace=CHATLAS_NAMESPACE,
    )
    depot.register(
        {
            "app": "chatlas",
            "schema": "chatlas.support-set.v3",
            "hint": "",
            "members": _support_record(1)["members"],
        },
        anchor="c20260718-1u",
        namespace=CHATLAS_NAMESPACE,
    )
    source = tmp_path / "source.md"
    source.write_text(
        "valid ^c20260718-0u\ninvalid ^c20260718-1u\n",
        encoding="utf-8",
    )

    payload = chatlas_anchory_sessions(
        sources=(source,),
        regex=r"\^(?P<anchor>c\d{8}-\d+[a-z]?)",
        chatlas_root=tmp_path,
    )

    assert payload["status"] == "needs-review"
    assert payload["resolved_anchor_count"] == 1
    assert payload["findings"][0]["kind"] == "invalid_support_record"
    assert payload["sessions"][0]["identity_hash"] == f"{1:064x}"
    assert payload["sessions"][0]["indexed"] is False


def _event(
    sequence: int,
    *,
    role: str,
    timestamp: str,
    transcript: str = "visible",
) -> dict[str, object]:
    event = {
        "annotations": {"normal_turn": {"id": f"turn-{sequence}", "kind": role}},
        "event_address": f"{sequence:064x}",
        "sequence": sequence,
        "kind": "message",
        "timestamp": timestamp,
        "producer": {"type": "human" if role == "user" else "assistant"},
        "surfaces": {"transcript": transcript},
        "payload": {
            "role": role,
            "content": [{"type": "text", "text": f"event-{sequence}"}],
        },
    }
    event["event_hash"] = compute_event_hash(event)
    return event


def _tool_event(sequence: int, *, timestamp: str) -> dict[str, object]:
    event = {
        "annotations": {"normal_turn": {"id": f"turn-{sequence}", "kind": "assistant"}},
        "event_address": f"{sequence:064x}",
        "sequence": sequence,
        "kind": "tool.call",
        "timestamp": timestamp,
        "producer": {"type": "assistant"},
        "surfaces": {"transcript": "hidden"},
        "payload": {"tool_name": "apply_patch", "input": {"patch": "edit"}},
    }
    event["event_hash"] = compute_event_hash(event)
    return event


def _session_model(*events: dict[str, object]) -> dict[str, object]:
    return {
        "chat": {
            "events": list(events),
            "model_runs": [],
            "tool_invocations": [],
            "usage": [],
        }
    }


def _member(identity: str, event: dict[str, object]) -> dict[str, str]:
    return normal_turn_ref(identity, [event])


def test_parse_support_set_record_requires_supported_shape() -> None:
    from tarav._core.errors import CliError
    from tarav.chatlas.anchory import parse_support_set_record

    valid = {
        "app": "chatlas",
        "schema": "chatlas.support-set.v3",
        "hint": "approved design",
        "members": [
            {
                "session": "a" * 64,
                "turn_id": "turn-2",
                "turn_hash": "b" * 64,
                "at": "2026-07-18T08:51:04.561Z",
            }
        ],
    }
    assert parse_support_set_record(valid) == valid["members"]

    with pytest.raises(CliError, match="unsupported schema"):
        parse_support_set_record(
            {"app": "chatlas", "session": "a" * 64, "at": "2026-07-18T08:51:04.561Z"}
        )
    with pytest.raises(CliError, match="non-empty"):
        parse_support_set_record({**valid, "members": []})
    with pytest.raises(CliError, match="duplicate"):
        parse_support_set_record({**valid, "members": valid["members"] * 2})
    with pytest.raises(CliError, match="unknown fields"):
        parse_support_set_record({**valid, "extra": True})


def test_line_anchor_dossier_binds_triplet_and_predecessors() -> None:
    from tarav.index_model import index_line_anchor_triplet_hash
    from tarav.chatlas.anchory import (
        CHATLAS_LINE_ANCHOR_DOSSIER_SCHEMA,
        bind_support_set_to_index_line,
        parse_line_attachment,
        parse_line_predecessors,
        parse_support_set_record,
    )

    base = _support_record(1)
    bound = bind_support_set_to_index_line(
        base,
        line_content="- [CT] stable content ^c20260802-1u",
        anchor="c20260802-3u",
        predecessors=("c20260802-1u", "c20260802-2u"),
    )

    assert bound["schema"] == CHATLAS_LINE_ANCHOR_DOSSIER_SCHEMA
    assert parse_line_predecessors(bound) == ("c20260802-1u", "c20260802-2u")
    assert parse_line_attachment(bound) == {
        "canonical_schema": "agentos.index-line-anchor-triplet.v1",
        "triplet_hash": index_line_anchor_triplet_hash(
            "- [CT] stable content", "c20260802-3u"
        ),
    }
    assert parse_support_set_record(bound) == base["members"]


def test_line_anchor_dossier_rejects_invalid_attachment_and_predecessors() -> None:
    from tarav._core.errors import CliError
    from tarav.chatlas.anchory import (
        bind_support_set_to_index_line,
        parse_support_set_record,
    )

    bound = bind_support_set_to_index_line(
        _support_record(1),
        line_content="- [CT] stable content",
        anchor="c20260802-3u",
        predecessors=("c20260802-1u",),
    )
    with pytest.raises(CliError, match="triplet_hash"):
        changed = {**bound, "attachment": {**bound["attachment"], "triplet_hash": "bad"}}
        parse_support_set_record(changed)
    with pytest.raises(CliError, match="duplicate"):
        changed = {
            **bound,
            "relationships": {
                **bound["relationships"],
                "provenance": {
                    **bound["relationships"]["provenance"],
                    "predecessor_anchors": ["c20260802-1u", "c20260802-1u"],
                },
            },
        }
        parse_support_set_record(
            changed
        )


def test_line_content_authoring_supports_an_untyped_index_line() -> None:
    from tarav.index_model import index_line_anchor_triplet_hash
    from tarav.chatlas.anchory import build_line_anchor_dossier, build_line_relationships

    line_content = "- untyped line"
    anchor = "c20260802-3u"
    dossier = build_line_anchor_dossier(
        anchor=anchor,
        line_content=line_content,
        relationships=build_line_relationships(_support_record(1)["members"]),
    )

    assert dossier["attachment"]["triplet_hash"] == index_line_anchor_triplet_hash(
        line_content,
        anchor,
    )


def test_parse_support_set_record_accepts_member_turn_types() -> None:
    from tarav._core.errors import CliError
    from tarav.chatlas.anchory import parse_support_set_record

    base_member = {
        "session": "a" * 64,
        "turn_id": "turn-2",
        "turn_hash": "a" * 64,
        "at": "2026-07-18T08:51:04.561Z",
    }
    record = {
        "app": "chatlas",
        "schema": "chatlas.support-set.v3",
        "hint": "approved design",
        "members": [
            base_member,  # base support turn: no types
            {
                "session": "b" * 64,
                "turn_id": "turn-9",
                "turn_hash": "b" * 64,
                "at": "2026-07-18T09:00:00.000Z",
                "types": {
                    "tokenized.approval.turn": {
                        "token": "AXT-amber-otter-42",
                        "verbatim_turn": ("b" * 64) + ":turn-7",
                        "approval_turn": ("b" * 64) + ":turn-9",
                    }
                },
            },
        ],
    }

    members = parse_support_set_record(record)
    assert "types" not in members[0]
    assert (
        members[1]["types"]["tokenized.approval.turn"]["token"] == "AXT-amber-otter-42"
    )

    # An empty types map is rejected — absence, not `{}`, means base support.
    with pytest.raises(CliError, match="non-empty object"):
        parse_support_set_record({**record, "members": [{**base_member, "types": {}}]})


def test_resolve_support_set_record_uses_exact_visible_user_event() -> None:
    from tarav._core.errors import CliError
    from tarav.chatlas.anchory import resolve_support_set_record

    identity = "a" * 64
    model = _session_model(
        _event(1, role="assistant", timestamp="2026-07-18T08:51:04.561Z"),
        _event(2, role="user", timestamp="2026-07-18T08:51:04.561Z"),
    )
    user_member = _member(identity, model["chat"]["events"][1])
    record = {
        "app": "chatlas",
        "schema": "chatlas.support-set.v3",
        "hint": "approved design",
        "members": [user_member],
    }
    resolved = resolve_support_set_record(record, model_loader=lambda _session: model)
    assert resolved[0].event["sequence"] == 2

    with pytest.raises(CliError, match="timestamp mismatch"):
        resolve_support_set_record(
            {
                **record,
                "members": [{**record["members"][0], "at": "2026-07-18T09:00:00Z"}],
            },
            model_loader=lambda _session: model,
        )
    with pytest.raises(CliError, match="visible user turn"):
        resolve_support_set_record(
            {
                **record,
                "members": [_member(identity, model["chat"]["events"][0])],
            },
            model_loader=lambda _session: model,
        )
    # an ordinal-keyed v1 member is not a v2 member
    with pytest.raises(CliError, match="unknown fields: event_id"):
        resolve_support_set_record(
            {
                **record,
                "members": [
                    {
                        "session": "a" * 64,
                        "event_id": "event-2",
                        "at": "2026-07-18T08:51:04.561Z",
                    }
                ],
            },
            model_loader=lambda _session: model,
        )


def test_validate_support_set_amendment_repairs_metadata_without_changing_meaning() -> (
    None
):
    from tarav.chatlas.anchory import validate_support_set_amendment

    identity = "a" * 64
    model = _session_model(
        _event(1, role="user", timestamp="2026-07-18T08:51:01.000Z"),
        _event(2, role="user", timestamp="2026-07-18T08:51:02.000Z"),
    )
    member = _member(identity, model["chat"]["events"][0])
    current = {
        "app": "chatlas",
        "schema": "chatlas.support-set.v3",
        "hint": "old hint",
        "members": [member],
    }
    proposed = {
        **current,
        "hint": "corrected hint",
        "members": [member],
    }

    validate_support_set_amendment(
        current,
        proposed,
        model_loader=lambda _identity: model,
    )


def test_validate_dossier_amendment_allows_maintainer_owned_relationship_change() -> None:
    from tarav._core.errors import CliError
    from tarav.chatlas.anchory import (
        bind_support_set_to_index_line,
        validate_support_set_amendment,
    )

    identity = "a" * 64
    model = _session_model(
        _event(1, role="user", timestamp="2026-07-18T08:51:01.000Z"),
    )
    current = bind_support_set_to_index_line(
        {
            "app": "chatlas",
            "schema": "chatlas.support-set.v3",
            "hint": "old hint",
            "members": [_member(identity, model["chat"]["events"][0])],
        },
        line_content="- [CT] stable content",
        anchor="c20260802-3u",
        predecessors=("c20260802-1u",),
    )
    proposed = {
        **current,
        "relationships": {
            **current["relationships"],
            "provenance": {
                **current["relationships"]["provenance"],
                "predecessor_anchors": ["c20260802-2u"],
            },
        },
    }
    validate_support_set_amendment(
        current,
        proposed,
        model_loader=lambda _identity: model,
    )

    with pytest.raises(CliError, match="relationship identity"):
        validate_support_set_amendment(
            current,
            {**current, "schema": "chatlas.support-set.v3"},
            model_loader=lambda _identity: model,
        )


@pytest.mark.parametrize(
    ("members", "error"),
    [
        (
            [
                {
                    "session": "a" * 64,
                    "turn_id": "turn-1",
                }
            ],
            "requires non-empty 'turn_hash'",
        ),
        (
            [
                {
                    "session": "a" * 64,
                    "turn_id": "turn-1",
                    "turn_hash": "0" * 64,
                    "at": "2026-07-18T09:00:00.000Z",
                }
            ],
            "timestamp mismatch",
        ),
    ],
)
def test_validate_support_set_amendment_rejects_unresolvable_replacement(
    members: list[dict[str, object]],
    error: str,
) -> None:
    from tarav._core.errors import CliError
    from tarav.chatlas.anchory import validate_support_set_amendment

    identity = "a" * 64
    model = _session_model(
        _event(1, role="user", timestamp="2026-07-18T08:51:01.000Z"),
    )
    current_member = _member(identity, model["chat"]["events"][0])
    if error == "timestamp mismatch":
        members[0]["turn_hash"] = current_member["turn_hash"]
    current = {
        "app": "chatlas",
        "schema": "chatlas.support-set.v3",
        "hint": "old hint",
        "members": [current_member],
    }
    proposed = {**current, "hint": "new hint", "members": members}

    with pytest.raises(CliError, match=error):
        validate_support_set_amendment(
            current,
            proposed,
            model_loader=lambda _identity: model,
        )


@pytest.mark.parametrize(
    "members",
    [
        [
            {
                "session": "a" * 64,
                "turn_id": "turn-2",
                "at": "2026-07-18T08:51:02.000Z",
            },
            {
                "session": "a" * 64,
                "turn_id": "turn-1",
                "at": "2026-07-18T08:51:01.000Z",
            },
        ],
        [
            {
                "session": "a" * 64,
                "turn_id": "turn-1",
                "at": "2026-07-18T08:51:01.000Z",
                "types": {"approval.turn": {"token": "changed"}},
            },
            {
                "session": "a" * 64,
                "turn_id": "turn-2",
                "at": "2026-07-18T08:51:02.000Z",
            },
        ],
        [
            {
                "session": "a" * 64,
                "turn_id": "turn-3",
                "at": "2026-07-18T08:51:03.000Z",
            },
            {
                "session": "a" * 64,
                "turn_id": "turn-2",
                "at": "2026-07-18T08:51:02.000Z",
            },
        ],
    ],
)
def test_validate_support_set_amendment_rejects_changed_support_meaning(
    members: list[dict[str, object]],
) -> None:
    from tarav._core.errors import CliError
    from tarav.chatlas.anchory import validate_support_set_amendment

    identity = "a" * 64
    model = _session_model(
        _event(1, role="user", timestamp="2026-07-18T08:51:01.000Z"),
        _event(2, role="user", timestamp="2026-07-18T08:51:02.000Z"),
        _event(3, role="user", timestamp="2026-07-18T08:51:03.000Z"),
    )
    current = {
        "app": "chatlas",
        "schema": "chatlas.support-set.v3",
        "hint": "old hint",
        "members": [
            _member(identity, model["chat"]["events"][0]),
            _member(identity, model["chat"]["events"][1]),
        ],
    }

    events_by_turn = {
        f"turn-{index}": event
        for index, event in enumerate(model["chat"]["events"], start=1)
    }
    for item in members:
        turn_id = item.get("turn_id")
        if isinstance(turn_id, str) and turn_id in events_by_turn:
            item.setdefault(
                "turn_hash",
                _member(identity, events_by_turn[turn_id])["turn_hash"],
            )

    with pytest.raises(CliError, match="cannot change support-set meaning"):
        validate_support_set_amendment(
            current,
            {**current, "members": members},
            model_loader=lambda _identity: model,
        )


def test_chatlas_anchory_amend_validator_ignores_other_applications(
    tmp_path: Path,
) -> None:
    from tarav.chatlas.anchory import validate_chatlas_anchory_amendment

    validate_chatlas_anchory_amendment(
        tmp_path / "anchory",
        {"app": "other", "value": 1},
        {"broken": True},
    )


def test_support_runtime_cache_indexes_each_session_tape_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import tarav.chatlas.anchory as anchory
    from tarav.chatlas.anchory import (
        ChatlasSupportRuntimeCache,
        resolve_support_set_record,
    )

    identity = "a" * 64
    model = _session_model(
        _event(1, role="user", timestamp="2026-07-18T08:51:01.000Z"),
        _event(2, role="user", timestamp="2026-07-18T08:51:02.000Z"),
    )
    builds = 0
    original_build = anchory._turn_index

    def counted_build(session_model):
        nonlocal builds
        builds += 1
        return original_build(session_model)

    monkeypatch.setattr(anchory, "_turn_index", counted_build)
    cache = ChatlasSupportRuntimeCache(capacity=4)
    for sequence in (1, 2):
        resolve_support_set_record(
            {
                "app": "chatlas",
                "schema": "chatlas.support-set.v3",
                "hint": f"turn {sequence}",
                "members": [_member(identity, model["chat"]["events"][sequence - 1])],
            },
            model_loader=lambda _session: model,
            runtime_cache=cache,
        )

    assert builds == 1
    assert cache.session_count == 1


def test_resolve_event_support_set_record_accepts_exact_tool_event() -> None:
    from tarav._core.errors import CliError
    from tarav.chatlas.anchory import resolve_event_support_set_record

    identity = "a" * 64
    timestamp = "2026-07-18T08:51:04.561Z"
    model = _session_model(_tool_event(3, timestamp=timestamp))
    record = {
        "app": "chatlas",
        "schema": "chatlas.support-set.v3",
        "hint": "the session edited the file",
        "members": [_member(identity, model["chat"]["events"][0])],
    }

    resolved = resolve_event_support_set_record(
        record,
        model_loader=lambda _session: model,
    )

    assert resolved[0].event["kind"] == "tool.call"
    with pytest.raises(CliError, match="timestamp mismatch"):
        resolve_event_support_set_record(
            {
                **record,
                "members": [{**record["members"][0], "at": "2026-07-18T09:00:00Z"}],
            },
            model_loader=lambda _session: model,
        )


def test_event_neighborhood_selects_by_turn_id_and_tape_order() -> None:
    from tarav.chatlas.anchory import event_neighborhood

    model = _session_model(
        _event(1, role="assistant", timestamp="2026-07-18T08:51:04.561Z"),
        _event(2, role="user", timestamp="2026-07-18T08:51:04.561Z"),
        _event(3, role="assistant", timestamp="2026-07-18T08:51:04.561Z"),
    )
    neighborhood = event_neighborhood(model, turn_id="turn-2", radius=1)
    assert [event["sequence"] for event in neighborhood["chat"]["events"]] == [1, 2, 3]
    # Messages carry `Event.Ref` objects, so a projection addresses the tape by
    # the model's own coordinates rather than by a tape-local id.
    assert [
        [ref["event_address"] for ref in message["event_refs"]]
        for message in neighborhood["chat"]["messages"]
    ] == [[f"{sequence:064x}"] for sequence in (1, 2, 3)]
    assert neighborhood["chat"]["model_runs"] == []
    assert neighborhood["chat"]["tool_invocations"] == []
    assert neighborhood["chat"]["usage"] == []
