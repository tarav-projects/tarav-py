from __future__ import annotations

import json
from pathlib import Path

import pytest

from tarav.chatlas.index_query import chatlas_index_query
from tarav.chatlas.index_store import ChatlasSessionIndexCache


def _write_partition(
    root: Path,
    *,
    provider: str,
    shard: str,
    rows: list[dict[str, object]],
) -> Path:
    path = root / "index" / "sessions" / provider / shard / "sessions.index.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )
    return path


def test_identity_query_reads_matching_shards_once_per_runtime_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_partition(
        tmp_path,
        provider="codex",
        shard="ab",
        rows=[{"provider": "codex", "identity_hash": "ab-codex"}],
    )
    _write_partition(
        tmp_path,
        provider="claude-code",
        shard="ab",
        rows=[{"provider": "claude-code", "identity_hash": "ab-claude"}],
    )
    _write_partition(
        tmp_path,
        provider="codex",
        shard="cd",
        rows=[{"provider": "codex", "identity_hash": "cd-other"}],
    )
    original_read = Path.read_text
    reads: list[Path] = []

    def counted_read(path: Path, *args, **kwargs):
        if path.name == "sessions.index.jsonl":
            reads.append(path)
        return original_read(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counted_read)
    cache = ChatlasSessionIndexCache(capacity=8)

    first = chatlas_index_query(
        identity_hash="ab-",
        chatlas_root=tmp_path,
        index_cache=cache,
    )
    second = chatlas_index_query(
        identity_hash="ab-",
        chatlas_root=tmp_path,
        index_cache=cache,
    )

    assert {row["identity_hash"] for row in first["rows"]} == {
        "ab-codex",
        "ab-claude",
    }
    assert second["rows"] == first["rows"]
    assert first["partition_count"] == 2
    assert len(reads) == 2


def test_short_identity_prefix_preserves_full_prefix_query_semantics(
    tmp_path: Path,
) -> None:
    _write_partition(
        tmp_path,
        provider="codex",
        shard="ab",
        rows=[{"provider": "codex", "identity_hash": "ab-one"}],
    )
    _write_partition(
        tmp_path,
        provider="codex",
        shard="ac",
        rows=[{"provider": "codex", "identity_hash": "ac-two"}],
    )
    _write_partition(
        tmp_path,
        provider="codex",
        shard="ba",
        rows=[{"provider": "codex", "identity_hash": "ba-other"}],
    )

    payload = chatlas_index_query(identity_hash="a", chatlas_root=tmp_path)

    assert {row["identity_hash"] for row in payload["rows"]} == {
        "ab-one",
        "ac-two",
    }
    assert payload["partition_count"] == 3


def test_index_partition_cache_has_bounded_capacity(tmp_path: Path) -> None:
    cache = ChatlasSessionIndexCache(capacity=1)
    _write_partition(
        tmp_path,
        provider="codex",
        shard="ab",
        rows=[{"provider": "codex", "identity_hash": "ab-one"}],
    )
    _write_partition(
        tmp_path,
        provider="codex",
        shard="cd",
        rows=[{"provider": "codex", "identity_hash": "cd-two"}],
    )

    chatlas_index_query(
        identity_hash="ab-one",
        chatlas_root=tmp_path,
        index_cache=cache,
    )
    chatlas_index_query(
        identity_hash="cd-two",
        chatlas_root=tmp_path,
        index_cache=cache,
    )

    assert cache.partition_count == 1
