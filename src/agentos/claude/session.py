from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Any


CLAUDE_PROVIDER = "claude-code"


@dataclass(frozen=True)
class ClaudeSessionRef:
    native_session_id: str
    artifact_paths: tuple[Path, ...]
    source_ref_id: str | None = None
    title: str | None = None
    source_kind: str = "project"
    updated_at: float | str | None = None

    @property
    def provider(self) -> str:
        return CLAUDE_PROVIDER

    @property
    def transcript_path(self) -> Path:
        return self.artifact_paths[0]

    def matches_query(self, query: str) -> bool:
        return query in {self.native_session_id, self.title}

    def to_session(self) -> "ClaudeSession":
        return ClaudeSession(
            native_session_id=self.native_session_id,
            artifact_paths=self.artifact_paths,
            source_ref_id=self.source_ref_id,
            title=self.title,
            source_kind=self.source_kind,
            updated_at=self.updated_at,
        )

    @classmethod
    def from_chatlas_session_payload(
        cls,
        session: dict[str, Any],
        *,
        sources: list[dict[str, object]],
    ) -> "ClaudeSessionRef | None":
        claude_session = ClaudeSession.from_chatlas_session_payload(
            session,
            sources=sources,
        )
        if claude_session is None:
            return None
        return _claude_session_ref_from_session(claude_session)


@dataclass(frozen=True)
class ClaudeSession:
    native_session_id: str
    artifact_paths: tuple[Path, ...]
    source_ref_id: str | None = None
    title: str | None = None
    source_kind: str = "project"
    updated_at: float | str | None = None

    @property
    def provider(self) -> str:
        return CLAUDE_PROVIDER

    @property
    def transcript_path(self) -> Path:
        return self.artifact_paths[0]

    @classmethod
    def from_chatlas_session_payload(
        cls,
        session: dict[str, Any],
        *,
        sources: list[dict[str, object]],
    ) -> ClaudeSession | None:
        if session.get("provider") != CLAUDE_PROVIDER:
            return None

        native_session_id = _string_or_none(session.get("session_id"))
        if native_session_id is None:
            return None

        primary_artifact = _primary_transcript_artifact(session)
        if primary_artifact is None:
            return None
        transcript_path_text = _string_or_none(primary_artifact.get("path"))
        if transcript_path_text is None:
            return None

        return cls(
            native_session_id=native_session_id,
            artifact_paths=(Path(transcript_path_text),),
            source_ref_id=_source_ref_id_for_artifact(primary_artifact, sources=sources),
            title=_string_or_none(session.get("display_name")),
            updated_at=_string_or_none(session.get("updated_at")),
        )

    def merge(self, other: ClaudeSession) -> ClaudeSession:
        if self.native_session_id != other.native_session_id:
            raise TypeError(
                f"cannot merge Claude sessions: {self.native_session_id} != {other.native_session_id}"
            )
        source_kind = self.source_kind if self.source_kind == other.source_kind else "mixed"
        return ClaudeSession(
            native_session_id=self.native_session_id,
            artifact_paths=_unique_paths(self.artifact_paths + other.artifact_paths),
            source_ref_id=self.source_ref_id or other.source_ref_id,
            title=self.title or other.title,
            source_kind=source_kind,
            updated_at=_coalesce_timestamp(self.updated_at, other.updated_at),
        )


def discover_claude_sessions(*, targets: tuple[Path, ...]) -> tuple[ClaudeSession, ...]:
    sessions_by_id: dict[str, ClaudeSession] = {}

    for target in targets:
        if target.name == "projects":
            for path in _glob_paths(target, "**/*.jsonl"):
                session = read_claude_project_session(path)
                if session is not None:
                    _merge_claude_session(sessions_by_id, session)
            continue

        for path in _glob_paths(target, "**/*.json"):
            session = read_claude_desktop_session(path)
            if session is not None:
                _merge_claude_session(sessions_by_id, session)

    return _sort_claude_sessions(tuple(sessions_by_id.values()))


def discover_claude_session_refs(*, targets: tuple[Path, ...]) -> tuple[ClaudeSessionRef, ...]:
    return tuple(
        _claude_session_ref_from_session(session)
        for session in discover_claude_sessions(targets=targets)
    )


def find_claude_sessions(*, targets: tuple[Path, ...], query: str) -> tuple[ClaudeSession, ...]:
    sessions_by_id: dict[str, ClaudeSession] = {}
    for session_ref in discover_claude_session_refs(targets=targets):
        if session_ref.matches_query(query):
            session = session_ref.to_session()
            _merge_claude_session(sessions_by_id, session)
    return _sort_claude_sessions(tuple(sessions_by_id.values()))


