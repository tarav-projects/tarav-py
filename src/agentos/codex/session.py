from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Any


CODEX_PROVIDER = "codex"


@dataclass(frozen=True)
class CodexSession:
    native_session_id: str
    rollout_paths: tuple[Path, ...] = ()
    source_ref_id: str | None = None
    thread_name: str | None = None
    index_paths: tuple[Path, ...] = ()
    updated_at: float | None = None

    @property
    def provider(self) -> str:
        return CODEX_PROVIDER

    @property
    def rollout_path(self) -> Path | None:
        if not self.rollout_paths:
            return None
        return self.rollout_paths[0]

    @property
    def session_id(self) -> str:
        return self.native_session_id

    def matches_query(self, query: str) -> bool:
        return query in {self.native_session_id, self.thread_name}

    def merge(self, other: CodexSession) -> CodexSession:
        if self.native_session_id != other.native_session_id:
            raise TypeError(
                f"cannot merge Codex sessions: {self.native_session_id} != {other.native_session_id}"
            )
        return CodexSession(
            native_session_id=self.native_session_id,
            rollout_paths=_unique_paths(self.rollout_paths + other.rollout_paths),
            source_ref_id=self.source_ref_id or other.source_ref_id,
            thread_name=self.thread_name or other.thread_name,
            index_paths=_unique_paths(self.index_paths + other.index_paths),
            updated_at=_coalesce_timestamp(self.updated_at, other.updated_at),
        )

    @classmethod
    def from_chatlas_session_payload(
        cls,
        session: dict[str, Any],
        *,
        sources: list[dict[str, object]],
    ) -> CodexSession | None:
        if session.get("provider") != CODEX_PROVIDER:
            return None

        native_session_id = _string_or_none(session.get("session_id"))
        if native_session_id is None:
            return None

        primary_artifact = _primary_transcript_artifact(session)
        if primary_artifact is None:
            return None
        rollout_path_text = _string_or_none(primary_artifact.get("path"))
        if rollout_path_text is None:
            return None

        return cls(
            native_session_id=native_session_id,
            rollout_paths=(Path(rollout_path_text),),
            source_ref_id=_source_ref_id_for_artifact(primary_artifact, sources=sources),
            thread_name=_string_or_none(session.get("display_name")),
            index_paths=tuple(
                Path(path_text)
                for path_text in _artifact_paths_by_role(session, role="session_index")
            ),
            updated_at=_coerce_timestamp(session.get("updated_at")),
        )


def discover_codex_sessions(*, targets: tuple[Path, ...]) -> tuple[CodexSession, ...]:
    sessions_by_id: dict[str, CodexSession] = {}

    for target in targets:
        if target.is_file() and target.name == "session_index.jsonl":
            for session in read_codex_index_sessions(target):
                _merge_codex_session(sessions_by_id, session)
            continue
        for path in _glob_paths(target, "**/rollout-*.jsonl"):
            session = read_codex_rollout_session(path)
            if session is not None:
                _merge_codex_session(sessions_by_id, session)

    return _sort_codex_sessions(tuple(sessions_by_id.values()))


def find_codex_sessions(*, targets: tuple[Path, ...], query: str) -> tuple[CodexSession, ...]:
    sessions_by_id: dict[str, CodexSession] = {}
    for session in discover_codex_sessions(targets=targets):
        if session.matches_query(query):
            _merge_codex_session(sessions_by_id, session)
    return _sort_codex_sessions(tuple(sessions_by_id.values()))


def read_codex_rollout_session(path: Path) -> CodexSession | None:
    meta_obj = _read_codex_session_meta(path)
    if meta_obj is None:
        return None

    payload = meta_obj.get("payload")
    if not isinstance(payload, dict):
        return None

    session_id = _string_or_none(payload.get("id"))
    if session_id is None:
        return None

    return CodexSession(
        native_session_id=session_id,
        rollout_paths=(path,),
        updated_at=_coalesce_timestamp(_safe_path_mtime(path), _coerce_timestamp(meta_obj.get("timestamp"))),
    )


def read_codex_index_sessions(path: Path) -> tuple[CodexSession, ...]:
    if not path.is_file():
        return ()

    sessions: list[CodexSession] = []
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
                if not isinstance(obj, dict):
                    continue
                session_id = _string_or_none(obj.get("id"))
                if session_id is None:
                    continue
                sessions.append(
                    CodexSession(
                        native_session_id=session_id,
                        thread_name=_string_or_none(obj.get("thread_name")),
                        index_paths=(path,),
                        updated_at=_coalesce_timestamp(_coerce_timestamp(obj.get("updated_at")), _safe_path_mtime(path)),
                    )
                )
    except OSError:
        return ()

    return tuple(sessions)


def _read_codex_session_meta(path: Path) -> dict[str, Any] | None:
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
                if not isinstance(obj, dict):
                    continue
                if obj.get("type") != "session_meta":
                    continue
                payload = obj.get("payload")
                if not isinstance(payload, dict):
                    continue
                if _string_or_none(payload.get("id")) is None:
                    continue
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


def _merge_codex_session(sessions_by_id: dict[str, CodexSession], session: CodexSession) -> None:
    existing = sessions_by_id.get(session.native_session_id)
    if existing is None:
        sessions_by_id[session.native_session_id] = session
        return
    sessions_by_id[session.native_session_id] = existing.merge(session)


def _sort_codex_sessions(sessions: tuple[CodexSession, ...]) -> tuple[CodexSession, ...]:
    return tuple(sorted(sessions, key=lambda session: session.native_session_id))


def _coalesce_timestamp(*values: float | None) -> float | None:
    timestamps = [value for value in values if value is not None]
    if not timestamps:
        return None
    return max(timestamps)


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


def _artifact_paths_by_role(session: dict[str, Any], *, role: str) -> tuple[str, ...]:
    artifacts = session.get("backing_artifacts")
    if not isinstance(artifacts, list):
        return ()

    paths: list[str] = []
    for artifact in artifacts:
        if not isinstance(artifact, dict) or artifact.get("role") != role:
            continue
        path_text = _string_or_none(artifact.get("path"))
        if path_text is not None:
            paths.append(path_text)
    return tuple(paths)


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
    "CodexSession",
    "discover_codex_sessions",
    "find_codex_sessions",
    "read_codex_index_sessions",
    "read_codex_rollout_session",
]
