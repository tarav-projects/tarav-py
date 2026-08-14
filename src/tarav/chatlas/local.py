# $kw: --from Chatlas.Local
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tarav.chatlas.index_query import chatlas_index_row_matches, sort_chatlas_index_rows
from tarav.chatlas.index_store import load_chatlas_session_index_rows
from tarav.chatlas.normalization.session_model.filters import apply_chatlas_filters
from tarav.chatlas.views import load_chatlas_session_model

LOCAL_CHATLAS_MANIFEST = "manifest.json"
LOCAL_CHATLAS_MANIFEST_CLASS = "agentos_chatlas.local_manifest"
LOCAL_CHATLAS_SCHEMA_VERSION = 1


def chatlas_local_sync(
    *,
    project: Path | str,
    chatlas_root: Path | None = None,
) -> dict[str, object]:
    project_root = _project_root(project)
    local_root = _local_root(project_root)
    local_root.mkdir(parents=True, exist_ok=True)

    rows = attributed_chatlas_index_rows(project_root, chatlas_root=chatlas_root)
    written: list[dict[str, object]] = []
    skipped: list[dict[str, object]] = []
    for row in rows:
        identity_hash = _row_identity_hash(row)
        if identity_hash is None:
            skipped.append(_skip_payload(row, reason="indexed row has no identity_hash"))
            continue
        try:
            model = load_chatlas_session_model(row, chatlas_root=chatlas_root)
            filtered_model = apply_chatlas_filters(model, ("turns",))
            path = _local_session_path(local_root, identity_hash)
            _write_json(path, filtered_model)
            written.append(_session_payload(row, path=path, local_root=local_root))
        except Exception as exc:
            skipped.append(_skip_payload(row, reason=str(exc)))

    manifest = {
        "class": LOCAL_CHATLAS_MANIFEST_CLASS,
        "schema_version": LOCAL_CHATLAS_SCHEMA_VERSION,
        "project_root": str(project_root),
        "attribution_paths": [str(path) for path in project_attribution_paths(project_root)],
        "session_count": len(written),
        "sessions": written,
    }
    _write_json(local_root / LOCAL_CHATLAS_MANIFEST, manifest)

    present = _local_session_files(local_root)
    return {
        "status": "ok",
        "command": "chatlas local sync",
        "project_root": str(project_root),
        "local_root": str(local_root),
        "attribution_paths": [str(path) for path in project_attribution_paths(project_root)],
        "attributed_session_count": len(rows),
        "written_count": len(written),
        "skipped_count": len(skipped),
        "skipped": skipped,
        "total_local_session_count": len(present),
        "total_local_bytes": _total_local_bytes(local_root),
        "sessions": written,
    }


def chatlas_local_status(
    *,
    project: Path | str,
    chatlas_root: Path | None = None,
) -> dict[str, object]:
    project_root = _project_root(project)
    local_root = _local_root(project_root)
    rows = attributed_chatlas_index_rows(project_root, chatlas_root=chatlas_root)
    attributed = {
        identity_hash: row
        for row in rows
        if (identity_hash := _row_identity_hash(row)) is not None
    }
    present_files = _local_session_files(local_root)
    present = {path.stem: path for path in present_files}
    attributed_identities = set(attributed)
    present_identities = set(present)

    attributed_and_present = [
        _session_payload(attributed[identity_hash], path=present[identity_hash], local_root=local_root)
        for identity_hash in sorted(attributed_identities & present_identities)
    ]
    attributed_and_missing = [
        _session_payload(attributed[identity_hash])
        for identity_hash in sorted(attributed_identities - present_identities)
    ]
    present_but_not_attributed = [
        {
            "identity_hash": identity_hash,
            "file": _relative_path(present[identity_hash], local_root),
        }
        for identity_hash in sorted(present_identities - attributed_identities)
    ]

    return {
        "status": "ok",
        "command": "chatlas local status",
        "project_root": str(project_root),
        "local_root": str(local_root),
        "attribution_paths": [str(path) for path in project_attribution_paths(project_root)],
        "attributed_session_count": len(attributed),
        "total_local_session_count": len(present),
        "attributed_and_present_count": len(attributed_and_present),
        "attributed_and_missing_count": len(attributed_and_missing),
        "present_but_not_attributed_count": len(present_but_not_attributed),
        "attributed_and_present": attributed_and_present,
        "attributed_and_missing": attributed_and_missing,
        "present_but_not_attributed": present_but_not_attributed,
    }


