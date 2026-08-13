from __future__ import annotations

import json
from pathlib import Path

from agentos.chatlas.normalization.session_assembler import assemble_session_model
from agentos.chatlas.normalization.session_model._model import (
    _session_model_artifact_dir,
    build_chatlas_session_model_from_index_row,
    build_session_model_with_delta_state,
    record_delta_checkpoint,
)
from agentos.chatlas.normalization.session_model.artifact import (
    write_session_model_artifact,
)
from agentos.chatlas.normalization.session_model.delta import (
    claude_delta_normalization_result,
    delta_checkpoint_path,
    load_delta_checkpoint,
    save_delta_checkpoint,
)

from .test_tape_provenance import (
    _assistant_record,
    _closed_turn_records,
    _open_turn_records,
    _second_closed_turn_records,
    _user_record,
    _write_jsonl,
)


def _row(jsonl_path: Path) -> dict[str, object]:
    return {
        "provider": "claude-code",
        "session_id": "S1",
        "identity_hash": "delta-test-identity",
        "backing_artifacts": [
            {
                "role": "transcript",
                "storage_kind": "file",
                "path": str(jsonl_path),
                "extractable": True,
            }
        ],
    }


def _full_derive_and_publish(row: dict[str, object], chatlas_root: Path) -> dict[str, object]:
    """Derive and publish the way the view producer does: artifact write and
    checkpoint record in lockstep."""
    model, delta_state = build_session_model_with_delta_state(
        row, chatlas_root=chatlas_root
    )
    write_session_model_artifact(model, _session_model_artifact_dir(row, chatlas_root))
    record_delta_checkpoint(row, chatlas_root=chatlas_root, delta_state=delta_state)
    return model


def test_delta_pass_equals_full_derivation(tmp_path):
    jsonl = tmp_path / "raw" / "S1.jsonl"
    jsonl.parent.mkdir()
    root = tmp_path / "chatlas"
    base = _closed_turn_records() + _second_closed_turn_records()
    _write_jsonl(jsonl, base)
    row = _row(jsonl)

    _full_derive_and_publish(row, root)
    assert load_delta_checkpoint(root, provider="claude-code", session_id="S1")

    _write_jsonl(jsonl, base + _open_turn_records(parent="a6"))
    delta_result = claude_delta_normalization_result(
        row,
        chatlas_root=root,
        artifact_dir=_session_model_artifact_dir(row, root),
        trust="verify",
    )
    assert delta_result is not None

    delta_model = assemble_session_model(row, delta_result)
    assert "delta_state" not in delta_model["normalization"]
    assert delta_model["normalization"]["derivation"] == "delta"
    full_model = assemble_session_model(row)
    assert full_model["normalization"]["derivation"] == "full"
    # derivation is pure provenance — the only field the oracle excludes
    full_model["normalization"]["derivation"] = "delta"
    assert json.dumps(delta_model, sort_keys=True) == json.dumps(
        full_model, sort_keys=True
    )


def test_delta_pass_with_queued_user_input_equals_full_derivation(tmp_path):
    jsonl = tmp_path / "raw" / "S1.jsonl"
    jsonl.parent.mkdir()
    root = tmp_path / "chatlas"
    base = _closed_turn_records() + _second_closed_turn_records()
    _write_jsonl(jsonl, base)
    row = _row(jsonl)
    _full_derive_and_publish(row, root)

    queued = {
        "type": "attachment",
        "uuid": "q7",
        "parentUuid": "a6",
        "timestamp": "2026-07-26T10:00:07.000Z",
        "sessionId": "S1",
        "attachment": {
            "type": "queued_command",
            "prompt": "change the active plan",
            "commandMode": "prompt",
            "origin": {"kind": "human"},
            "timestamp": "2026-07-26T10:00:07.000Z",
        },
    }
    extension = [
        queued,
        _assistant_record(
            "a8",
            "following the change",
            parent="q7",
            message_id="msg4",
            stop_reason=None,
        ),
    ]
    _write_jsonl(jsonl, base + extension)

    delta_result = claude_delta_normalization_result(
        row,
        chatlas_root=root,
        artifact_dir=_session_model_artifact_dir(row, root),
        trust="verify",
    )
    assert delta_result is not None
    delta_model = assemble_session_model(row, delta_result)
    full_model = assemble_session_model(row)
    full_model["normalization"]["derivation"] = "delta"
    assert json.dumps(delta_model, sort_keys=True) == json.dumps(
        full_model, sort_keys=True
    )

    queued_event = next(
        event
        for event in delta_model["chat"]["events"]
        if (event.get("payload") or {}).get("content")
        == [{"type": "text", "text": "change the active plan"}]
    )
    assert queued_event["annotations"]["normal_turn"] == {
        "id": "q7",
        "kind": "user",
    }


