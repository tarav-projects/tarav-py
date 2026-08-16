from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from tarav.chatlas2.claude import (
    CLAUDE_LEGACY_RAW_MODEL_VERSION,
    CLAUDE_PROMPT_SOURCE_RAW_MODEL_VERSION,
    ClaudeLegacyRawNormalizer,
    ClaudePromptSourceRawNormalizer,
    ClaudeRawModelVersioner,
)
from tarav.chatlas2.event_ref import resolve_event_ref
from tarav.chatlas2.message_ref import resolve_chat_message_ref
from tarav.chatlas2.pipeline import build_normal_model_from_row


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    path.write_text(
        "\n".join(json.dumps(record) for record in records) + "\n",
        encoding="utf-8",
    )


def _record(
    record_type: str,
    *,
    uuid: str,
    timestamp: str,
    parent_uuid: str | None,
    session_id: str = "claude-session",
    version: str = "2.1.170",
    **extra: object,
) -> dict[str, object]:
    return {
        "type": record_type,
        "uuid": uuid,
        "parentUuid": parent_uuid,
        "sessionId": session_id,
        "timestamp": timestamp,
        "version": version,
        **extra,
    }


def _user(
    text: str,
    *,
    uuid: str,
    timestamp: str,
    parent_uuid: str | None,
    prompt_source: str | None = "typed",
) -> dict[str, object]:
    record = _record(
        "user",
        uuid=uuid,
        timestamp=timestamp,
        parent_uuid=parent_uuid,
        message={"role": "user", "content": text},
    )
    if prompt_source is not None:
        record["promptSource"] = prompt_source
    return record


def _assistant(
    block: dict[str, object],
    *,
    uuid: str,
    timestamp: str,
    parent_uuid: str,
    request_id: str,
) -> dict[str, object]:
    return _record(
        "assistant",
        uuid=uuid,
        timestamp=timestamp,
        parent_uuid=parent_uuid,
        requestId=request_id,
        message={"role": "assistant", "content": [block]},
    )


def _artifact(path: Path) -> dict[str, object]:
    return {"path": str(path), "role": "transcript", "extractable": True}


def _row(*paths: Path) -> dict[str, object]:
    artifacts = [_artifact(path) for path in paths]
    return {
        "provider": "claude-code",
        "session_id": "claude-session",
        "identity_hash": "identity",
        "backing_artifacts": artifacts[:1],
        "archive_versions": [
            {"provider": "claude-code", "backing_artifacts": [artifact]}
            for artifact in artifacts
        ],
    }


def _rollout() -> list[dict[str, object]]:
    return [
        {"type": "mode", "sessionId": "claude-session", "mode": "default"},
        _user(
            "hello",
            uuid="user-1",
            timestamp="2026-08-15T00:00:01Z",
            parent_uuid=None,
        ),
        _record(
            "attachment",
            uuid="attachment-1",
            timestamp="2026-08-15T00:00:02Z",
            parent_uuid="user-1",
            attachment={"kind": "context"},
        ),
        _assistant(
            {"type": "thinking", "thinking": "private", "signature": "sig"},
            uuid="assistant-1",
            timestamp="2026-08-15T00:00:03Z",
            parent_uuid="attachment-1",
            request_id="request-1",
        ),
        _assistant(
            {"type": "text", "text": "hi"},
            uuid="assistant-2",
            timestamp="2026-08-15T00:00:04Z",
            parent_uuid="assistant-1",
            request_id="request-1",
        ),
        _record(
            "system",
            uuid="duration-1",
            timestamp="2026-08-15T00:00:05Z",
            parent_uuid="assistant-2",
            subtype="turn_duration",
            durationMs=5,
        ),
        _record(
            "user",
            uuid="tool-result-1",
            timestamp="2026-08-15T00:00:06Z",
            parent_uuid="assistant-2",
            sourceToolAssistantUUID="assistant-2",
            message={
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "tool-1",
                        "content": "result",
                    }
                ],
            },
        ),
        _assistant(
            {"type": "tool_use", "id": "tool-2", "name": "Read", "input": {}},
            uuid="assistant-3",
            timestamp="2026-08-15T00:00:07Z",
            parent_uuid="tool-result-1",
            request_id="request-2",
        ),
        _assistant(
            {"type": "text", "text": "done"},
            uuid="assistant-4",
            timestamp="2026-08-15T00:00:08Z",
            parent_uuid="assistant-3",
            request_id="request-2",
        ),
        _user(
            "<command-name>/exit</command-name>",
            uuid="local-command-1",
            timestamp="2026-08-15T00:00:09Z",
            parent_uuid="assistant-4",
            prompt_source=None,
        ),
    ]


