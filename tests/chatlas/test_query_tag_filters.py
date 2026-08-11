from __future__ import annotations

from pathlib import Path
from typing import Any

from agentos.chatlas.annotations import add_session_tag
from agentos.chatlas.query import row_matches_annotation_filters


def _row(identity_hash: str) -> dict[str, Any]:
    return {"identity_hash": identity_hash}


def test_no_filters_passes_through(tmp_path: Path) -> None:
    cache: dict[str, dict[str, dict[str, Any]]] = {}
    assert row_matches_annotation_filters(
        _row("ab12"),
        tags=None,
        without_tags=None,
        shard_cache=cache,
        chatlas_root=tmp_path,
    )


def test_tag_filter_matches_tagged_session(tmp_path: Path) -> None:
    add_session_tag("ab12", "work", chatlas_root=tmp_path)
    cache: dict[str, dict[str, dict[str, Any]]] = {}
    assert row_matches_annotation_filters(
        _row("ab12"),
        tags=("work",),
        without_tags=None,
        shard_cache=cache,
        chatlas_root=tmp_path,
    )


def test_tag_filter_excludes_untagged_session(tmp_path: Path) -> None:
    cache: dict[str, dict[str, dict[str, Any]]] = {}
    assert not row_matches_annotation_filters(
        _row("ab12"),
        tags=("work",),
        without_tags=None,
        shard_cache=cache,
        chatlas_root=tmp_path,
    )


def test_without_tag_excludes_tagged_session(tmp_path: Path) -> None:
    add_session_tag("ab12", "work", chatlas_root=tmp_path)
    cache: dict[str, dict[str, dict[str, Any]]] = {}
    assert not row_matches_annotation_filters(
        _row("ab12"),
        tags=None,
        without_tags=("work",),
        shard_cache=cache,
        chatlas_root=tmp_path,
    )


def test_without_tag_passes_untagged_session(tmp_path: Path) -> None:
    cache: dict[str, dict[str, dict[str, Any]]] = {}
    assert row_matches_annotation_filters(
        _row("ab12"),
        tags=None,
        without_tags=("work",),
        shard_cache=cache,
        chatlas_root=tmp_path,
    )


def test_without_tag_passes_session_with_other_tags(tmp_path: Path) -> None:
    add_session_tag("ab12", "personal", chatlas_root=tmp_path)
    cache: dict[str, dict[str, dict[str, Any]]] = {}
    assert row_matches_annotation_filters(
        _row("ab12"),
        tags=None,
        without_tags=("work",),
        shard_cache=cache,
        chatlas_root=tmp_path,
    )


def test_multi_without_tag_and_semantics(tmp_path: Path) -> None:
    add_session_tag("ab12", "alpha", chatlas_root=tmp_path)
    cache: dict[str, dict[str, dict[str, Any]]] = {}
    # excluded because it has alpha
    assert not row_matches_annotation_filters(
        _row("ab12"),
        tags=None,
        without_tags=("alpha", "beta"),
        shard_cache=cache,
        chatlas_root=tmp_path,
    )

    add_session_tag("cd34", "beta", chatlas_root=tmp_path)
    cache2: dict[str, dict[str, dict[str, Any]]] = {}
    assert not row_matches_annotation_filters(
        _row("cd34"),
        tags=None,
        without_tags=("alpha", "beta"),
        shard_cache=cache2,
        chatlas_root=tmp_path,
    )

    cache3: dict[str, dict[str, dict[str, Any]]] = {}
    assert row_matches_annotation_filters(
        _row("ef56"),
        tags=None,
        without_tags=("alpha", "beta"),
        shard_cache=cache3,
        chatlas_root=tmp_path,
    )


def test_combined_tag_and_without_tag(tmp_path: Path) -> None:
    add_session_tag("ab12", "wanted", chatlas_root=tmp_path)
    add_session_tag("ab12", "blocked", chatlas_root=tmp_path)
    add_session_tag("cd34", "wanted", chatlas_root=tmp_path)
    cache: dict[str, dict[str, dict[str, Any]]] = {}
    # ab12 has both → excluded by without
    assert not row_matches_annotation_filters(
        _row("ab12"),
        tags=("wanted",),
        without_tags=("blocked",),
        shard_cache=cache,
        chatlas_root=tmp_path,
    )
    cache2: dict[str, dict[str, dict[str, Any]]] = {}
    # cd34 has wanted, lacks blocked → kept
    assert row_matches_annotation_filters(
        _row("cd34"),
        tags=("wanted",),
        without_tags=("blocked",),
        shard_cache=cache2,
        chatlas_root=tmp_path,
    )
