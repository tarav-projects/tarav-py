from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from tarav.chatlas.normal_model import cache


def _row(source: Path) -> dict[str, object]:
    return {
        "provider": "codex",
        "session_id": "session-one",
        "identity_hash": "f" * 64,
        "backing_artifacts": [{"role": "transcript", "path": str(source)}],
    }


def _model(source: Path) -> dict[str, object]:
    return {
        "schema": "tarav.chatlas.normal-model",
        "schema_version": 2,
        "metadata": {"commit": "1" * 40},
        "session": {
            "provider": "codex",
            "session_id": "session-one",
            "identity_hash": "f" * 64,
        },
        "sources": [{"source_id": "source-one", "path": str(source)}],
        "events": [
            {
                "type": "User.Event",
                "event_address": "1" * 64,
                "event_hash": "2" * 64,
                "started_at": "2026-09-20T00:00:00Z",
                "origin": "user",
                "observations": [
                    {
                        "observed_at": "2026-09-20T00:00:00Z",
                        "source_ref": {
                            "source_id": "source-one",
                            "record_index": 1,
                            "line": 1,
                        },
                    }
                ],
                "opaque_payload_hash": "3" * 64,
            }
        ],
        "messages": [
            {
                "type": "Chat.Message",
                "message_address": "4" * 64,
                "message_hash": "5" * 64,
                "side": "user",
                "text": "hello",
                "event_refs": [
                    {"event_address": "1" * 64, "event_hash": "2" * 64}
                ],
            }
        ],
        "turns": [
            {
                "type": "Chat.Turn",
                "turn_address": "6" * 64,
                "turn_hash": "7" * 64,
                "side": "user",
                "event_refs": [
                    {"event_address": "1" * 64, "event_hash": "2" * 64}
                ],
                "message_refs": [
                    {"message_address": "4" * 64, "message_hash": "5" * 64}
                ],
            }
        ],
        "loaded_contexts": [
            {
                "type": "Agent.Loaded.Context",
                "agent_event_ref": {
                    "event_address": "1" * 64,
                    "event_hash": "2" * 64,
                },
                "event_refs": [
                    {"event_address": "1" * 64, "event_hash": "2" * 64}
                ],
            }
        ],
    }


def test_cache_is_one_streamable_directory_per_normal_model(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "source.jsonl"
    source.write_text("one\n", encoding="utf-8")
    row = _row(source)
    model = _model(source)
    root = tmp_path / "chatlas"
    monkeypatch.setattr(
        cache,
        "build_normal_model_from_row",
        lambda selected, *, include_raw=False: deepcopy(model)
        if selected is row and not include_raw
        else None,
    )
    monkeypatch.setattr(cache, "normal_model_producer_commit", lambda: "1" * 40)

    assert cache.normal_model_cache_status_from_row(row, chatlas_root=root) == "MISSING"
    reader = cache.materialize_normal_model_cache_from_row(row, chatlas_root=root)
    path = cache.normal_model_cache_path(row, chatlas_root=root)

    assert path == root / "normal-model" / ("f" * 64)
    assert path.is_dir()
    assert {child.name for child in path.iterdir()} == {
        "metadata.json",
        "events.jsonl",
        "messages.jsonl",
        "turns.jsonl",
        "loaded-contexts.jsonl",
    }
    metadata = json.loads((path / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["schema"] == "tarav.chatlas.normal-model-cache"
    assert metadata["schema_version"] == 3
    assert metadata["model"] == {
        key: model[key]
        for key in ("schema", "schema_version", "metadata", "session", "sources")
    }
    assert metadata["counts"] == {
        "events": 1,
        "messages": 1,
        "turns": 1,
        "loaded_contexts": 1,
    }
    assert list(reader.iter_events()) == model["events"]
    assert list(reader.iter_messages()) == model["messages"]
    assert list(reader.iter_turns()) == model["turns"]
    assert list(reader.iter_loaded_contexts()) == model["loaded_contexts"]
    assert reader.project() == {
        **metadata["model"],
        "events": model["events"],
    }
    assert reader.project(
        include_messages=True,
        include_turns=True,
        include_loaded_contexts=True,
    ) == model
    assert cache.normal_model_cache_status_from_row(row, chatlas_root=root) == "FRESH"
    assert cache.read_normal_model_cache_from_row(row, chatlas_root=root) == model

    source.write_text("changed\n", encoding="utf-8")
    assert cache.normal_model_cache_status_from_row(row, chatlas_root=root) == "STALE"
