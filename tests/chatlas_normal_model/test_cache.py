from __future__ import annotations

from copy import deepcopy
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
        "class": "tarav.chatlas.normal_model",
        "schema_version": 1,
        "metadata": {"commit": "1" * 40},
        "session": {
            "provider": "codex",
            "session_id": "session-one",
            "identity_hash": "f" * 64,
        },
        "sources": [{"source_id": "source-one", "path": str(source)}],
        "events": [],
        "messages": [],
        "turns": [],
        "loaded_contexts": [],
    }


def test_cache_is_one_rebuildable_normal_model_file(monkeypatch, tmp_path: Path) -> None:
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
    assert cache.materialize_normal_model_cache_from_row(row, chatlas_root=root) == model
    path = cache.normal_model_cache_path(row, chatlas_root=root)
    assert path.is_file()
    assert cache.normal_model_cache_status_from_row(row, chatlas_root=root) == "FRESH"
    assert cache.read_normal_model_cache_from_row(row, chatlas_root=root) == model

    source.write_text("changed\n", encoding="utf-8")
    assert cache.normal_model_cache_status_from_row(row, chatlas_root=root) == "STALE"
