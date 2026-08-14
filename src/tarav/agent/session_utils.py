# $kw: --from Agent.Normal.Model
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from tarav.agent.primitives import SessionSource


def coerce_timestamp(value: object) -> float | None:
    if value is None:
        return None

    if isinstance(value, (int, float)):
        timestamp = float(value)
        if timestamp > 1_000_000_000_000:
            return timestamp / 1000.0
        if timestamp > 1_000_000_000:
            return timestamp
        return None

    if not isinstance(value, str):
        return None

    value = value.strip()
    if not value:
        return None

    try:
        return coerce_timestamp(float(value))
    except ValueError:
        pass

    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        return datetime.fromisoformat(normalized).timestamp()
    except ValueError:
        return None


def safe_path_mtime(path: Path | None) -> float | None:
    if path is None:
        return None
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def coalesce_timestamp(*values: float | None) -> float | None:
    timestamps = [value for value in values if value is not None]
    if not timestamps:
        return None
    return max(timestamps)


def glob_paths(root: Path, pattern: str) -> tuple[Path, ...]:
    if root.is_file():
        return (root,) if root.match(pattern) else ()
    if not root.is_dir():
        return ()
    try:
        return tuple(sorted(root.glob(pattern)))
    except OSError:
        return ()


def primary_source_path(sources: tuple[SessionSource, ...]) -> Path | None:
    if not sources:
        return None
    return sources[0].path


def created_timestamp_from_turns(turns: list[Any]) -> float | None:
    for turn in turns:
        timestamp = coerce_timestamp(getattr(turn, "timestamp", None))
        if timestamp is not None:
            return timestamp
    return None


def primary_transcript_artifact(session: dict[str, Any]) -> dict[str, Any] | None:
    primary = session.get("primary_backing_artifact")
    if isinstance(primary, dict) and primary.get("role") == "transcript":
        return primary
    artifacts = session.get("backing_artifacts")
    if not isinstance(artifacts, list):
        return None
    for artifact in artifacts:
        if isinstance(artifact, dict) and artifact.get("role") == "transcript":
            return artifact
    return None


def artifact_paths_by_role(session: dict[str, Any], *, role: str) -> tuple[str, ...]:
    artifacts = session.get("backing_artifacts")
    if not isinstance(artifacts, list):
        return ()
    paths = []
    for artifact in artifacts:
        if not isinstance(artifact, dict) or artifact.get("role") != role:
            continue
        path_text = string_or_none(artifact.get("path"))
        if path_text is not None:
            paths.append(path_text)
    return tuple(paths)


def source_ref_id_for_artifact(
    artifact: dict[str, Any],
    *,
    sources: list[dict[str, object]],
) -> str | None:
    role = artifact.get("role")
    storage_kind = artifact.get("storage_kind")
    path = artifact.get("path")
    for source in sources:
        if (
            source.get("role") == role
            and source.get("storage_kind") == storage_kind
            and source.get("path") == path
        ):
            return string_or_none(source.get("source_ref_id"))
    return None


def string_or_none(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None
