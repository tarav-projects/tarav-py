from __future__ import annotations

from pathlib import Path

import pytest

from tarav.chatlas.annotations import (
    ANNOTATIONS_ROOT,
    _read_shard,
    _shard_path,
    add_session_tag,
    list_all_tags,
    read_session_annotations,
    remove_session_tag,
    write_session_annotations,
)


def test_shard_path_uses_first_two_chars(tmp_path: Path) -> None:
    shard = _shard_path("ab12cd34ef", chatlas_root=tmp_path)
    assert shard == tmp_path / ANNOTATIONS_ROOT / "ab.jsonl"


def test_shard_path_lowercases_prefix(tmp_path: Path) -> None:
    shard = _shard_path("AB12cd", chatlas_root=tmp_path)
    assert shard.name == "ab.jsonl"


def test_shard_path_rejects_empty_identity_hash(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        _shard_path("", chatlas_root=tmp_path)


def test_read_missing_returns_empty(tmp_path: Path) -> None:
    assert read_session_annotations("ab12", chatlas_root=tmp_path) == {}


def test_write_and_read_round_trip(tmp_path: Path) -> None:
    write_session_annotations(
        "ab12cd",
        {"tags": ["work"], "note": "hi"},
        chatlas_root=tmp_path,
    )
    assert read_session_annotations("ab12cd", chatlas_root=tmp_path) == {
        "tags": ["work"],
        "note": "hi",
    }


def test_write_session_annotations_full_overwrite(tmp_path: Path) -> None:
    write_session_annotations(
        "ab12",
        {"tags": ["a", "b"], "note": "x"},
        chatlas_root=tmp_path,
    )
    write_session_annotations(
        "ab12",
        {"tags": ["c"]},
        chatlas_root=tmp_path,
    )
    assert read_session_annotations("ab12", chatlas_root=tmp_path) == {"tags": ["c"]}


def test_add_tag_idempotent(tmp_path: Path) -> None:
    new_tags, changed = add_session_tag("ab12", "work", chatlas_root=tmp_path)
    assert new_tags == ["work"]
    assert changed is True

    new_tags, changed = add_session_tag("ab12", "work", chatlas_root=tmp_path)
    assert new_tags == ["work"]
    assert changed is False


def test_add_multiple_tags_preserves_order(tmp_path: Path) -> None:
    add_session_tag("ab12", "alpha", chatlas_root=tmp_path)
    add_session_tag("ab12", "beta", chatlas_root=tmp_path)
    add_session_tag("ab12", "gamma", chatlas_root=tmp_path)
    annotations = read_session_annotations("ab12", chatlas_root=tmp_path)
    assert annotations["tags"] == ["alpha", "beta", "gamma"]


def test_remove_tag_idempotent(tmp_path: Path) -> None:
    add_session_tag("ab12", "work", chatlas_root=tmp_path)
    new_tags, changed = remove_session_tag("ab12", "work", chatlas_root=tmp_path)
    assert new_tags == []
    assert changed is True

    new_tags, changed = remove_session_tag("ab12", "work", chatlas_root=tmp_path)
    assert new_tags == []
    assert changed is False


def test_remove_tag_keeps_session_line(tmp_path: Path) -> None:
    add_session_tag("ab12", "work", chatlas_root=tmp_path)
    remove_session_tag("ab12", "work", chatlas_root=tmp_path)
    annotations = read_session_annotations("ab12", chatlas_root=tmp_path)
    assert annotations == {"tags": []}


def test_remove_tag_for_missing_session_is_noop(tmp_path: Path) -> None:
    new_tags, changed = remove_session_tag("ab12", "work", chatlas_root=tmp_path)
    assert new_tags == []
    assert changed is False


def test_multiple_sessions_in_same_shard(tmp_path: Path) -> None:
    add_session_tag("ab11", "alpha", chatlas_root=tmp_path)
    add_session_tag("ab22", "beta", chatlas_root=tmp_path)
    add_session_tag("ab33", "gamma", chatlas_root=tmp_path)
    shard = _shard_path("ab00", chatlas_root=tmp_path)
    sessions = _read_shard(shard)
    assert sessions == {
        "ab11": {"tags": ["alpha"]},
        "ab22": {"tags": ["beta"]},
        "ab33": {"tags": ["gamma"]},
    }


def test_different_shards_for_different_prefixes(tmp_path: Path) -> None:
    add_session_tag("ab11", "alpha", chatlas_root=tmp_path)
    add_session_tag("cd22", "beta", chatlas_root=tmp_path)
    assert read_session_annotations("ab11", chatlas_root=tmp_path) == {"tags": ["alpha"]}
    assert read_session_annotations("cd22", chatlas_root=tmp_path) == {"tags": ["beta"]}
    assert (tmp_path / ANNOTATIONS_ROOT / "ab.jsonl").is_file()
    assert (tmp_path / ANNOTATIONS_ROOT / "cd.jsonl").is_file()


def test_atomic_write_leaves_no_tmp(tmp_path: Path) -> None:
    add_session_tag("ab12", "work", chatlas_root=tmp_path)
    shard_dir = tmp_path / ANNOTATIONS_ROOT
    leftover = list(shard_dir.glob("*.tmp"))
    assert leftover == []


def test_empty_tag_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        add_session_tag("ab12", "", chatlas_root=tmp_path)
    with pytest.raises(ValueError):
        remove_session_tag("ab12", "", chatlas_root=tmp_path)


def test_no_shard_created_until_first_write(tmp_path: Path) -> None:
    read_session_annotations("ab12", chatlas_root=tmp_path)
    assert not (tmp_path / ANNOTATIONS_ROOT).exists()


def test_list_all_tags_empty_root_returns_empty(tmp_path: Path) -> None:
    assert list_all_tags(chatlas_root=tmp_path) == []


def test_list_all_tags_counts_across_shards(tmp_path: Path) -> None:
    add_session_tag("ab11", "alpha", chatlas_root=tmp_path)
    add_session_tag("ab11", "beta", chatlas_root=tmp_path)
    add_session_tag("ab22", "alpha", chatlas_root=tmp_path)
    add_session_tag("cd33", "alpha", chatlas_root=tmp_path)
    add_session_tag("cd44", "beta", chatlas_root=tmp_path)
    assert list_all_tags(chatlas_root=tmp_path) == [
        {"tag": "alpha", "count": 3},
        {"tag": "beta", "count": 2},
    ]


def test_list_all_tags_orders_by_count_then_tag(tmp_path: Path) -> None:
    add_session_tag("ab11", "zeta", chatlas_root=tmp_path)
    add_session_tag("ab22", "zeta", chatlas_root=tmp_path)
    add_session_tag("ab33", "alpha", chatlas_root=tmp_path)
    add_session_tag("ab44", "alpha", chatlas_root=tmp_path)
    # equal counts -> tag ascending
    assert list_all_tags(chatlas_root=tmp_path) == [
        {"tag": "alpha", "count": 2},
        {"tag": "zeta", "count": 2},
    ]


def test_list_all_tags_counts_session_once_per_tag(tmp_path: Path) -> None:
    write_session_annotations(
        "ab11",
        {"tags": ["dup", "dup", "other"]},
        chatlas_root=tmp_path,
    )
    assert list_all_tags(chatlas_root=tmp_path) == [
        {"tag": "dup", "count": 1},
        {"tag": "other", "count": 1},
    ]


def test_list_all_tags_ignores_malformed_lines(tmp_path: Path) -> None:
    add_session_tag("ab11", "alpha", chatlas_root=tmp_path)
    shard = _shard_path("ab11", chatlas_root=tmp_path)
    with shard.open("a", encoding="utf-8") as handle:
        handle.write("not json\n")
        handle.write("[1, 2, 3]\n")
    assert list_all_tags(chatlas_root=tmp_path) == [{"tag": "alpha", "count": 1}]
