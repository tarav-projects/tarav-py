from __future__ import annotations

from copy import deepcopy
import gzip
import json
from pathlib import Path

import pytest

from tarav._core.errors import CliError
from tarav.chatlas.lossless.anonymizer import anonymize_text
from tarav.chatlas.lossless.corpus import (
    _model_signature,
    _validate_checked_model,
    load_capture_records,
    load_script_spec,
    prepare_capture,
    register_candidate,
    verify_corpus,
)
from tarav.chatlas.lossless.message_ref import compute_chat_message_hash
from tarav.chatlas.lossless.pipeline import build_normal_model_from_row


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )


def _rollout(path: Path, *, session_id: str) -> None:
    _write_jsonl(
        path,
        [
            {
                "timestamp": "2026-08-15T00:00:00.000Z",
                "type": "session_meta",
                "payload": {
                    "id": session_id,
                    "cwd": "/Users/alice/private-project",
                    "email": "alice@example.com",
                },
            },
            {
                "timestamp": "2026-08-15T00:00:01.000Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "id": "user-message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": "hello"}],
                },
            },
            {
                "timestamp": "2026-08-15T00:00:02.000Z",
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "id": "assistant-message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "hi"}],
                },
            },
        ],
    )


def _artifact(path: Path) -> dict[str, object]:
    return {"path": str(path), "role": "transcript", "extractable": True}


def _row(*paths: Path) -> dict[str, object]:
    artifacts = [_artifact(path) for path in paths]
    return {
        "provider": "codex",
        "session_id": "019ccafa-7835-7fc3-ac17-0e0a0f675c22",
        "identity_hash": "a" * 64,
        "backing_artifacts": artifacts[:1],
        "archive_versions": [
            {"provider": "codex", "backing_artifacts": [artifact]}
            for artifact in artifacts
        ],
    }