def load_claude_session(session_ref: ClaudeSessionRef) -> ClaudeSession:
    return session_ref.to_session()


def read_claude_project_session(path: Path) -> ClaudeSession | None:
    if not _is_claude_project_session_artifact(path):
        return None

    first_obj = _read_first_jsonl_object(path)
    session_id = path.stem
    updated_at = _safe_path_mtime(path)

    if first_obj is not None:
        first_session_id = _string_or_none(first_obj.get("sessionId"))
        if first_session_id is not None:
            session_id = first_session_id
        updated_at = _coerce_timestamp(first_obj.get("timestamp")) or updated_at

    return ClaudeSession(
        native_session_id=session_id,
        artifact_paths=(path,),
        source_kind="project",
        updated_at=updated_at,
    )


def read_claude_desktop_session(path: Path) -> ClaudeSession | None:
    obj = _read_json_file(path)
    if obj is None:
        return None

    session_id = _string_or_none(obj.get("sessionId"))
    if session_id is None:
        return None

    return ClaudeSession(
        native_session_id=session_id,
        artifact_paths=(path,),
        source_kind="desktop",
        title=_string_or_none(obj.get("title")),
        updated_at=(
            _coerce_timestamp(obj.get("lastActivityAt"))
            or _coerce_timestamp(obj.get("createdAt"))
            or _safe_path_mtime(path)
        ),
    )


def _claude_session_ref_from_session(session: ClaudeSession) -> ClaudeSessionRef:
    return ClaudeSessionRef(
        native_session_id=session.native_session_id,
        artifact_paths=session.artifact_paths,
        source_ref_id=session.source_ref_id,
        title=session.title,
        source_kind=session.source_kind,
        updated_at=session.updated_at,
    )


def _is_claude_project_session_artifact(path: Path) -> bool:
    if path.suffix != ".jsonl":
        return False
    return "subagents" not in path.parts


def _read_json_file(path: Path) -> dict[str, Any] | None:
    try:
        raw_text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None

    try:
        obj = json.loads(raw_text)
    except json.JSONDecodeError:
        return None

    if not isinstance(obj, dict):
        return None
    return obj


def _read_first_jsonl_object(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    return obj
    except OSError:
        return None

    return None


def _glob_paths(root: Path, pattern: str) -> tuple[Path, ...]:
    if root.is_file():
        return (root,) if root.match(pattern) else ()
    if not root.is_dir():
        return ()
    try:
        return tuple(sorted(root.glob(pattern)))
    except OSError:
        return ()


def _merge_claude_session(sessions_by_id: dict[str, ClaudeSession], session: ClaudeSession) -> None:
    existing = sessions_by_id.get(session.native_session_id)
    if existing is None:
        sessions_by_id[session.native_session_id] = session
        return
    sessions_by_id[session.native_session_id] = existing.merge(session)


def _sort_claude_sessions(sessions: tuple[ClaudeSession, ...]) -> tuple[ClaudeSession, ...]:
    return tuple(sorted(sessions, key=lambda session: session.native_session_id))


def _coalesce_timestamp(
    *values: float | str | None,
) -> float | str | None:
    timestamps = [value for value in values if value is not None]
    if not timestamps:
        return None
    numeric = [value for value in timestamps if isinstance(value, (int, float))]
    if numeric:
        return max(float(value) for value in numeric)
    return timestamps[0]


def _safe_path_mtime(path: Path | None) -> float | None:
    if path is None:
        return None
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def _coerce_timestamp(value: object) -> float | None:
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
        return _coerce_timestamp(float(value))
    except ValueError:
        pass

    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        return datetime.fromisoformat(normalized).timestamp()
    except ValueError:
        return None


def _unique_paths(paths: tuple[Path, ...]) -> tuple[Path, ...]:
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return tuple(unique)


def _primary_transcript_artifact(session: dict[str, Any]) -> dict[str, Any] | None:
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


def _source_ref_id_for_artifact(
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
            return _string_or_none(source.get("source_ref_id"))
    return None


def _string_or_none(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


__all__ = [
    "ClaudeSession",
    "ClaudeSessionRef",
    "discover_claude_session_refs",
    "discover_claude_sessions",
    "find_claude_sessions",
    "load_claude_session",
    "read_claude_desktop_session",
    "read_claude_project_session",
]
