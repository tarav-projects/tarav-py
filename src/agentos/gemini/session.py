from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from agentos._core.sequences import _unique_paths


GEMINI_PROVIDER = "gemini-cli"


@dataclass(frozen=True)
class GeminiSessionRef:
    native_session_id: str
    artifact_paths: tuple[Path, ...]
    updated_at: float | None = None

    @property
    def provider(self) -> str:
        return GEMINI_PROVIDER

    def matches_query(self, query: str) -> bool:
        if query == self.native_session_id:
            return True
        return any(query in path.name for path in self.artifact_paths)

    def to_session(self) -> "GeminiSession":
        return GeminiSession(
            native_session_id=self.native_session_id,
            artifact_paths=self.artifact_paths,
            updated_at=self.updated_at,
        )


@dataclass(frozen=True)
class GeminiSession:
    native_session_id: str
    artifact_paths: tuple[Path, ...]
    updated_at: float | None = None

    @property
    def provider(self) -> str:
        return GEMINI_PROVIDER

    def merge(self, other: GeminiSession) -> GeminiSession:
        if self.native_session_id != other.native_session_id:
            raise TypeError(
                f"cannot merge Gemini sessions: {self.native_session_id} != {other.native_session_id}"
            )
        return GeminiSession(
            native_session_id=self.native_session_id,
            artifact_paths=_unique_paths(self.artifact_paths + other.artifact_paths),
            updated_at=_coalesce_timestamp(self.updated_at, other.updated_at),
        )


def discover_gemini_sessions(*, targets: tuple[Path, ...]) -> tuple[GeminiSession, ...]:
    sessions_by_id: dict[str, GeminiSession] = {}

    for target in targets:
        for path in _glob_paths(target, "**/chats/session-*.json"):
            session = read_gemini_session(path)
            if session is not None:
                _merge_gemini_session(sessions_by_id, session)

    return _sort_gemini_sessions(tuple(sessions_by_id.values()))


def discover_gemini_session_refs(*, targets: tuple[Path, ...]) -> tuple[GeminiSessionRef, ...]:
    return tuple(
        _gemini_session_ref_from_session(session)
        for session in discover_gemini_sessions(targets=targets)
    )


def find_gemini_sessions(*, targets: tuple[Path, ...], query: str) -> tuple[GeminiSession, ...]:
    sessions_by_id: dict[str, GeminiSession] = {}

    for session_ref in discover_gemini_session_refs(targets=targets):
        if session_ref.matches_query(query):
            session = session_ref.to_session()
            _merge_gemini_session(sessions_by_id, session)

    return _sort_gemini_sessions(tuple(sessions_by_id.values()))


def load_gemini_session(session_ref: GeminiSessionRef) -> GeminiSession:
    return session_ref.to_session()


def read_gemini_session(path: Path) -> GeminiSession | None:
    obj = _read_json_file(path)
    if obj is None:
        return None

    session_id = _string_or_none(obj.get("sessionId"))
    if session_id is None:
        return None

    return GeminiSession(
        native_session_id=session_id,
        artifact_paths=(path,),
        updated_at=(
            _coerce_timestamp(obj.get("lastUpdated"))
            or _coerce_timestamp(obj.get("startTime"))
            or _safe_path_mtime(path)
        ),
    )


def _gemini_session_ref_from_session(session: GeminiSession) -> GeminiSessionRef:
    return GeminiSessionRef(
        native_session_id=session.native_session_id,
        artifact_paths=session.artifact_paths,
        updated_at=session.updated_at,
    )


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


def _glob_paths(root: Path, pattern: str) -> tuple[Path, ...]:
    if root.is_file():
        return (root,) if root.match(pattern) else ()
    if not root.is_dir():
        return ()
    try:
        return tuple(sorted(root.glob(pattern)))
    except OSError:
        return ()


def _merge_gemini_session(sessions_by_id: dict[str, GeminiSession], session: GeminiSession) -> None:
    existing = sessions_by_id.get(session.native_session_id)
    if existing is None:
        sessions_by_id[session.native_session_id] = session
        return
    sessions_by_id[session.native_session_id] = existing.merge(session)


def _sort_gemini_sessions(sessions: tuple[GeminiSession, ...]) -> tuple[GeminiSession, ...]:
    return tuple(sorted(sessions, key=lambda session: session.native_session_id))


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


def _coalesce_timestamp(*values: float | None) -> float | None:
    timestamps = [value for value in values if value is not None]
    if not timestamps:
        return None
    return max(timestamps)


def _string_or_none(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


__all__ = [
    "GeminiSession",
    "GeminiSessionRef",
    "discover_gemini_session_refs",
    "discover_gemini_sessions",
    "find_gemini_sessions",
    "load_gemini_session",
    "read_gemini_session",
]
