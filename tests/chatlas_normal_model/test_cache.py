from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from tarav.l1.chatlas import normal_model_cache as cache
from tarav.l1.chatlas.index_writer import raw_version
from tarav.l1.chatlas.normal_model import pipeline


def _row(source: Path) -> dict[str, object]:
    row: dict[str, object] = {
        "provider": "codex",
        "session_id": "session-one",
        "identity_hash": "f" * 64,
        "backing_artifacts": [{"role": "transcript", "path": str(source)}],
    }
    row["raw_version"] = raw_version(row)
    return row


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


@pytest.fixture
def session(monkeypatch, tmp_path: Path):
    """A transcript, its index row, and a counted fake normalizer."""
    source = tmp_path / "source.jsonl"
    source.write_text("one\n", encoding="utf-8")
    model = _model(source)
    builds: list[int] = []

    def build(selected, *, include_raw=False):
        builds.append(1)
        return deepcopy(model)

    monkeypatch.setattr(cache, "build_normal_model_from_row", build)
    return source, model, builds, tmp_path / "chatlas"


def test_a_build_caches_every_part_with_the_raw_version_it_used(session) -> None:
    source, model, builds, root = session
    row = _row(source)
    store = cache.NormalModelCache(row, chatlas_root=root)

    assert {part.present for part in store.parts().values()} == {False}
    store.build()

    metadata = json.loads((store.path / "cache.json").read_text(encoding="utf-8"))
    assert metadata["parts"] == {
        "main": row["raw_version"],
        "events": row["raw_version"],
        "messages": row["raw_version"],
        "turns": row["raw_version"],
        "loaded_contexts": row["raw_version"],
    }
    assert all(part.fresh for part in store.parts().values())
    reader = cache.provide_normal_model_reader_from_row(row, chatlas_root=root)
    assert list(reader.iter_messages()) == model["messages"]
    assert len(builds) == 1


def test_code_changes_do_not_make_the_cache_stale(monkeypatch, session) -> None:
    source, _model, builds, root = session
    row = _row(source)
    cache.provide_normal_model_reader_from_row(row, chatlas_root=root)
    monkeypatch.setattr(pipeline, "normal_model_producer_commit", lambda: "9" * 40)

    cache.provide_normal_model_reader_from_row(row, chatlas_root=root)

    assert len(builds) == 1


def test_changed_raw_data_leaves_stale_parts_readable(session) -> None:
    source, model, builds, root = session
    cache.NormalModelCache(_row(source), chatlas_root=root).build()
    source.write_text("one\ntwo\n", encoding="utf-8")
    row = _row(source)
    store = cache.NormalModelCache(row, chatlas_root=root)

    turns = store.parts()["turns"]
    assert turns.present and turns.stale and not turns.fresh
    assert turns.current_raw_version == row["raw_version"] != turns.raw_version
    assert list(store.model().iter_turns()) == model["turns"]
    cache.provide_normal_model_reader_from_row(row, chatlas_root=root)
    assert len(builds) == 2
    assert store.fresh()


def test_the_safe_path_needs_only_the_requested_parts(session) -> None:
    source, model, builds, root = session
    row = _row(source)
    store = cache.NormalModelCache(row, chatlas_root=root)
    store.build()
    (store.path / "events.jsonl").unlink()

    assert store.parts()["events"].present is False
    reader = cache.provide_normal_model_reader_from_row(
        row, chatlas_root=root, parts=("turns", "messages")
    )
    assert list(reader.iter_turns()) == model["turns"]
    assert len(builds) == 1
    cache.provide_normal_model_reader_from_row(row, chatlas_root=root)
    assert len(builds) == 2
    assert store.parts()["events"].fresh


def test_a_row_without_a_raw_version_has_no_fresh_part(session) -> None:
    source, _model, builds, root = session
    row = _row(source)
    cache.NormalModelCache(row, chatlas_root=root).build()
    unversioned = {key: value for key, value in row.items() if key != "raw_version"}
    store = cache.NormalModelCache(unversioned, chatlas_root=root)

    assert {part.stale for part in store.parts().values()} == {True}
    with pytest.raises(ValueError, match="unknown Normal Model parts: text"):
        store.fresh(("text",))
