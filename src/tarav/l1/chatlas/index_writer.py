from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from tarav.l1.agent.session_refs import BackingArtifact
from tarav.l1.agent.sessions import (
    CHAT_SESSION_URI_PREFIX,
    _format_stats_timestamp,
    current_chat_session_uri,
)
from tarav.l1.chatlas._cache_io import write_text_if_changed
from tarav.l1.chatlas.index_store import (
    iter_session_index_rows,
    session_index_shard_path,
    session_index_shard_prefix,
)
from tarav.l1.chatlas.index_time import chatlas_index_timestamp_sort_value
from tarav.l1.chatlas.session_identity import session_identity_hash

if TYPE_CHECKING:
    from tarav.l1.chatlas.provider_home_adapter import ChatlasDiscoveredSession

_TRANSCRIPT_EXTRACTABLE_SUFFIXES = {
    "claude-code": {".json", ".jsonl"},
    "copilot-cli": {".jsonl"},
}

_USE_PROVIDER_INSTANCE_HOME = object()


def _session_index_row(
    session: "ChatlasDiscoveredSession",
    *,
    provider_home: str | None | object = _USE_PROVIDER_INSTANCE_HOME,
) -> dict[str, Any]:
    session_ref = session.session_ref
    backing_artifacts = session.backing_artifacts()
    primary_backing_artifact = backing_artifacts[0] if backing_artifacts else None
    if provider_home is _USE_PROVIDER_INSTANCE_HOME:
        from tarav.l1.chatlas.provider_home_adapter import provider_instance_home
        provider_home = provider_instance_home(session.provider_instance)
    home_value = provider_home if isinstance(provider_home, str) else None


    from tarav.l1.chatlas.index_metadata import index_metadata

    meta = index_metadata(session.provider_instance.provider, backing_artifacts)
    if meta is None:
        native = dict(session_ref.native_ref_metadata())
        meta = {
            "native": native,
            "project_path": _session_project_path(native),
            "display_name": session_ref.display_name(),
            "display_name_field": session_ref.display_name_field(),
            "created_at": _format_stats_timestamp(
                session_ref.to_session().created_timestamp()
            ),
            "last_activity_at": _format_stats_timestamp(session_ref.sort_timestamp()),
        }
    return {
        "schema": "tarav.chatlas.session-index-row",
        "schema_version": 2,
        "provider": session.provider_instance.provider,
        "instance": session.provider_instance.instance,
        "provider_instance_fingerprint": session.provider_instance.fingerprint,
        "home": home_value,
        "project_path": meta["project_path"],
        "uri": _session_uri(session),
        "session_id": session.session_id,
        "display_name": meta["display_name"],
        "display_name_field": meta["display_name_field"],
        "created_at": meta["created_at"],
        "last_activity_at": meta["last_activity_at"],
        "extractable": any(_backing_artifact_is_extractable(session.provider_instance.provider, artifact) for artifact in backing_artifacts),
        "backing_artifact_count": len(backing_artifacts),
        "primary_backing_artifact": (
            _serialize_backing_artifact(session.provider_instance.provider, primary_backing_artifact)
            if primary_backing_artifact is not None
            else None
        ),
        "backing_artifacts": [
            _serialize_backing_artifact(session.provider_instance.provider, artifact)
            for artifact in backing_artifacts
        ],
        "native": meta["native"],
        "identity_hash": session_identity_hash(
            provider=session.provider_instance.provider,
            instance=session.provider_instance.instance,
            session_id=session.session_id,
        ),
    }


def _session_project_path(native: dict[str, object]) -> str | None:
    project_path = native.get("project_path")
    if isinstance(project_path, str) and project_path:
        return project_path
    cwd = native.get("cwd")
    if isinstance(cwd, str) and cwd:
        return cwd
    return None


def _session_uri(session: "ChatlasDiscoveredSession") -> str:
    return (
        f"{CHAT_SESSION_URI_PREFIX}{quote(session.provider_instance.provider, safe='')}/"
        f"{quote(session.provider_instance.fingerprint, safe='')}/"
        f"{quote(session.session_id, safe='')}"
    )


