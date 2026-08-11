# $kw: ^chatlas-annotations --supp static cleanup authorized ^c20260730-34u
from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from agentos._core.persistence import atomic_write_text
from agentos.chatlas.paths import default_chatlas_root

ANNOTATIONS_ROOT = Path("annotations")


def read_session_annotations(
    identity_hash: str,
    *,
    chatlas_root: Path | None = None,
) -> dict[str, Any]:
    shard = _shard_path(identity_hash, chatlas_root)
    sessions = _read_shard(shard)
    return dict(sessions.get(identity_hash, {}))


def write_session_annotations(
    identity_hash: str,
    annotations: dict[str, Any],
    *,
    chatlas_root: Path | None = None,
) -> None:
    shard = _shard_path(identity_hash, chatlas_root)
    sessions = _read_shard(shard)
    sessions[identity_hash] = dict(annotations)
    _write_shard_atomic(shard, sessions)


def add_session_tag(
    identity_hash: str,
    tag: str,
    *,
    chatlas_root: Path | None = None,
) -> tuple[list[str], bool]:
    return _mutate_session_tags(
        identity_hash,
        tag,
        lambda tags: tags if tag in tags else [*tags, tag],
        chatlas_root=chatlas_root,
    )


def read_shard_annotations(
    prefix: str,
    *,
    chatlas_root: Path | None = None,
) -> dict[str, dict[str, Any]]:
    return _read_shard(_shard_path_for_prefix(prefix, chatlas_root))





def remove_session_tag(
    identity_hash: str,
    tag: str,
    *,
    chatlas_root: Path | None = None,
) -> tuple[list[str], bool]:
    return _mutate_session_tags(
        identity_hash,
        tag,
        lambda tags: [existing for existing in tags if existing != tag],
        chatlas_root=chatlas_root,
    )


def _mutate_session_tags(
    identity_hash: str,
    tag: str,
    transform: Callable[[list[str]], list[str]],
    *,
    chatlas_root: Path | None = None,
) -> tuple[list[str], bool]:
    if not tag:
        raise ValueError("tag must be a non-empty string")
    shard = _shard_path(identity_hash, chatlas_root)
    sessions = _read_shard(shard)
    current = sessions.get(identity_hash, {})
    tags = _coerce_tag_list(current.get("tags"))
    new_tags = transform(tags)
    if new_tags == tags:
        return tags, False
    sessions[identity_hash] = {**current, "tags": new_tags}
    _write_shard_atomic(shard, sessions)
    return new_tags, True


def list_all_tags(
    *,
    chatlas_root: Path | None = None,
) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    annotations_dir = _annotations_dir(chatlas_root)
    if not annotations_dir.is_dir():
        return []
    for shard in sorted(annotations_dir.glob("*.jsonl")):
        sessions = _read_shard(shard)
        for session_annotations in sessions.values():
            for tag in set(_coerce_tag_list(session_annotations.get("tags"))):
                counts[tag] = counts.get(tag, 0) + 1
    return [
        {"tag": tag, "count": count}
        for tag, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _annotations_dir(chatlas_root: Path | None) -> Path:
    root = (chatlas_root or default_chatlas_root()).expanduser().resolve()
    return root / ANNOTATIONS_ROOT


def _shard_path(identity_hash: str, chatlas_root: Path | None) -> Path:
    if not identity_hash:
        raise ValueError("identity_hash must be a non-empty string")
    return _shard_path_for_prefix(identity_hash[:2], chatlas_root)


def _shard_path_for_prefix(prefix: str, chatlas_root: Path | None) -> Path:
    return _annotations_dir(chatlas_root) / f"{prefix.lower()}.jsonl"


def _read_shard(shard_path: Path) -> dict[str, dict[str, Any]]:
    if not shard_path.is_file():
        return {}
    sessions: dict[str, dict[str, Any]] = {}
    for line in shard_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict):
            continue
        ih = entry.get("identity_hash")
        ann = entry.get("annotations")
        if isinstance(ih, str) and isinstance(ann, dict):
            sessions[ih] = ann
    return sessions


def _write_shard_atomic(shard_path: Path, sessions: dict[str, dict[str, Any]]) -> None:
    shard_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps(
            {"identity_hash": ih, "annotations": sessions[ih]},
            separators=(",", ":"),
            sort_keys=True,
        )
        for ih in sorted(sessions)
    ]
    text = "\n".join(lines) + ("\n" if lines else "")
    atomic_write_text(shard_path, text)


def _coerce_tag_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


__all__ = [
    "ANNOTATIONS_ROOT",
    "read_session_annotations",
    "write_session_annotations",
    "read_shard_annotations",
    "add_session_tag",
    "remove_session_tag",
    "list_all_tags",
]
