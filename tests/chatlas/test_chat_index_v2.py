from __future__ import annotations

import json
from pathlib import Path


from agentos.chatlas.chat_index import (
    _canonical_v2_source,
    _compare_v2_source_tail,
    _load_capture,
)
from agentos.chatlas.normalization.session_model.messages import (
    transcript_visible_messages,
)


IDENTITY = "a" * 64


def _turn(turn_id: str, *, sequence: int, timestamp: str) -> dict[str, object]:
    turn_ref = {
        "session": IDENTITY,
        "turn_id": turn_id,
        "turn_hash": (turn_id[-1] * 64),
        "at": timestamp,
    }
    return {
        "turn_ref": turn_ref,
        "normal_turn": {
            "turn_id": turn_id,
            "events": [
                {
                    "sequence": sequence,
                    "kind": "message",
                    "timestamp": timestamp,
                    "producer": {"type": "human"},
                    "payload": {"role": "user", "content": []},
                }
            ],
        },
    }


def _source(*, turns: list[dict[str, object]]) -> dict[str, object]:
    return {
        "materialized_source_hash": "sha256:" + "f" * 64,
        "turn_count": len(turns),
        "linear": True,
        "turn_refs": [
            {
                "turn_ref": turn["turn_ref"],
                "tape_position": turn["normal_turn"]["events"][0]["sequence"],
                "role": "user",
                "producer_type": "human",
            }
            for turn in turns
        ],
        "findings": [],
    }


def _write_surface(
    tmp_path: Path,
    *,
    deltas: dict[str, str],
    head: str = "# Chat.Index.HEAD\n",
    directory: str = IDENTITY,
) -> Path:
    surface = tmp_path / directory
    (surface / "deltas").mkdir(parents=True)
    for name, content in deltas.items():
        (surface / "deltas" / name).write_text(content, encoding="utf-8")
    (surface / "HEAD.md").write_text(head, encoding="utf-8")
    return surface


def test_v2_source_uses_tape_sequence_instead_of_timestamp() -> None:
    later_timestamp_first_on_tape = _turn(
        "turn-1", sequence=10, timestamp="2026-08-04T12:00:00Z"
    )
    earlier_timestamp_later_on_tape = _turn(
        "turn-2", sequence=20, timestamp="2026-08-04T11:00:00Z"
    )

    canonical = _canonical_v2_source(
        {"turns": [earlier_timestamp_later_on_tape, later_timestamp_first_on_tape]}
    )

    assert [turn["turn_ref"]["turn_id"] for turn in canonical["turns"]] == [
        "turn-1",
        "turn-2",
    ]


def test_v2_source_surfaces_non_linear_lineage() -> None:
    turn = _turn("turn-1", sequence=10, timestamp="2026-08-04T10:00:00Z")
    turn["normal_turn"]["events"].append({"sequence": 11, "kind": "lineage.rollback"})

    canonical = _canonical_v2_source({"turns": [turn]})

    assert canonical["linear"] is False
    assert canonical["findings"] == [
        {"kind": "non-linear-chat", "reason": "lineage.rollback", "sequence": 11}
    ]


def test_surface_rejects_a_delta_heading_that_disagrees_with_its_filename(
    tmp_path: Path,
) -> None:
    surface = _write_surface(
        tmp_path,
        deltas={"turn-1.md": "# Chat.Index.Delta/turn-9\n"},
    )

    loaded, error = _load_capture(surface, expected_identity_hash=IDENTITY)

    assert loaded is None
    assert "disagrees with its filename" in str(error)


def test_surface_rejects_a_directory_that_is_not_its_session_identity(
    tmp_path: Path,
) -> None:
    surface = _write_surface(
        tmp_path,
        deltas={"turn-1.md": "# Chat.Index.Delta/turn-1\n"},
        directory="b" * 64,
    )

    loaded, error = _load_capture(surface, expected_identity_hash=IDENTITY)

    assert loaded is None
    assert "is not its session identity" in str(error)


def test_surface_derives_its_deltas_and_head_horizon_from_the_files(
    tmp_path: Path,
) -> None:
    surface = _write_surface(
        tmp_path,
        deltas={
            "turn-1.md": "# Chat.Index.Delta/turn-1 @ 2026-08-04T10:00:00Z\n",
            "turn-2.md": "# Chat.Index.Delta/turn-2\n",
        },
        head="# Chat.Index.HEAD\n\nEvidence.Horizon: `turn-2`\n",
    )

    loaded, error = _load_capture(surface, expected_identity_hash=IDENTITY)

    assert error is None
    assert loaded is not None
    assert [delta["path"] for delta in loaded["deltas"]] == [
        "deltas/turn-1.md",
        "deltas/turn-2.md",
    ]
    assert loaded["deltas"][0]["horizon"] == {
        "session": IDENTITY,
        "turn_id": "turn-1",
        "at": "2026-08-04T10:00:00Z",
    }
    assert loaded["head"]["horizon"]["turn_id"] == "turn-2"
    assert loaded["managed_files"] == [
        "HEAD.md",
        "deltas/turn-1.md",
        "deltas/turn-2.md",
    ]