def _tool_use_turn_records() -> list[dict]:
    """A closed tool turn with no progress records — normalizes fine but emits
    benign 'missing PreToolUse/PostToolUse progress' tool-pass warnings."""
    user = _user_record("u3", "list the files", parent="a2")
    request = _assistant_record(
        "a4", "", parent="u3", message_id="msg2", stop_reason="tool_use"
    )
    request["message"]["content"] = [
        {"type": "tool_use", "id": "toolu_1", "name": "Bash", "input": {"command": "ls"}}
    ]
    result = _user_record("u5", "", parent="a4")
    result["message"]["content"] = [
        {
            "type": "tool_result",
            "tool_use_id": "toolu_1",
            "content": [{"type": "text", "text": "ok"}],
        }
    ]
    closing = _assistant_record(
        "a6", "done", parent="u5", message_id="msg3", stop_reason="end_turn"
    )
    return [user, request, result, closing]


def test_delta_engages_with_benign_frozen_warnings(tmp_path):
    jsonl = tmp_path / "raw" / "S1.jsonl"
    jsonl.parent.mkdir()
    root = tmp_path / "chatlas"
    base = (
        _closed_turn_records()
        + _tool_use_turn_records()
        + [
            _user_record("u7", "follow-up", parent="a6"),
            _assistant_record(
                "a8",
                "follow-up answer",
                parent="u7",
                message_id="msg4",
                stop_reason="end_turn",
            ),
        ]
    )
    _write_jsonl(jsonl, base)
    row = _row(jsonl)
    _full_derive_and_publish(row, root)

    # the benign warnings land in the frozen prefix, split off the volatile suffix
    checkpoint = load_delta_checkpoint(root, provider="claude-code", session_id="S1")
    assert checkpoint is not None
    frozen_pass_warnings = checkpoint["state"]["frozen_pass_warnings"]
    assert any("progress" in w for w in frozen_pass_warnings["tool"])

    _write_jsonl(
        jsonl,
        base
        + [
            _user_record("u9", "next question", parent="a8"),
            _assistant_record(
                "b1", "next partial", parent="u9", message_id="msg5", stop_reason=None
            ),
        ],
    )
    delta_result = claude_delta_normalization_result(
        row,
        chatlas_root=root,
        artifact_dir=_session_model_artifact_dir(row, root),
        trust="verify",
    )
    assert delta_result is not None
    assert any("progress" in w for w in delta_result.warnings)

    delta_model = assemble_session_model(row, delta_result)
    full_model = assemble_session_model(row)
    full_model["normalization"]["derivation"] = "delta"
    assert json.dumps(delta_model, sort_keys=True) == json.dumps(
        full_model, sort_keys=True
    )


def test_chained_deltas_stay_equivalent(tmp_path):
    jsonl = tmp_path / "raw" / "S1.jsonl"
    jsonl.parent.mkdir()
    root = tmp_path / "chatlas"
    records = _closed_turn_records() + _second_closed_turn_records()
    _write_jsonl(jsonl, records)
    row = _row(jsonl)
    _full_derive_and_publish(row, root)

    extensions = [
        [
            _user_record("u7", "third question", parent="a6"),
            _assistant_record(
                "a8", "third answer", parent="u7", message_id="msg4", stop_reason="end_turn"
            ),
        ],
        [
            _user_record("u9", "fourth question", parent="a8"),
            _assistant_record(
                "b1", "fourth partial", parent="u9", message_id="msg5", stop_reason=None
            ),
        ],
    ]
    for extension in extensions:
        records = records + extension
        _write_jsonl(jsonl, records)
        delta_result = claude_delta_normalization_result(
            row,
            chatlas_root=root,
            artifact_dir=_session_model_artifact_dir(row, root),
            trust="verify",
        )
        assert delta_result is not None
        delta_model = assemble_session_model(row, delta_result)

        reference = build_chatlas_session_model_from_index_row(row)
        assert delta_model["chat"] == reference["chat"]
        assert delta_model["session"] == reference["session"]

        # publish the delta result so the next round resumes from it
        write_session_model_artifact(delta_model, _session_model_artifact_dir(row, root))
        state = delta_result.metadata["delta_state"]
        assert isinstance(state, dict)
        record_delta_checkpoint(row, chatlas_root=root, delta_state=state)


def test_repeated_builds_keep_delta_engaged_without_republish(tmp_path):
    """Plain builds never advance the checkpoint, so successive updates all
    resume from the last published artifact instead of falling back to full."""
    jsonl = tmp_path / "raw" / "S1.jsonl"
    jsonl.parent.mkdir()
    root = tmp_path / "chatlas"
    base = _closed_turn_records() + _second_closed_turn_records()
    _write_jsonl(jsonl, base)
    row = _row(jsonl)
    _full_derive_and_publish(row, root)
    checkpoint_before = load_delta_checkpoint(root, provider="claude-code", session_id="S1")

    _write_jsonl(jsonl, base + _open_turn_records(parent="a6"))
    kwargs = dict(chatlas_root=root, artifact_dir=_session_model_artifact_dir(row, root))
    for _ in range(3):
        model = build_chatlas_session_model_from_index_row(row, chatlas_root=root)
        assert model["normalization"]["derivation"] == "delta"
        assert "delta_state" not in model["normalization"]
        assert claude_delta_normalization_result(row, trust="verify", **kwargs) is not None

    checkpoint_after = load_delta_checkpoint(root, provider="claude-code", session_id="S1")
    assert checkpoint_after == checkpoint_before