def _serialize_backing_artifact(provider: str, artifact: BackingArtifact) -> dict[str, Any]:
    return artifact.summary(
        extractable=_backing_artifact_is_extractable(provider, artifact),
    )


def _backing_artifact_is_extractable(provider: str, artifact: BackingArtifact) -> bool:
    if not artifact.path.is_file():
        return False
    if provider == "codex":
        return artifact.role == "transcript" and artifact.path.name.startswith("rollout-") and artifact.path.suffix == ".jsonl"
    if provider in _TRANSCRIPT_EXTRACTABLE_SUFFIXES:
        return artifact.role == "transcript" and artifact.path.suffix in _TRANSCRIPT_EXTRACTABLE_SUFFIXES[provider]
    return False


def _upsert_session_index_rows(
    session_index_root: Path,
    *,
    rows: list[dict[str, Any]],
) -> int:
    rows_by_shard = _rows_by_shard(rows)
    for (provider, prefix), incoming_rows in rows_by_shard.items():
        path = session_index_shard_path(
            session_index_root,
            provider=provider,
            identity_hash=f"{prefix}0",
        )
        existing_rows = iter_session_index_rows(
            session_index_root,
            provider=provider,
            identity_hash=f"{prefix}0",
        )
        rendered = _render_session_index_rows(
            _merge_session_index_rows(existing_rows + incoming_rows)
        )
        write_text_if_changed(path, rendered)
    return len(rows)


def _replace_session_index_rows(
    session_index_root: Path,
    *,
    rows: list[dict[str, Any]],
) -> int:
    rows_by_shard = _rows_by_shard(rows)
    for (provider, prefix), shard_rows in rows_by_shard.items():
        path = session_index_shard_path(
            session_index_root,
            provider=provider,
            identity_hash=f"{prefix}0",
        )
        rendered = _render_session_index_rows(_merge_session_index_rows(shard_rows))
        write_text_if_changed(path, rendered)
    return len(rows)


def _render_session_index_rows(rows: list[dict[str, Any]]) -> str:
    return "".join(
        json.dumps(row, sort_keys=True) + "\n"
        for row in sorted(
            rows,
            key=lambda payload: (
                str(payload.get("provider", "")),
                str(payload.get("identity_hash", "")),
                str(payload.get("session_id", "")),
            ),
        )
    )


def _index_partition_count(
    *,
    rows: list[dict[str, Any]],
) -> int:
    return len(_rows_by_shard(rows))


