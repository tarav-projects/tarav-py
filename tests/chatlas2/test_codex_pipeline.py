from __future__ import annotations

import json
from pathlib import Path

from tarav.chatlas2.codex import (
    CODEX_RAW_MODEL_VERSION,
    CodexRawModelVersioner,
    CodexRawNormalizer,
)
from tarav.chatlas2.pipeline import build_normal_model_from_row


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )


def _record(
    timestamp: str,
    record_type: str,
    payload: dict[str, object],
) -> dict[str, object]:
    return {"timestamp": timestamp, "type": record_type, "payload": payload}


def _message(
    timestamp: str,
    role: str,
    text: str,
    *,
    message_id: str,
) -> dict[str, object]:
    content_type = "output_text" if role == "assistant" else "input_text"
    return _record(
        timestamp,
        "response_item",
        {
            "type": "message",
            "id": message_id,
            "role": role,
            "content": [{"type": content_type, "text": text}],
        },
    )


def _artifact(path: Path) -> dict[str, object]:
    return {
        "path": str(path),
        "role": "transcript",
        "storage_kind": "file",
        "extractable": True,
    }


def _row(*artifacts: Path) -> dict[str, object]:
    serialized = [_artifact(path) for path in artifacts]
    return {
        "provider": "codex",
        "session_id": "codex-session",
        "identity_hash": "identity",
        "backing_artifacts": serialized[:1],
        "archive_versions": [
            {"provider": "codex", "backing_artifacts": [artifact]}
            for artifact in serialized
        ],
    }


def test_codex_versioner_and_normalizer_keep_the_minimal_semantic_floor(
    tmp_path: Path,
) -> None:
    path = tmp_path / "rollout.jsonl"
    records = [
        _record(
            "2026-08-15T00:00:00.000Z",
            "session_meta",
            {"id": "codex-session", "originator": "codex_cli_rs"},
        ),
        _message(
            "2026-08-15T00:00:01.000Z",
            "developer",
            "system instructions",
            message_id="developer-1",
        ),
        _message(
            "2026-08-15T00:00:02.000Z",
            "user",
            "# AGENTS.md instructions for /repo",
            message_id="injected-1",
        ),
        _message(
            "2026-08-15T00:00:03.000Z",
            "user",
            "hello",
            message_id="user-1",
        ),
        _record(
            "2026-08-15T00:00:04.000Z",
            "response_item",
            {"type": "reasoning", "id": "reasoning-1", "summary": []},
        ),
        _message(
            "2026-08-15T00:00:05.000Z",
            "assistant",
            "hi",
            message_id="assistant-1",
        ),
        _record(
            "2026-08-15T00:00:06.000Z",
            "future_record",
            {"opaque": True},
        ),
    ]
    _write_jsonl(path, records)

    versioner = CodexRawModelVersioner()
    assert versioner.version(path) == CODEX_RAW_MODEL_VERSION
    assert CodexRawNormalizer.supported_raw_model_versions == frozenset(
        {CODEX_RAW_MODEL_VERSION}
    )

    model = build_normal_model_from_row(_row(path))

    assert [event["origin"] for event in model["events"]] == [
        "agent",
        "agent",
        "agent",
        "user",
        "agent",
        "agent",
        "unresolved",
    ]
    assert [event["class"] for event in model["events"]] == [
        "Agent.Event",
        "Agent.Event",
        "Agent.Event",
        "User.Event",
        "Agent.Event",
        "Agent.Event",
        "Unresolved.Event",
    ]
    assert [message["side"] for message in model["annotations"]["chat_messages"]] == [
        "user",
        "agent",
    ]
    contexts = model["annotations"]["agent_loaded_contexts"]
    assert all(
        message["class"] == "Chat.Message"
        for message in model["annotations"]["chat_messages"]
    )
    assert all(context["class"] == "Agent.Loaded.Context" for context in contexts)
    assert len(contexts) == 2
    assert contexts[0]["event_ids"] == contexts[1]["event_ids"]
    assert len(contexts[0]["event_ids"]) == 3

    malformed = tmp_path / "malformed.jsonl"
    malformed.write_text('{"type":"session_meta"}\nnot-json\n', encoding="utf-8")
    assert versioner.version(malformed) is None


def test_multi_artifact_union_collapses_only_same_position_observations(
    tmp_path: Path,
) -> None:
    old = tmp_path / "old.jsonl"
    new = tmp_path / "new.jsonl"
    prefix = [
        _record(
            "2026-08-15T00:00:00.000Z",
            "session_meta",
            {"id": "codex-session", "originator": "codex_cli_rs"},
        ),
        _record(
            "2026-08-15T00:00:01.000Z",
            "turn_context",
            {"turn_id": "turn-1", "model": "gpt"},
        ),
        _message(
            "2026-08-15T00:00:02.000Z",
            "user",
            "first question",
            message_id="user-1",
        ),
        _message(
            "2026-08-15T00:00:03.000Z",
            "assistant",
            "first answer",
            message_id="assistant-1",
        ),
    ]
    continuation = [
        _message(
            "2026-08-15T00:00:04.000Z",
            "user",
            "second question",
            message_id="user-2",
        ),
        _message(
            "2026-08-15T00:00:05.000Z",
            "assistant",
            "second answer",
            message_id="assistant-2",
        ),
    ]
    _write_jsonl(old, prefix)
    _write_jsonl(new, [*prefix, *continuation])

    model = build_normal_model_from_row(_row(old, new))

    assert len(model["sources"]) == 2
    assert len(model["events"]) == 6
    assert [event["started_at"] for event in model["events"]] == sorted(
        event["started_at"] for event in model["events"]
    )
    assert [len(event["observations"]) for event in model["events"]] == [
        2,
        2,
        2,
        2,
        1,
        1,
    ]
    assert len(model["annotations"]["chat_messages"]) == 4
    assert len(model["annotations"]["agent_loaded_contexts"]) == 2


def test_same_raw_record_at_a_different_position_is_retained(tmp_path: Path) -> None:
    first = tmp_path / "first.jsonl"
    second = tmp_path / "second.jsonl"
    meta = _record(
        "2026-08-15T00:00:00.000Z",
        "session_meta",
        {"id": "codex-session", "originator": "codex_cli_rs"},
    )
    repeated = _message(
        "2026-08-15T00:00:02.000Z",
        "user",
        "same raw message",
        message_id="user-1",
    )
    _write_jsonl(first, [meta, repeated])
    _write_jsonl(
        second,
        [
            meta,
            _record(
                "2026-08-15T00:00:01.000Z",
                "turn_context",
                {"turn_id": "turn-1"},
            ),
            repeated,
        ],
    )

    model = build_normal_model_from_row(_row(first, second))

    assert len(model["events"]) == 4
    assert len(model["annotations"]["chat_messages"]) == 2