def test_verify_tier_catches_mutated_frozen_record(tmp_path):
    jsonl = tmp_path / "raw" / "S1.jsonl"
    jsonl.parent.mkdir()
    root = tmp_path / "chatlas"
    base = _closed_turn_records() + _second_closed_turn_records()
    _write_jsonl(jsonl, base)
    row = _row(jsonl)
    _full_derive_and_publish(row, root)

    mutated = [dict(record) for record in base]
    mutated[0] = json.loads(json.dumps(base[0]))
    mutated[0]["message"]["content"][0]["text"] = "first question, tampered"
    _write_jsonl(jsonl, mutated + _open_turn_records(parent="a6"))

    kwargs = dict(
        chatlas_root=root,
        artifact_dir=_session_model_artifact_dir(row, root),
    )
    assert claude_delta_normalization_result(row, trust="verify", **kwargs) is None
    assert claude_delta_normalization_result(row, trust="append", **kwargs) is not None
    assert claude_delta_normalization_result(row, trust="rebuild", **kwargs) is None


def test_fork_into_frozen_prefix_falls_back(tmp_path):
    jsonl = tmp_path / "raw" / "S1.jsonl"
    jsonl.parent.mkdir()
    root = tmp_path / "chatlas"
    base = _closed_turn_records() + _second_closed_turn_records()
    _write_jsonl(jsonl, base)
    row = _row(jsonl)
    _full_derive_and_publish(row, root)

    # a rewind: the new user turn forks from u1 deep in the frozen prefix
    _write_jsonl(jsonl, base + [_user_record("u8", "rewound question", parent="u1")])
    assert (
        claude_delta_normalization_result(
            row,
            chatlas_root=root,
            artifact_dir=_session_model_artifact_dir(row, root),
            trust="append",
        )
        is None
    )


def test_tail_internal_fork_falls_back(tmp_path):
    """A fork whose branch point is inside the appended tail passes the linearity
    guard (every parent is 'known') but still needs full derivation's lineage
    marks — delta must fall back, or it silently emits a shorter tape than full."""
    jsonl = tmp_path / "raw" / "S1.jsonl"
    jsonl.parent.mkdir()
    root = tmp_path / "chatlas"
    base = _closed_turn_records() + _second_closed_turn_records()
    _write_jsonl(jsonl, base)
    row = _row(jsonl)
    _full_derive_and_publish(row, root)
    assert load_delta_checkpoint(root, provider="claude-code", session_id="S1")

    # tail: u8 extends linearly from the frozen tip, a9 answers it, then u10 rewinds
    # off u8 — a conversation fork rooted on a tail record (u8), not the frozen prefix
    tail = [
        _user_record("u8", "a question", parent="a6"),
        _assistant_record("a9", "an answer", parent="u8", message_id="msgT", stop_reason="end_turn"),
        _user_record("u10", "rewound question", parent="u8"),
    ]
    _write_jsonl(jsonl, base + tail)

    for trust in ("append", "verify"):
        assert (
            claude_delta_normalization_result(
                row,
                chatlas_root=root,
                artifact_dir=_session_model_artifact_dir(row, root),
                trust=trust,
            )
            is None
        ), f"delta must fall back on a tail-internal fork (trust={trust})"

    # and the full-derivation path stays correct end to end
    delta_model = build_chatlas_session_model_from_index_row(
        row, chatlas_root=root, trust="append"
    )
    full_model = build_chatlas_session_model_from_index_row(row)
    full_model["normalization"]["derivation"] = delta_model["normalization"]["derivation"]
    assert json.dumps(delta_model, sort_keys=True) == json.dumps(
        full_model, sort_keys=True
    )


def test_checkpoint_round_trip_and_corruption(tmp_path):
    root = tmp_path / "chatlas"
    state = {"frozen_record_count": 2, "anything": True}
    save_delta_checkpoint(
        root,
        provider="claude-code",
        session_id="S9",
        source_path=tmp_path / "x.jsonl",
        delta_state=state,
    )
    loaded = load_delta_checkpoint(root, provider="claude-code", session_id="S9")
    assert loaded is not None and loaded["state"] == state

    path = delta_checkpoint_path(root, provider="claude-code", session_id="S9")
    path.write_text("{broken", encoding="utf-8")
    assert load_delta_checkpoint(root, provider="claude-code", session_id="S9") is None
