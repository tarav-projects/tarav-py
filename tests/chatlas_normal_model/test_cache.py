from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from tarav._core.errors import CliError
from tarav.chatlas import normal_model_cache as cache
from tarav.chatlas.normal_model import ChatlasNormalModel
from tarav.runtime import create_runtime


def _row(source: Path) -> dict[str, object]:
    return {
        "provider": "codex",
        "session_id": "session-one",
        "identity_hash": "f" * 64,
        "backing_artifacts": [{"role": "transcript", "path": str(source)}],
    }


def _model(source: Path) -> dict[str, object]:
    return {
        "type": "Chatlas.Normal.Model",
        "schema_version": 1,
        "metadata": {"commit": "1" * 40},
        "session": {
            "provider": "codex",
            "session_id": "session-one",
            "identity_hash": "f" * 64,
        },
        "sources": [
            {
                "source_id": "source-one",
                "path": str(source),
                "role": "transcript",
                "raw_model_version": "codex.rollout.test",
                "status": "recognized",
            }
        ],
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
        "counts": {
            "events": 1,
            "messages": 1,
            "turns": 1,
            "loaded_contexts": 1,
        },
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
        "main.json",
        "cache.json",
        "events.jsonl",
        "messages.jsonl",
        "turns.jsonl",
        "loaded-contexts.jsonl",
    }
    metadata = json.loads((path / "cache.json").read_text(encoding="utf-8"))
    assert metadata["schema"] == "tarav.chatlas.normal-model-cache"
    assert metadata["schema_version"] == 4
    assert json.loads((path / "main.json").read_text(encoding="utf-8")) == {
        key: model[key]
        for key in ("type", "schema_version", "metadata", "session", "sources", "counts")
    }
    assert isinstance(reader, ChatlasNormalModel)
    assert create_runtime().load(path).to_json() == reader.to_json()
    assert list(reader.iter_events()) == model["events"]
    assert list(reader.iter_messages()) == model["messages"]
    assert list(reader.iter_turns()) == model["turns"]
    assert list(reader.iter_loaded_contexts()) == model["loaded_contexts"]
    assert reader.project() == {
        **reader.model_header(),
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


def test_normal_model_remains_loadable_without_valid_cache_metadata(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "source.jsonl"
    source.write_text("one\n", encoding="utf-8")
    row = _row(source)
    model = _model(source)
    root = tmp_path / "chatlas"
    monkeypatch.setattr(cache, "build_normal_model_from_row", lambda *_args, **_kwargs: model)
    monkeypatch.setattr(cache, "normal_model_producer_commit", lambda: "1" * 40)

    cache.materialize_normal_model_cache_from_row(row, chatlas_root=root)
    path = cache.normal_model_cache_path(row, chatlas_root=root)
    (path / "cache.json").write_text("{}\n", encoding="utf-8")

    assert cache.normal_model_cache_status_from_row(row, chatlas_root=root) == "STALE"
    assert ChatlasNormalModel.open(path).load_normal_model() == model
    assert create_runtime().load(path).to_json()["type"] == "Chatlas.Normal.Model"


def test_raw_diagnostics_are_not_persisted_in_the_semantic_directory(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.jsonl"
    model = {**_model(source), "raw": [{"value": "native"}]}

    with pytest.raises(CliError, match="raw diagnostic fragments"):
        ChatlasNormalModel.materialize(tmp_path / "model", model)