def _legacy_rollout() -> list[dict[str, object]]:
    return [
        {"type": "mode", "sessionId": "claude-session", "mode": "default"},
        _user(
            "legacy hello",
            uuid="legacy-user-1",
            timestamp="2026-08-15T00:00:01Z",
            parent_uuid=None,
            prompt_source=None,
        ),
        _assistant(
            {"type": "text", "text": "legacy answer"},
            uuid="legacy-assistant-1",
            timestamp="2026-08-15T00:00:02Z",
            parent_uuid="legacy-user-1",
            request_id="legacy-request-1",
        ),
        _record(
            "user",
            uuid="legacy-tool-result",
            timestamp="2026-08-15T00:00:03Z",
            parent_uuid="legacy-assistant-1",
            sourceToolAssistantUUID="legacy-assistant-1",
            message={
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "legacy-tool-1",
                        "content": "result",
                    }
                ],
            },
        ),
        _user(
            "<system-reminder>injected</system-reminder>",
            uuid="legacy-system-reminder",
            timestamp="2026-08-15T00:00:04Z",
            parent_uuid="legacy-tool-result",
            prompt_source=None,
        ),
        _user(
            "<command-name>/review</command-name><command-args>target</command-args>",
            uuid="legacy-command",
            timestamp="2026-08-15T00:00:05Z",
            parent_uuid="legacy-system-reminder",
            prompt_source=None,
        ),
        _record(
            "user",
            uuid="legacy-compact",
            timestamp="2026-08-15T00:00:06Z",
            parent_uuid="legacy-command",
            isCompactSummary=True,
            message={"role": "user", "content": "summary"},
        ),
        _user(
            "<command-name>/exit</command-name>",
            uuid="legacy-local-command",
            timestamp="2026-08-15T00:00:07Z",
            parent_uuid="legacy-compact",
            prompt_source=None,
        ),
    ]


@pytest.mark.parametrize("producer_version", ["2.1.170", "2.1.196", "2.1.223"])
def test_claude_versioner_recognizes_prompt_source_mapping_family(
    tmp_path: Path,
    producer_version: str,
) -> None:
    path = tmp_path / "transcript.jsonl"
    records = _rollout()
    for record in records:
        if "version" in record:
            record["version"] = producer_version
    _write_jsonl(path, records)

    assert (
        ClaudeRawModelVersioner().version(path)
        == CLAUDE_PROMPT_SOURCE_RAW_MODEL_VERSION
    )
    assert CLAUDE_PROMPT_SOURCE_RAW_MODEL_VERSION == "claude.transcript.1ecc"
    assert ClaudePromptSourceRawNormalizer.supported_raw_model_versions == frozenset(
        {CLAUDE_PROMPT_SOURCE_RAW_MODEL_VERSION}
    )


def test_claude_versioner_and_pipeline_recognize_legacy_mapping_family(
    tmp_path: Path,
) -> None:
    path = tmp_path / "legacy-transcript.jsonl"
    _write_jsonl(path, _legacy_rollout())

    assert ClaudeRawModelVersioner().version(path) == CLAUDE_LEGACY_RAW_MODEL_VERSION
    assert CLAUDE_LEGACY_RAW_MODEL_VERSION == "claude.transcript.b17b"
    assert ClaudeLegacyRawNormalizer.supported_raw_model_versions == frozenset(
        {CLAUDE_LEGACY_RAW_MODEL_VERSION}
    )

    model = build_normal_model_from_row(_row(path))
    assert [event["origin"] for event in model["events"]] == [
        "user",
        "agent",
        "agent",
        "agent",
        "user",
        "agent",
        "agent",
    ]
    assert [
        message["side"] for message in model["annotations"]["chat_messages"]
    ] == ["user", "agent", "user"]
    assert [
        message["text"] for message in model["annotations"]["chat_messages"]
    ] == ["legacy hello", "legacy answer", "target"]
    assert model["sources"][0]["raw_model_version"] == (
        CLAUDE_LEGACY_RAW_MODEL_VERSION
    )


def test_claude_versioner_allows_auxiliary_records_without_session_id(
    tmp_path: Path,
) -> None:
    path = tmp_path / "transcript-with-snapshot.jsonl"
    records = [
        {
            "type": "file-history-snapshot",
            "snapshot": {"trackedFileBackups": {}},
        },
        *_rollout(),
    ]
    _write_jsonl(path, records)

    assert (
        ClaudeRawModelVersioner().version(path)
        == CLAUDE_PROMPT_SOURCE_RAW_MODEL_VERSION
    )
    assert len(build_normal_model_from_row(_row(path))["events"]) == 9


@pytest.mark.parametrize("records", [_rollout(), _legacy_rollout()])
def test_claude_raw_evidence_is_optional_and_identity_inert(
    tmp_path: Path,
    records: list[dict[str, object]],
) -> None:
    path = tmp_path / "transcript.jsonl"
    _write_jsonl(path, records)

    compact = build_normal_model_from_row(_row(path))
    enriched = build_normal_model_from_row(_row(path), include_raw=True)

    raw = enriched.pop("raw")
    assert enriched == compact
    assert raw == [
        {
            "source_id": compact["sources"][0]["source_id"],
            "raw_model_version": compact["sources"][0]["raw_model_version"],
            "value": {"records": records},
        }
    ]


