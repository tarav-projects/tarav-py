from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from tarav._core.errors import CliError
from tarav.chatlas2 import cache
from tarav.chatlas2.message_ref import compute_chat_message_hash
from tarav.chatlas2.turn_ref import compute_chat_turn_hash


def _row(source: Path) -> dict[str, object]:
    return {
        "provider": "codex",
        "session_id": "019ccafa-7835-7fc3-ac17-0e0a0f675c22",
        "identity_hash": "f" * 64,
        "backing_artifacts": [
            {"role": "transcript", "path": str(source)},
        ],
    }


def _model(source: Path | None = None) -> dict[str, object]:
    event = {
        "class": "User.Event",
        "origin": "user",
        "event_address": "a" * 64,
        "event_hash": "b" * 64,
        "started_at": "2026-08-16T00:00:01Z",
        "observations": [
            {
                "observed_at": "2026-08-16T00:00:01Z",
                "source_ref": {
                    "source_id": "source-one",
                    "record_index": 1,
                    "line": 1,
                },
            }
        ],
        "opaque_payload_hash": "e" * 64,
        "content": {"text": "first question"},
    }
    message = {
        "class": "Chat.Message",
        "message_address": "c" * 64,
        "side": "user",
        "text": "first question",
        "event_refs": [
            {
                "event_address": event["event_address"],
                "event_hash": event["event_hash"],
            }
        ],
    }
    message["message_hash"] = compute_chat_message_hash(message)
    turn = {
        "class": "Chat.Turn",
        "turn_address": "f" * 64,
        "side": "user",
        "event_refs": deepcopy(message["event_refs"]),
        "message_refs": [
            {
                "message_address": message["message_address"],
                "message_hash": message["message_hash"],
            }
        ],
    }
    turn["turn_hash"] = compute_chat_turn_hash(
        turn,
        opaque_payload_hashes=[event["opaque_payload_hash"]],
    )
    return {
        "class": "tarav.chatlas2.normal_model",
        "schema_version": 6,
        "metadata": {"commit": "1" * 40},
        "session": {
            "provider": "codex",
            "session_id": "019ccafa-7835-7fc3-ac17-0e0a0f675c22",
            "identity_hash": "f" * 64,
        },
        "sources": [
            {
                "source_id": "source-one",
                "path": str(source or Path("/tmp/source.jsonl")),
                "role": "transcript",
                "raw_model_version": "codex.rollout.5f98",
                "status": "recognized",
            }
        ],
        "events": [event],
        "annotations": {
            "chat_messages": [message],
            "chat_turns": [turn],
            "agent_loaded_contexts": [],
        },
    }


