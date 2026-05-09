from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from typing import Any

from agentos._core.sequences import _unique_strings


OPENCLAW_PROVIDER = "openclaw"


@dataclass(frozen=True)
class OpenclawSessionRef:
    native_session_id: str
    transcript_path: Path | None = None
    sessions_index_path: Path | None = None
    session_keys: tuple[str, ...] = ()
    agent_id: str | None = None
    updated_at: float | None = None

    @property
    def provider(self) -> str:
        return OPENCLAW_PROVIDER

    def to_session(self) -> "OpenclawSession":
        return OpenclawSession(
            native_session_id=self.native_session_id,
            transcript_path=self.transcript_path,
            sessions_index_path=self.sessions_index_path,
            session_keys=self.session_keys,
            agent_id=self.agent_id,
            updated_at=self.updated_at,
        )


@dataclass(frozen=True)
class OpenclawSession:
    native_session_id: str
    transcript_path: Path | None = None
    sessions_index_path: Path | None = None
    session_keys: tuple[str, ...] = ()
    agent_id: str | None = None
    updated_at: float | None = None

    @property
    def provider(self) -> str:
        return OPENCLAW_PROVIDER

    def matches_query(self, query: str) -> bool:
        return query == self.native_session_id or query in self.session_keys

    def merge(self, other: OpenclawSession) -> OpenclawSession:
        if self.native_session_id != other.native_session_id:
            raise TypeError(
                f"cannot merge OpenClaw sessions: {self.native_session_id} != {other.native_session_id}"
            )
        return OpenclawSession(
            native_session_id=self.native_session_id,
            transcript_path=self.transcript_path or other.transcript_path,
            sessions_index_path=self.sessions_index_path or other.sessions_index_path,
            session_keys=_unique_strings(self.session_keys + other.session_keys),
            agent_id=self.agent_id if self.agent_id == other.agent_id else self.agent_id or other.agent_id,
            updated_at=_coalesce_timestamp(self.updated_at, other.updated_at),
        )


def discover_openclaw_sessions(*, targets: tuple[Path, ...]) -> tuple[OpenclawSession, ...]:
    sessions_by_id: dict[str, OpenclawSession] = {}

    for target in targets:
        for agent_dir in _iter_openclaw_agent_dirs(target):
            for session in read_openclaw_agent_sessions(agent_dir):
                _merge_openclaw_session(sessions_by_id, session)

    return _sort_openclaw_sessions(tuple(sessions_by_id.values()))


def discover_openclaw_session_refs(*, targets: tuple[Path, ...]) -> tuple[OpenclawSessionRef, ...]:
    return tuple(
        _openclaw_session_ref_from_session(session)
        for session in discover_openclaw_sessions(targets=targets)
    )


def find_openclaw_sessions(*, targets: tuple[Path, ...], query: str) -> tuple[OpenclawSession, ...]:
    sessions_by_id: dict[str, OpenclawSession] = {}

    for session in discover_openclaw_sessions(targets=targets):
        if session.matches_query(query):
            _merge_openclaw_session(sessions_by_id, session)

    return _sort_openclaw_sessions(tuple(sessions_by_id.values()))


def load_openclaw_session(session_ref: OpenclawSessionRef) -> OpenclawSession:
    return session_ref.to_session()


def read_openclaw_agent_sessions(agent_dir: Path) -> tuple[OpenclawSession, ...]:
    sessions_dir = agent_dir / "sessions"
    index_path = sessions_dir / "sessions.json"
    transcript_paths = {
        path.stem: path
        for path in sorted(sessions_dir.glob("*.jsonl"), key=lambda path: path.name)
        if ".reset." not in path.name
    }

    sessions_by_id: dict[str, OpenclawSession] = {}
    index_obj = _read_json_file(index_path)
    if isinstance(index_obj, dict):
        for session_key, entry in index_obj.items():
            if not isinstance(entry, dict):
                continue
            session_id = _string_or_none(entry.get("sessionId"))
            if session_id is None:
                continue

            transcript_path = _openclaw_transcript_path_from_entry(entry) or transcript_paths.get(session_id)
            session = OpenclawSession(
                native_session_id=session_id,
                transcript_path=transcript_path,
                sessions_index_path=index_path.resolve(),
                session_keys=(session_key,) if isinstance(session_key, str) and session_key else (),
                agent_id=agent_dir.name,
                updated_at=(
                    _coerce_timestamp(entry.get("updatedAt"))
                    or _safe_path_mtime(transcript_path)
                    or _safe_path_mtime(index_path)
                ),
            )
            _merge_openclaw_session(sessions_by_id, session)

    for session_id, transcript_path in transcript_paths.items():
        existing = sessions_by_id.get(session_id)
        transcript_path = transcript_path.resolve()
        if existing is None:
            sessions_by_id[session_id] = OpenclawSession(
                native_session_id=session_id,
                transcript_path=transcript_path,
                sessions_index_path=index_path.resolve() if index_path.exists() else None,
                agent_id=agent_dir.name,
                updated_at=_safe_path_mtime(transcript_path),
            )
            continue

        sessions_by_id[session_id] = OpenclawSession(
            native_session_id=session_id,
            transcript_path=existing.transcript_path or transcript_path,
            sessions_index_path=existing.sessions_index_path,
            session_keys=existing.session_keys,
            agent_id=existing.agent_id,
            updated_at=existing.updated_at or _safe_path_mtime(transcript_path),
        )

    return tuple(sessions_by_id.values())


def _openclaw_session_ref_from_session(session: OpenclawSession) -> OpenclawSessionRef:
    return OpenclawSessionRef(
        native_session_id=session.native_session_id,
        transcript_path=session.transcript_path,
        sessions_index_path=session.sessions_index_path,
        session_keys=session.session_keys,
        agent_id=session.agent_id,
        updated_at=session.updated_at,
    )


def _iter_openclaw_agent_dirs(root: Path) -> tuple[Path, ...]:
    if not root.is_dir():
        return ()
    return tuple(
        child
        for child in sorted(root.iterdir(), key=lambda path: path.name)
        if child.is_dir() and (child / "sessions").is_dir()
    )


def _openclaw_transcript_path_from_entry(entry: dict[str, Any]) -> Path | None:
    session_file = _string_or_none(entry.get("sessionFile"))
    if session_file is None:
        return None
    candidate = Path(session_file).expanduser()
    if not candidate.is_file():
        return None
    return candidate.resolve()


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


def _merge_openclaw_session(
    sessions_by_id: dict[str, OpenclawSession],
    session: OpenclawSession,
) -> None:
    existing = sessions_by_id.get(session.native_session_id)
    if existing is None:
        sessions_by_id[session.native_session_id] = session
        return
    sessions_by_id[session.native_session_id] = existing.merge(session)


def _sort_openclaw_sessions(sessions: tuple[OpenclawSession, ...]) -> tuple[OpenclawSession, ...]:
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
    "OpenclawSession",
    "OpenclawSessionRef",
    "discover_openclaw_session_refs",
    "discover_openclaw_sessions",
    "find_openclaw_sessions",
    "load_openclaw_session",
    "read_openclaw_agent_sessions",
]