def _script(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema": "tarav.chatlas2.conformance.script.v1",
                "script_id": "sample",
                "revision": 1,
                "title": "Sample",
                "user_messages": ["hello"],
                "operator_actions": [],
                "features": ["messages"],
                "capture_requirements": ["closed-session"],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_text_anonymizer_is_deterministic_and_raw_model_agnostic() -> None:
    source = (
        "opaque /Users/alice/work alice@example.com "
        "019ccafa-7835-7fc3-ac17-0e0a0f675c22 api_key=secret-value\n"
    )

    first = anonymize_text(source)
    second = anonymize_text(source)

    assert first == second
    assert "/Users/alice" not in first.text
    assert "alice@example.com" not in first.text
    assert "019ccafa-7835-7fc3-ac17-0e0a0f675c22" not in first.text
    assert "secret-value" not in first.text
    assert first.text.endswith("\n")
    assert first.replacements
    assert first.warnings == ()


def test_specimen_signature_ignores_identity_order_between_equal_event_shapes() -> None:
    def model(first_id: str, second_id: str) -> dict[str, object]:
        first_address = first_id * 64
        second_address = second_id * 64
        first_ref = {"event_address": first_address, "event_hash": "1" * 64}
        second_ref = {"event_address": second_address, "event_hash": "2" * 64}
        events = [
            {
                "event_address": first_address,
                "event_hash": first_ref["event_hash"],
                "started_at": "2026-08-15T00:00:00Z",
                "class": "Record.Event",
                "origin": "Agent.Event",
            },
            {
                "event_address": second_address,
                "event_hash": second_ref["event_hash"],
                "started_at": "2026-08-15T00:00:00Z",
                "class": "Record.Event",
                "origin": "Agent.Event",
            },
        ]
        return {
            "events": events,
            "annotations": {
                "chat_messages": [{"side": "agent", "event_refs": [second_ref]}],
                "agent_loaded_contexts": [
                    {
                        "agent_event_ref": first_ref,
                        "event_refs": [second_ref, first_ref],
                    }
                ],
            },
        }

    assert _model_signature(model("a", "b")) == _model_signature(model("b", "a"))


def test_checked_model_requires_unique_self_verifying_message_addresses(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.jsonl"
    _rollout(source, session_id="019ccafa-7835-7fc3-ac17-0e0a0f675c22")
    model = build_normal_model_from_row(_row(source))

    _validate_checked_model(model)

    duplicate = deepcopy(model)
    duplicate["annotations"]["chat_messages"].append(
        deepcopy(duplicate["annotations"]["chat_messages"][0])
    )
    with pytest.raises(CliError, match="message addresses are not unique"):
        _validate_checked_model(duplicate)

    invalid_hash = deepcopy(model)
    invalid_hash["annotations"]["chat_messages"][0]["message_hash"] = "0" * 64
    with pytest.raises(CliError, match="Chat.Message.Hash"):
        _validate_checked_model(invalid_hash)


def test_checked_model_rejects_message_side_origin_disagreement(tmp_path: Path) -> None:
    source = tmp_path / "source.jsonl"
    _rollout(source, session_id="019ccafa-7835-7fc3-ac17-0e0a0f675c22")
    model = build_normal_model_from_row(_row(source))
    message = model["annotations"]["chat_messages"][0]
    message["side"] = "agent"
    message["message_hash"] = compute_chat_message_hash(message)

    with pytest.raises(CliError, match="side does not agree with member origins"):
        _validate_checked_model(model)


def test_prepare_and_register_capture_preserve_specimen_and_archive_every_artifact(
    tmp_path: Path,
) -> None:
    first = tmp_path / "source" / "first.jsonl"
    second = tmp_path / "source" / "second.jsonl"
    _rollout(first, session_id="019ccafa-7835-7fc3-ac17-0e0a0f675c22")
    _rollout(second, session_id="019ccafa-7835-7fc3-ac17-0e0a0f675c22")
    script = load_script_spec(_script(tmp_path / "sample.json"))
    corpus = tmp_path / "corpus"
    stage = tmp_path / "stage"

    candidate = prepare_capture(
        row=_row(first, second),
        script=script,
        captured_at="2026-08-15",
        features=("messages",),
        stage_dir=stage,
    )

    assert candidate.is_file()
    assert not corpus.exists()
    prepared = json.loads(candidate.read_text(encoding="utf-8"))
    assert len(prepared["record"]["artifacts"]) == 2
    assert all(
        artifact["raw_model_version"] == "codex.rollout.5f98"
        for artifact in prepared["record"]["artifacts"]
    )
    assert register_candidate(candidate, corpus_root=corpus) is True
    assert register_candidate(candidate, corpus_root=corpus) is False

    records = load_capture_records(corpus / "captures.jsonl")
    assert len(records) == 1
    assert "019ccafa-7835-7fc3-ac17-0e0a0f675c22" not in json.dumps(records)
    assert verify_corpus(corpus) == {
        "artifact_count": 2,
        "capture_count": 1,
        "status": "ok",
    }
    for artifact in records[0]["artifacts"]:
        stored = corpus / artifact["path"]
        assert stored.is_file()
        assert len(gzip.decompress(stored.read_bytes())) == artifact["size"]


def test_registry_rejects_a_conflicting_capture_identifier(tmp_path: Path) -> None:
    source = tmp_path / "source.jsonl"
    _rollout(source, session_id="019ccafa-7835-7fc3-ac17-0e0a0f675c22")
    script = load_script_spec(_script(tmp_path / "sample.json"))
    corpus = tmp_path / "corpus"
    candidate = prepare_capture(
        row=_row(source),
        script=script,
        captured_at="2026-08-15",
        features=("messages",),
        stage_dir=tmp_path / "stage",
    )
    assert register_candidate(candidate, corpus_root=corpus) is True
    payload = json.loads(candidate.read_text(encoding="utf-8"))
    payload["record"]["provider"] = "claude-code"
    candidate.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CliError, match="conflicting capture_id"):
        register_candidate(candidate, corpus_root=corpus)


def test_registry_rejects_capture_content_drift(tmp_path: Path) -> None:
    source = tmp_path / "source.jsonl"
    _rollout(source, session_id="019ccafa-7835-7fc3-ac17-0e0a0f675c22")
    script = load_script_spec(_script(tmp_path / "sample.json"))
    corpus = tmp_path / "corpus"
    candidate = prepare_capture(
        row=_row(source),
        script=script,
        captured_at="2026-08-15",
        features=("messages",),
        stage_dir=tmp_path / "stage",
    )
    assert register_candidate(candidate, corpus_root=corpus) is True
    registry = corpus / "captures.jsonl"
    record = json.loads(registry.read_text(encoding="utf-8"))
    record["captured_at"] = "2026-08-16"
    registry.write_text(json.dumps(record) + "\n", encoding="utf-8")

    with pytest.raises(CliError, match="does not match registry content"):
        verify_corpus(corpus)


def test_script_spec_is_strict(tmp_path: Path) -> None:
    path = _script(tmp_path / "sample.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["unexpected"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(CliError, match="unexpected keys"):
        load_script_spec(path)