def test_claude_normalization_preserves_origin_messages_refs_and_context(
    tmp_path: Path,
) -> None:
    path = tmp_path / "transcript.jsonl"
    _write_jsonl(path, _rollout())

    model = build_normal_model_from_row(_row(path))

    assert model["session"]["provider"] == "claude-code"
    assert model["schema_version"] == 5
    assert "raw" not in model
    assert all("record" not in event and "raw" not in event for event in model["events"])
    assert len(model["events"]) == 9
    assert [event["started_at"] for event in model["events"]] == sorted(
        event["started_at"] for event in model["events"]
    )
    assert model["events"][0]["origin"] == "user"
    assert all(event["origin"] == "agent" for event in model["events"][1:])

    messages = model["annotations"]["chat_messages"]
    assert [message["side"] for message in messages] == ["user", "agent", "agent"]
    assert [message["text"] for message in messages] == ["hello", "hi", "done"]
    event_by_address = {
        event["event_address"]: event for event in model["events"]
    }
    assert [
        event_by_address[message["event_refs"][0]["event_address"]]["content"]
        for message in messages
    ] == [{"text": "hello"}, {"text": "hi"}, {"text": "done"}]
    assert all(
        resolve_chat_message_ref(
            messages,
            {
                "message_address": message["message_address"],
                "message_hash": message["message_hash"],
            },
        )["standing"]
        == "MATCHED"
        for message in messages
    )

    contexts = model["annotations"]["agent_loaded_contexts"]
    assert len(contexts) == 4
    context_members = []
    for context in contexts:
        assert resolve_event_ref(
            model["events"], context["agent_event_ref"]
        )["standing"] == "MATCHED"
        resolved = [
            resolve_event_ref(model["events"], ref)["event"]["started_at"]
            for ref in context["event_refs"]
        ]
        context_members.append(resolved)
    assert context_members == [
        ["2026-08-15T00:00:01Z"],
        ["2026-08-15T00:00:01Z"],
        ["2026-08-15T00:00:06Z"],
        ["2026-08-15T00:00:06Z"],
    ]


def test_claude_normalization_unions_every_artifact_without_losing_continuation(
    tmp_path: Path,
) -> None:
    current = tmp_path / "current.jsonl"
    historical = tmp_path / "historical.jsonl"
    records = _rollout()
    _write_jsonl(current, records[:5])
    _write_jsonl(historical, records)

    model = build_normal_model_from_row(_row(current, historical))

    assert len(model["sources"]) == 2
    assert len(model["events"]) == 9
    assert model["events"][-1]["started_at"] == "2026-08-15T00:00:09Z"
    observations_by_time = {
        event["started_at"]: len(event["observations"])
        for event in model["events"]
    }
    assert observations_by_time["2026-08-15T00:00:01Z"] == 2
    assert observations_by_time["2026-08-15T00:00:04Z"] == 2
    assert observations_by_time["2026-08-15T00:00:08Z"] == 1
    assert len(model["annotations"]["chat_messages"]) == 3


def test_claude_event_hash_excludes_native_identifier_drift(tmp_path: Path) -> None:
    original = tmp_path / "original.jsonl"
    drifted = tmp_path / "drifted.jsonl"
    records = _rollout()
    _write_jsonl(original, records)
    changed = deepcopy(records)
    changed[1]["uuid"] = "user-reidentified"
    _write_jsonl(drifted, changed)
    normalizer = ClaudePromptSourceRawNormalizer()

    original_event = normalizer.normalize(
        original,
        source_id="original",
        raw_model_version=CLAUDE_PROMPT_SOURCE_RAW_MODEL_VERSION,
    ).events[0]
    changed_event = normalizer.normalize(
        drifted,
        source_id="drifted",
        raw_model_version=CLAUDE_PROMPT_SOURCE_RAW_MODEL_VERSION,
    ).events[0]

    assert original_event["event_address"] != changed_event["event_address"]
    assert original_event["event_hash"] == changed_event["event_hash"]


def test_claude_versioner_rejects_unrecognized_or_malformed_artifacts(
    tmp_path: Path,
) -> None:
    missing_session = tmp_path / "missing-session.jsonl"
    malformed = tmp_path / "malformed.jsonl"
    _write_jsonl(
        missing_session,
        [{"type": "user", "timestamp": "2026-08-15T00:00:00Z", "message": {}}],
    )
    malformed.write_text("not-json\n", encoding="utf-8")

    versioner = ClaudeRawModelVersioner()
    assert versioner.version(missing_session) is None
    assert versioner.version(malformed) is None
