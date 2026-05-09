from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


COPILOT_PROVIDER = "copilot-cli"


@dataclass(frozen=True)
class CopilotSessionRef:
    native_session_id: str
    events_path: Path
    source_ref_id: str | None = None
    updated_at: float | None = None

    @property
    def provider(self) -> str:
        return COPILOT_PROVIDER

    def to_session(self) -> "CopilotSession":
        return CopilotSession(
            native_session_id=self.native_session_id,
            events_path=self.events_path,
            source_ref_id=self.source_ref_id,
            updated_at=self.updated_at,
        )

    @classmethod
    def from_chatlas_session_payload(
        cls,
        session: dict[str, Any],
        *,
        sources: list[dict[str, object]],
    ) -> "CopilotSessionRef | None":
        copilot_session = CopilotSession.from_chatlas_session_payload(
            session,
            sources=sources,
        )
        if copilot_session is None:
            return None
        return _copilot_session_ref_from_session(copilot_session)


@dataclass(frozen=True)
class CopilotSession:
    native_session_id: str
    events_path: Path
    source_ref_id: str | None = None
    updated_at: float | None = None

    @property
    def provider(self) -> str:
        return COPILOT_PROVIDER

    @classmethod
    def from_chatlas_session_payload(
        cls,
        session: dict[str, Any],
        *,
        sources: list[dict[str, object]],
    ) -> CopilotSession | None:
        if session.get("provider") != COPILOT_PROVIDER:
            return None

        native_session_id = _string_or_none(session.get("session_id"))
        if native_session_id is None:
            return None

        primary_artifact = _primary_transcript_artifact(session)
        if primary_artifact is None:
            return None
        events_path_text = _string_or_none(primary_artifact.get("path"))
        if events_path_text is None:
            return None

        return cls(
            native_session_id=native_session_id,
            events_path=Path(events_path_text),
            source_ref_id=_source_ref_id_for_artifact(primary_artifact, sources=sources),
            updated_at=_coerce_timestamp(session.get("updated_at")),
        )


def discover_copilot_sessions(*, targets: tuple[Path, ...]) -> tuple[CopilotSession, ...]:
    sessions_by_id: dict[str, CopilotSession] = {}

    for target in targets:
        if target.is_file():
            session = read_copilot_session(target)
            if session is not None:
                _merge_copilot_session(sessions_by_id, session)
            continue

        if not target.is_dir():
            continue

        for child in sorted(target.iterdir(), key=lambda path: path.name):
            session = read_copilot_session(child)
            if session is None:
                continue
            _merge_copilot_session(sessions_by_id, session)

    return _sort_copilot_sessions(tuple(sessions_by_id.values()))


def discover_copilot_session_refs(*, targets: tuple[Path, ...]) -> tuple[CopilotSessionRef, ...]:
    return tuple(_copilot_session_ref_from_session(session) for session in discover_copilot_sessions(targets=targets))


def find_copilot_sessions(*, targets: tuple[Path, ...], query: str) -> tuple[CopilotSession, ...]:
    sessions_by_id: dict[str, CopilotSession] = {}
    for session in discover_copilot_sessions(targets=targets):
        if query in {session.native_session_id, session.events_path.stem}:
            _merge_copilot_session(sessions_by_id, session)
    return _sort_copilot_sessions(tuple(sessions_by_id.values()))


def load_copilot_session(session_ref: CopilotSessionRef) -> CopilotSession:
    return session_ref.to_session()


def read_copilot_session(path: Path) -> CopilotSession | None:
    if path.is_dir():
        events_path = path / "events.jsonl"
        if not events_path.is_file():
            return None
        return CopilotSession(
            native_session_id=path.name,
            events_path=events_path,
            updated_at=_safe_path_mtime(events_path) or _safe_path_mtime(path),
        )

    if path.is_file() and path.suffix == ".jsonl":
        return CopilotSession(
            native_session_id=path.stem,
            events_path=path,
            updated_at=_safe_path_mtime(path),
        )

    return None


def _copilot_session_ref_from_session(session: CopilotSession) -> CopilotSessionRef:
    return CopilotSessionRef(
        native_session_id=session.native_session_id,
        events_path=session.events_path,
        source_ref_id=session.source_ref_id,
        updated_at=session.updated_at,
    )


def _merge_copilot_session(
    sessions_by_id: dict[str, CopilotSession],
    session: CopilotSession,
) -> None:
    existing = sessions_by_id.get(session.native_session_id)
    if existing is None:
        sessions_by_id[session.native_session_id] = session
        return
    sessions_by_id[session.native_session_id] = CopilotSession(
        native_session_id=session.native_session_id,
        events_path=existing.events_path,
        source_ref_id=existing.source_ref_id or session.source_ref_id,
        updated_at=_max_timestamp(existing.updated_at, session.updated_at),
    )


def _sort_copilot_sessions(sessions: tuple[CopilotSession, ...]) -> tuple[CopilotSession, ...]:
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


def _max_timestamp(*values: float | None) -> float | None:
    timestamps = [value for value in values if value is not None]
    if not timestamps:
        return None
    return max(timestamps)


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
    "CopilotSession",
    "CopilotSessionRef",
    "discover_copilot_session_refs",
    "discover_copilot_sessions",
    "find_copilot_sessions",
    "load_copilot_session",
]