def test_cache_materializes_compact_model_as_independent_streams(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.jsonl"
    source.write_text("one\n", encoding="utf-8")
    row = _row(source)
    model = _model()
    calls: list[bool] = []

    def build(_row: dict[str, object], *, include_raw: bool = False):
        calls.append(include_raw)
        return deepcopy(model)

    monkeypatch.setattr(cache, "build_normal_model_from_row", build)
    reader = cache.materialize_normal_model_cache_from_row(
        row,
        chatlas_root=tmp_path / "chatlas",
    )

    assert calls == [False]
    assert {path.name for path in reader.path.iterdir()} == {
        "metadata.json",
        "events.jsonl",
        "chat-messages.jsonl",
        "chat-turns.jsonl",
        "agent-loaded-contexts.jsonl",
    }
    assert reader.metadata["class"] == "tarav.chatlas2.normal_model_cache"
    assert reader.metadata["schema_version"] == 2
    assert reader.metadata["model"]["schema_version"] == 6
    assert reader.metadata["counts"] == {
        "events": 1,
        "chat_messages": 1,
        "chat_turns": 1,
        "agent_loaded_contexts": 0,
    }
    assert list(reader.iter_events()) == model["events"]
    assert list(reader.iter_chat_message_records()) == [
        {
            "message": model["annotations"]["chat_messages"][0],
            "at": "2026-08-16T00:00:01Z",
        }
    ]
    assert list(reader.iter_agent_loaded_contexts()) == []
    assert list(reader.iter_chat_turns()) == model["annotations"]["chat_turns"]
    assert reader.load_normal_model() == model
    assert (
        cache.normal_model_cache_status_from_row(
            row, chatlas_root=tmp_path / "chatlas"
        )["standing"]
        == "FRESH"
    )


def test_cache_status_detects_missing_stale_and_incomplete_materialization(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.jsonl"
    source.write_text("one\n", encoding="utf-8")
    row = _row(source)
    root = tmp_path / "chatlas"
    monkeypatch.setattr(
        cache,
        "build_normal_model_from_row",
        lambda _row, *, include_raw=False: deepcopy(_model()),
    )

    assert (
        cache.normal_model_cache_status_from_row(row, chatlas_root=root)["standing"]
        == "MISSING"
    )
    with pytest.raises(CliError, match="not fresh"):
        cache.open_normal_model_cache_from_row(row, chatlas_root=root)

    reader = cache.materialize_normal_model_cache_from_row(row, chatlas_root=root)
    source.write_text("two and changed\n", encoding="utf-8")
    assert (
        cache.normal_model_cache_status_from_row(row, chatlas_root=root)["standing"]
        == "STALE"
    )

    source.write_text("one\n", encoding="utf-8")
    reader.path.joinpath("events.jsonl").unlink()
    assert (
        cache.normal_model_cache_status_from_row(row, chatlas_root=root)["standing"]
        == "STALE"
    )


def test_cached_message_iteration_filters_and_stops_at_limit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.jsonl"
    source.write_text("one\n", encoding="utf-8")
    model = _model()
    second = deepcopy(model["annotations"]["chat_messages"][0])
    second["message_address"] = "d" * 64
    second["side"] = "agent"
    second["text"] = "first answer"
    second["message_hash"] = compute_chat_message_hash(second)
    model["annotations"]["chat_messages"].append(second)
    monkeypatch.setattr(
        cache,
        "build_normal_model_from_row",
        lambda _row, *, include_raw=False: deepcopy(model),
    )
    reader = cache.materialize_normal_model_cache_from_row(
        _row(source), chatlas_root=tmp_path / "chatlas"
    )

    assert [
        record["message"]["text"]
        for record in reader.iter_chat_message_records(text="first", limit=1)
    ] == ["first question"]
    assert [
        record["message"]["text"]
        for record in reader.iter_chat_message_records(side="agent")
    ] == ["first answer"]
    with pytest.raises(ValueError, match="non-negative"):
        list(reader.iter_chat_message_records(limit=-1))


def test_cached_message_scan_verifies_candidates_before_counting_limit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.jsonl"
    source.write_text("one\n", encoding="utf-8")
    monkeypatch.setattr(
        cache,
        "build_normal_model_from_row",
        lambda _row, *, include_raw=False: deepcopy(_model()),
    )
    reader = cache.materialize_normal_model_cache_from_row(
        _row(source), chatlas_root=tmp_path / "chatlas"
    )
    target = reader.path / "chat-messages.jsonl"
    target.write_text(
        '{"noise":"needle","message":{"side":"user","text":"miss"}}\n'
        "not-json\n"
        + target.read_text(encoding="utf-8").replace(
            '"first question"', '"needle first question"'
        ),
        encoding="utf-8",
    )

    records = list(
        reader.iter_chat_message_records(text="needle", exact=False, limit=1)
    )
    assert [record["message"]["text"] for record in records] == [
        "needle first question"
    ]


def test_cached_message_scan_handles_json_escaped_text(tmp_path: Path) -> None:
    path = tmp_path / "cache"
    path.mkdir()
    reader = cache.NormalModelCacheReader(path=path, metadata={})
    (path / "chat-messages.jsonl").write_text(
        '{"message":{"side":"user","text":"line\\n\\"quoted\\" \\\\ café"}}\n',
        encoding="utf-8",
    )

    records = list(
        reader.iter_chat_message_records(text='line\n"quoted" \\ café', exact=True)
    )
    assert records[0]["message"]["text"] == 'line\n"quoted" \\ café'


def test_cached_message_scan_falls_back_when_text_has_no_safe_literal(
    tmp_path: Path,
) -> None:
    path = tmp_path / "cache"
    path.mkdir()
    reader = cache.NormalModelCacheReader(path=path, metadata={})
    (path / "chat-messages.jsonl").write_text(
        '{"message":{"side":"user","text":"\\ud800"}}\n',
        encoding="utf-8",
    )

    records = list(reader.iter_chat_message_records(text="\ud800", exact=True))
    assert records[0]["message"]["text"] == "\ud800"


def test_turn_lookup_and_hydration_load_only_selected_members(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.jsonl"
    native = {"type": "response_item", "payload": {"opaque": [1, 2, 3]}}
    source.write_text(json.dumps(native) + "\n", encoding="utf-8")
    model = _model(source)
    monkeypatch.setattr(
        cache,
        "build_normal_model_from_row",
        lambda _row, *, include_raw=False: deepcopy(model),
    )
    reader = cache.materialize_normal_model_cache_from_row(
        _row(source), chatlas_root=tmp_path / "chatlas"
    )

    turn = reader.find_chat_turn(
        message_address=model["annotations"]["chat_messages"][0]["message_address"]
    )
    assert turn == model["annotations"]["chat_turns"][0]
    hydrated = reader.hydrate_chat_turn(turn)

    assert hydrated["turn"] == turn
    assert hydrated["messages"][0]["message"]["text"] == "first question"
    assert hydrated["events"][0]["event"] == model["events"][0]
    assert hydrated["events"][0]["raw_observations"][0]["value"] == native


def test_cache_rejects_raw_attached_model(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.jsonl"
    source.write_text("one\n", encoding="utf-8")
    model = _model()
    model["raw"] = [{"value": "native"}]
    monkeypatch.setattr(
        cache,
        "build_normal_model_from_row",
        lambda _row, *, include_raw=False: deepcopy(model),
    )

    with pytest.raises(CliError, match="raw-attached"):
        cache.materialize_normal_model_cache_from_row(
            _row(source), chatlas_root=tmp_path / "chatlas"
        )