def attributed_chatlas_index_rows(
    project: Path | str,
    *,
    chatlas_root: Path | None = None,
) -> list[dict[str, Any]]:
    project_root = _project_root(project)
    index = load_chatlas_session_index_rows(chatlas_root=chatlas_root)
    matched: dict[str, dict[str, Any]] = {}
    for attribution_path in project_attribution_paths(project_root):
        for row in index.rows:
            if not chatlas_index_row_matches(
                row,
                uri=None,
                identity_hash=None,
                project=attribution_path,
                project_base=None,
                providers=None,
                instances=None,
                provider_instance_fingerprint=None,
                session_id=None,
                display_name=None,
                extractable_only=False,
                active_after=None,
            ):
                continue
            key = _row_identity_key(row)
            if key not in matched:
                matched[key] = row
    return sort_chatlas_index_rows(list(matched.values()), sort="lexical")


def project_attribution_paths(project: Path | str) -> list[Path]:
    paths: list[Path] = []
    current = _project_root(project)
    while True:
        paths.append(current)
        parent = current.parent
        if parent == current or not _is_agentos_project_root(parent):
            return paths
        current = parent


def _project_root(project: Path | str) -> Path:
    return Path(project).expanduser().resolve()


def _is_agentos_project_root(path: Path) -> bool:
    return (path / ".tarav" / "project.json").is_file()


def _local_root(project_root: Path) -> Path:
    return project_root / "chatlas"


def _row_identity_hash(row: dict[str, Any]) -> str | None:
    value = row.get("identity_hash")
    if not isinstance(value, str) or not value:
        return None
    return value


def _row_identity_key(row: dict[str, Any]) -> str:
    identity_hash = _row_identity_hash(row)
    if identity_hash is not None:
        return f"identity_hash:{identity_hash}"
    uri = row.get("uri")
    if isinstance(uri, str) and uri:
        return f"uri:{uri}"
    return json.dumps(row, sort_keys=True, default=str)


def _local_session_path(local_root: Path, identity_hash: str) -> Path:
    return local_root / f"{_safe_filename_stem(identity_hash)}.json"


def _safe_filename_stem(value: str) -> str:
    safe = "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in value)
    return safe or "unknown"


def _session_payload(
    row: dict[str, Any],
    *,
    path: Path | None = None,
    local_root: Path | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "identity_hash": row.get("identity_hash"),
        "session_id": row.get("session_id"),
        "uri": row.get("uri"),
        "provider": row.get("provider"),
        "project_path": row.get("project_path"),
    }
    if path is not None:
        payload["file"] = _relative_path(path, local_root or path.parent)
    return payload


def _skip_payload(row: dict[str, Any], *, reason: str) -> dict[str, object]:
    payload = _session_payload(row)
    payload["reason"] = reason
    return payload


def _local_session_files(local_root: Path) -> list[Path]:
    if not local_root.is_dir():
        return []
    return sorted(
        path
        for path in local_root.glob("*.json")
        if path.is_file() and path.name != LOCAL_CHATLAS_MANIFEST
    )


def _relative_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _total_local_bytes(local_root: Path) -> int:
    if not local_root.is_dir():
        return 0
    total = 0
    for path in local_root.glob("*.json"):
        if path.is_file():
            total += path.stat().st_size
    return total


__all__ = [
    "LOCAL_CHATLAS_MANIFEST",
    "LOCAL_CHATLAS_MANIFEST_CLASS",
    "LOCAL_CHATLAS_SCHEMA_VERSION",
    "attributed_chatlas_index_rows",
    "chatlas_local_status",
    "chatlas_local_sync",
    "project_attribution_paths",
]
