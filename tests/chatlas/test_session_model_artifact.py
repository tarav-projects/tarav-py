# $kw: ^test-session-artifact-sequences --from Chatlas.Session.Model.Tests --from Session.Event.Tape --note [CT] session artifacts preserve ordered canonical events without retired event_id fields ^c20260728-16u
from __future__ import annotations

import json

from agentos.chatlas.normalization.session_model.artifact import (
    SESSION_MODEL_HEAD_ARTIFACT,
    load_session_model_artifact,
    write_session_model_artifact,
)


def _sample_model() -> dict[str, object]:
    return {
        "class": "agentos_chatlas.session_model",
        "schema_version": "2",
        "session": {
            "provider": "claude-code",
            "session_id": "S1",
            "identity_hash": "H1",
            "content_hash": "C1",
        },
        "agent_instance": {"instance": "i1", "provider_family": "claude-code"},
        "sources": [{"path": "/tmp/raw.jsonl", "kind": "transcript"}],
        "chat": {
            "messages": [{"message_id": "m1", "role": "user", "text": "hi"}],
            "model_runs": [{"run_id": "r1", "status": "completed"}],
            "tool_invocations": [{"call_id": "t1", "tool_name": "Bash"}],
            "events": [
                {"sequence": 1, "kind": "message", "payload": {"text": "hi"}},
                {"sequence": 2, "kind": "tool_call", "payload": {"tool": "Bash"}},
            ],
            "usage": [{"usage_id": "u1", "input_tokens": 3}],
        },
        "normalization": {"provider": "claude-code", "version": 1, "warnings": []},
    }


def test_round_trip_preserves_model_exactly(tmp_path):
    model = _sample_model()
    write_session_model_artifact(model, tmp_path)
    assert load_session_model_artifact(tmp_path) == model


def test_artifact_layout_is_split(tmp_path):
    write_session_model_artifact(_sample_model(), tmp_path)

    head = json.loads((tmp_path / SESSION_MODEL_HEAD_ARTIFACT).read_text())
    assert head["session"]["session_id"] == "S1"
    assert "chat" not in head

    tape_lines = (tmp_path / "events.jsonl").read_text().strip().splitlines()
    assert [json.loads(line)["sequence"] for line in tape_lines] == [1, 2]

    assert json.loads((tmp_path / "tool_invocations.json").read_text()) == [
        {"call_id": "t1", "tool_name": "Bash"}
    ]


def test_empty_tape_round_trips(tmp_path):
    model = _sample_model()
    model["chat"] = {
        "messages": [],
        "model_runs": [],
        "tool_invocations": [],
        "events": [],
        "usage": [],
    }
    write_session_model_artifact(model, tmp_path)
    assert load_session_model_artifact(tmp_path) == model


def test_round_trip_preserves_unicode_line_separators_inside_events(tmp_path):
    model = _sample_model()
    model["chat"]["events"][0]["payload"]["text"] = "before\u2028after"

    write_session_model_artifact(model, tmp_path)

    assert load_session_model_artifact(tmp_path) == model