def _rows_by_shard(rows: list[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    result: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        provider = row.get("provider")
        identity_hash = row.get("identity_hash")
        if not isinstance(provider, str) or not provider:
            continue
        if not isinstance(identity_hash, str) or not identity_hash:
            continue
        result.setdefault((provider, session_index_shard_prefix(identity_hash)), []).append(row)
    return result


def _merge_session_index_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    versions_by_identity: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        identity_hash = row.get("identity_hash")
        if not isinstance(identity_hash, str) or not identity_hash:
            continue
        versions_by_identity.setdefault(identity_hash, []).extend(archive_versions_for(row))
    return [
        _merged_session_index_row(versions)
        for identity_hash, versions in sorted(versions_by_identity.items())
        if versions
    ]


def _merged_session_index_row(versions: list[dict[str, Any]]) -> dict[str, Any]:
    deduped = _dedupe_versions(versions)
    active = dict(select_active_archive_version(deduped))
    if len(deduped) > 1:
        active["archive_versions"] = sorted(
            deduped,
            key=lambda row: _version_sort_key(row),
        )
    # tarav.breadcrumb a0b9d5828486
    active["raw_version"] = raw_version(active)
    return active


def archive_versions_for(row: dict[str, Any]) -> list[dict[str, Any]]:
    versions = row.get("archive_versions")
    if isinstance(versions, list) and versions:
        return [
            plain_index_version(version)
            for version in versions
            if isinstance(version, dict)
        ]
    return [plain_index_version(row)]


@dataclass(frozen=True, slots=True)
class TranscriptSource:
    path: Path
    current: bool


def transcript_sources(row: dict[str, Any]) -> tuple[TranscriptSource, ...]:
    """The transcript artifacts a session is normalized from, current ones last."""
    current_paths = _version_transcript_paths(row)
    all_paths: dict[str, Path] = {}
    for version in archive_versions_for(row):
        for path in _version_transcript_paths(version):
            all_paths[str(path)] = path
    for path in current_paths:
        all_paths[str(path)] = path
    current_keys = {str(path) for path in current_paths}
    return tuple(
        TranscriptSource(path=path, current=key in current_keys)
        for key, path in sorted(
            all_paths.items(),
            key=lambda item: (item[0] in current_keys, item[0]),
        )
    )


def _version_transcript_paths(version: dict[str, Any]) -> tuple[Path, ...]:
    artifacts = version.get("backing_artifacts")
    if not isinstance(artifacts, list):
        artifacts = []
    candidates = [*artifacts, version.get("primary_backing_artifact")]
    paths: dict[str, Path] = {}
    for artifact in candidates:
        if not isinstance(artifact, dict) or artifact.get("role") != "transcript":
            continue
        path_text = artifact.get("path")
        if not isinstance(path_text, str) or not path_text:
            continue
        path = Path(path_text).expanduser().resolve()
        paths[str(path)] = path
    return tuple(paths[key] for key in sorted(paths))


# tarav.breadcrumb a33ff887a607
# tarav.breadcrumb 8c6ba02ca44e
def raw_version(row: dict[str, Any]) -> str | None:
    """The version of the raw data a session is normalized from.

    It hashes the path, size and modification time of every transcript source,
    so a derived artifact recording it is fresh while that data is unchanged.
    A missing source leaves no version.
    """
    fingerprints: list[list[object]] = []
    for source in transcript_sources(row):
        try:
            stat = source.path.stat()
        except OSError:
            return None
        fingerprints.append([str(source.path), stat.st_size, stat.st_mtime_ns])
    if not fingerprints:
        return None
    encoded = json.dumps(fingerprints, separators=(",", ":")).encode("utf-8")
    return f"sha256:{sha256(encoded).hexdigest()}"


def plain_index_version(row: dict[str, Any]) -> dict[str, Any]:
    version = dict(row)
    version.pop("archive_versions", None)
    version.pop("raw_version", None)
    # A retained version differing only by the pre-rename URI scheme is the same version.
    if isinstance(version.get("uri"), str):
        version["uri"] = current_chat_session_uri(version["uri"])
    return version


def select_active_archive_version(versions: list[dict[str, Any]]) -> dict[str, Any]:
    if not versions:
        raise ValueError("cannot select an active archive version from an empty list")
    return max(versions, key=_active_version_sort_key)


def _active_version_sort_key(row: dict[str, Any]) -> tuple[float, int, str]:
    return (
        chatlas_index_timestamp_sort_value(row.get("last_activity_at")),
        _backing_artifact_size(row),
        json.dumps(row, sort_keys=True, default=str),
    )


def _version_sort_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(row.get("provider", "")),
        str(row.get("provider_instance_fingerprint", "")),
        str(row.get("session_id", "")),
        str(row.get("uri", "")),
    )


def _dedupe_versions(versions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for version in versions:
        plain = plain_index_version(version)
        identity = json.dumps(plain, sort_keys=True, default=str)
        if identity in seen:
            continue
        seen.add(identity)
        deduped.append(plain)
    return deduped


def _backing_artifact_size(row: dict[str, Any]) -> int:
    paths: list[str] = []
    artifacts = row.get("backing_artifacts")
    if isinstance(artifacts, list):
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            path = artifact.get("path")
            if isinstance(path, str) and path:
                paths.append(path)
    if not paths:
        primary = row.get("primary_backing_artifact")
        if isinstance(primary, dict):
            path = primary.get("path")
            if isinstance(path, str) and path:
                paths.append(path)
    size = 0
    for path_text in dict.fromkeys(paths):
        try:
            size += Path(path_text).stat().st_size
        except OSError:
            continue
    return size