def test_v2_tail_classifies_current_and_append_only_sources() -> None:
    first = _turn("turn-1", sequence=10, timestamp="2026-08-04T10:00:00Z")
    second = _turn("turn-2", sequence=20, timestamp="2026-08-04T11:00:00Z")
    captured = _source(turns=[first])
    current = {
        **captured,
        "turn_count": 2,
        "turn_refs": [
            *captured["turn_refs"],
            {
                "turn_ref": second["turn_ref"],
                "tape_position": 20,
                "role": "user",
                "producer_type": "human",
            },
        ],
        "findings": [],
    }

    same = _compare_v2_source_tail(captured, captured)
    grown = _compare_v2_source_tail(captured, current)

    assert same["state"] == "current"
    assert same["pending_turn_count"] == 0
    assert same["turn_refs"] == []
    assert grown["state"] == "append-only"
    assert grown["pending_turn_count"] == 1
    assert grown["turn_refs"][0]["turn_ref"]["turn_id"] == "turn-2"


def test_v2_tail_fails_closed_on_divergence_and_non_linear_source() -> None:
    first = _turn("turn-1", sequence=10, timestamp="2026-08-04T10:00:00Z")
    captured = _source(turns=[first])
    divergent = json.loads(json.dumps(captured))
    divergent["turn_refs"][0]["turn_ref"]["turn_id"] = "turn-replaced"
    blocked = {
        **captured,
        "linear": False,
        "findings": [
            {"kind": "non-linear-chat", "reason": "lineage.rollback", "sequence": 11}
        ],
    }

    divergence = _compare_v2_source_tail(captured, divergent)
    non_linear = _compare_v2_source_tail(captured, blocked)

    assert divergence["state"] == "diverged"
    assert divergence["pending_turn_count"] == 0
    assert divergence["findings"][0]["kind"] == "source-prefix-diverged"
    assert non_linear["state"] == "blocked"
    assert non_linear["pending_turn_count"] == 0
    assert non_linear["findings"] == blocked["findings"]


def test_v2_tail_distinguishes_late_source_expansion_from_divergence() -> None:
    first = _turn("turn-1", sequence=10, timestamp="2026-08-04T10:00:00Z")
    late = _turn("turn-0", sequence=5, timestamp="2026-08-04T09:59:00Z")
    captured = _source(turns=[first])
    current = {
        **captured,
        "turn_count": 2,
        "turn_refs": [
            {
                "turn_ref": late["turn_ref"],
                "tape_position": 5,
                "role": None,
                "producer_type": "provider",
            },
            *captured["turn_refs"],
        ],
        "findings": [],
    }

    expanded = _compare_v2_source_tail(captured, current)

    assert expanded["state"] == "expanded"
    assert expanded["pending_turn_count"] == 1
    assert expanded["turn_refs"][0]["turn_ref"]["turn_id"] == "turn-0"


def test_v2_tail_surfaces_same_coordinate_content_revision() -> None:
    first = _turn("turn-1", sequence=10, timestamp="2026-08-04T10:00:00Z")
    captured = _source(turns=[first])
    revised = json.loads(json.dumps(captured))
    revised["turn_refs"][0]["turn_ref"]["turn_hash"] = "0" * 64

    tail = _compare_v2_source_tail(captured, revised)

    assert tail["state"] == "revised"
    assert tail["pending_turn_count"] == 1
    assert tail["pending_before_cursor_count"] == 1
    assert tail["revised_turn_count"] == 1
    assert tail["turn_refs"] == revised["turn_refs"]


def test_chat_evidence_keeps_visible_messages_in_tape_order() -> None:
    events = [
        {
            "sequence": 12,
            "kind": "message",
            "surfaces": {"transcript": "visible"},
            "payload": {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "first"},
                    {"type": "text", "text": "second"},
                ],
            },
        },
        {
            "sequence": 10,
            "kind": "message",
            "surfaces": {"transcript": "visible"},
            "payload": {"role": "user", "content": [{"type": "text", "text": "ask"}]},
        },
    ]

    assert transcript_visible_messages(events) == [
        {"sequence": 10, "role": "user", "text": "ask"},
        {"sequence": 12, "role": "assistant", "text": "first\nsecond"},
    ]


def test_chat_evidence_excludes_reasoning_tool_and_hidden_events() -> None:
    events = [
        {
            "sequence": 1,
            "kind": "message",
            "surfaces": {"transcript": "visible"},
            "payload": {"role": "user", "content": [{"type": "text", "text": "keep"}]},
        },
        {
            "sequence": 2,
            "kind": "reasoning",
            "surfaces": {"transcript": "visible"},
            "payload": {"role": "assistant", "content": [{"text": "thinking"}]},
        },
        {
            "sequence": 3,
            "kind": "tool.call",
            "surfaces": {"transcript": "visible"},
            "payload": {"role": "assistant", "content": [{"text": "ran a tool"}]},
        },
        {
            "sequence": 4,
            "kind": "tool.result",
            "surfaces": {"transcript": "visible"},
            "payload": {"role": "user", "content": [{"text": "tool output"}]},
        },
        {
            "sequence": 5,
            "kind": "message",
            "surfaces": {"transcript": "hidden"},
            "payload": {"role": "user", "content": [{"text": "context injection"}]},
        },
        {
            "sequence": 6,
            "kind": "message",
            "surfaces": {"transcript": "visible"},
            "payload": {"role": "system", "content": [{"text": "system note"}]},
        },
    ]

    assert transcript_visible_messages(events) == [
        {"sequence": 1, "role": "user", "text": "keep"}
    ]
