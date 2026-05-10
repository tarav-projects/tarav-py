from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from agentos._core.errors import CliError
from agentos._core.sequences import _unique_strings
from agentos.agent.primitives import SessionSource
from agentos.agent.session_utils import (
    artifact_paths_by_role as _artifact_paths_by_role,
    coalesce_timestamp as _coalesce_timestamp,
    coerce_timestamp as _coerce_timestamp,
    primary_source_path as _primary_source_path,
    safe_path_mtime as _safe_path_mtime,
    string_or_none as _string_or_none,
)


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

    def matches_query(self, query: str) -> bool:
        return query == self.native_session_id or query in self.session_keys

    def display_name(self) -> str | None:
        return None

    def display_name_field(self) -> str | None:
        return None

    def native_ref_metadata(self) -> dict[str, object]:
        payload: dict[str, object] = {}
        if self.session_keys:
            payload["session_keys"] = list(self.session_keys)
        if self.agent_id is not None:
            payload["agent_id"] = self.agent_id
        return payload

    def sort_timestamp(self) -> float | None:
        return _coalesce_timestamp(
            self.updated_at,
            _safe_path_mtime(self.transcript_path),
            _safe_path_mtime(self.sessions_index_path),
        )

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

    def sources(self) -> tuple[SessionSource, ...]:
        sources: list[SessionSource] = []
        if self.transcript_path is not None:
            sources.append(SessionSource(role="transcript", path=self.transcript_path))
        if self.sessions_index_path is not None:
            if self.session_keys:
                locator = {
                    "kind": "json_object_keys",
                    "keys": list(self.session_keys),
                }
            else:
                locator = {
                    "kind": "json_object_value_match",
                    "match": {"sessionId": self.native_session_id},
                }
            sources.append(
                SessionSource(
                    role="session_index",
                    path=self.sessions_index_path,
                    locator=locator,
                )
            )
        return tuple(sources)

    def created_timestamp(self) -> float | None:
        artifact = _primary_source_path(self.sources())
        if artifact is None or not artifact.exists():
            return None

        try:
            from agentos.agent.extractors.openclaw import load_openclaw_session_records

            records = load_openclaw_session_records(artifact)
            if records:
                return _coerce_timestamp(records[0].get("timestamp"))
        except (CliError, OSError, json.JSONDecodeError):
            return None
        return None

    def dialog_turn_count(self) -> int | None:
        if self.transcript_path is None or not self.transcript_path.is_file():
            return None

        try:
            from agentos.agent.extractors.openclaw import (
                extract_dialog_from_openclaw_session,
                load_openclaw_session_records,
            )

            return len(
                extract_dialog_from_openclaw_session(
                    records=load_openclaw_session_records(self.transcript_path),
                    session_id=self.native_session_id,
                    raw=False,
                )
            )
        except (CliError, OSError, json.JSONDecodeError):
            return None

    def provider_stats(self) -> dict[str, object]:
        return {
            "has_transcript": self.transcript_path is not None and self.transcript_path.is_file(),
            "has_sessions_index": (
                self.sessions_index_path is not None and self.sessions_index_path.is_file()
            ),
            "session_key_count": len(self.session_keys),
            "dialog_turn_count": self.dialog_turn_count(),
        }

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

    @classmethod
    def from_chatlas_session_payload(cls, session: dict[str, Any]) -> OpenclawSession | None:
        if session.get("provider") != OPENCLAW_PROVIDER:
            return None
        native_session_id = _string_or_none(session.get("session_id"))
        if native_session_id is None:
            return None

        transcript_paths = _artifact_paths_by_role(session, role="transcript")
        index_paths = _artifact_paths_by_role(session, role="session_index")
        native = session.get("native")
        session_keys: tuple[str, ...] = ()
        agent_id = None
        if isinstance(native, dict):
            raw_session_keys = native.get("session_keys")
            if isinstance(raw_session_keys, list):
                session_keys = tuple(
                    key for key in raw_session_keys if isinstance(key, str) and key
                )
            agent_id = _string_or_none(native.get("agent_id"))

        return cls(
            native_session_id=native_session_id,
            transcript_path=Path(transcript_paths[0]) if transcript_paths else None,
            sessions_index_path=Path(index_paths[0]) if index_paths else None,
            session_keys=session_keys,
            agent_id=agent_id,
            updated_at=_coerce_timestamp(session.get("updated_at")),
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

    for session_ref in discover_openclaw_session_refs(targets=targets):
        if session_ref.matches_query(query):
            session = session_ref.to_session()
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


__all__ = [
    "OpenclawSession",
    "OpenclawSessionRef",
    "discover_openclaw_session_refs",
    "discover_openclaw_sessions",
    "find_openclaw_sessions",
    "load_openclaw_session",
    "read_openclaw_agent_sessions",
]
