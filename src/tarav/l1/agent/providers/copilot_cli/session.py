from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from tarav.l0._core.errors import CliError
from tarav.l1.agent.primitives import SessionSource
from tarav.l1.agent.session_utils import (
    coalesce_timestamp as _max_timestamp,
    coerce_timestamp as _coerce_timestamp,
    primary_transcript_artifact as _primary_transcript_artifact,
    safe_path_mtime as _safe_path_mtime,
    source_ref_id_for_artifact as _source_ref_id_for_artifact,
    string_or_none as _string_or_none,
)


COPILOT_PROVIDER = "copilot-cli"


@dataclass(frozen=True)
class CopilotSessionRef:
    native_session_id: str
    events_path: Path
    source_ref_id: str | None = None
    project_path: str | None = None
    updated_at: float | None = None

    @property
    def provider(self) -> str:
        return COPILOT_PROVIDER

    def display_name(self) -> str | None:
        return None

    def display_name_field(self) -> str | None:
        return None

    def native_ref_metadata(self) -> dict[str, object]:
        if self.project_path is None:
            return {}
        return {"project_path": self.project_path}

    def sort_timestamp(self) -> float | None:
        event_ts = self.to_session().last_activity_timestamp()
        if event_ts is not None:
            return event_ts
        return _max_timestamp(
            self.updated_at,
            _safe_path_mtime(self.events_path),
        )

    def to_session(self) -> "CopilotSession":
        return CopilotSession(
            native_session_id=self.native_session_id,
            events_path=self.events_path,
            source_ref_id=self.source_ref_id,
            project_path=self.project_path,
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
    project_path: str | None = None
    updated_at: float | None = None

    @property
    def provider(self) -> str:
        return COPILOT_PROVIDER

    def sources(self) -> tuple[SessionSource, ...]:
        sources = [SessionSource(role="transcript", path=self.events_path)]
        if self.events_path.name == "events.jsonl":
            sources.append(
                SessionSource(
                    role="session_root",
                    path=self.events_path.parent,
                    storage_kind="directory",
                )
            )
        return tuple(sources)

    def created_timestamp(self) -> float | None:
        if not self.events_path.exists():
            return None

        try:
            from tarav.l1.agent.providers.copilot_cli.extractor import load_copilot_cli_events

            events = load_copilot_cli_events(self.events_path)
            first_event_timestamp: float | None = None
            for event in events:
                timestamp = _coerce_timestamp(event.get("timestamp"))
                if timestamp is not None and first_event_timestamp is None:
                    first_event_timestamp = timestamp
                if event.get("type") == "session.start":
                    return timestamp
            return first_event_timestamp
        except (CliError, OSError):
            return None

    def last_activity_timestamp(self) -> float | None:
        if not self.events_path.exists():
            return None
        try:
            from tarav.l1.agent.providers.copilot_cli.extractor import load_copilot_cli_events

            latest: float | None = None
            for event in load_copilot_cli_events(self.events_path):
                ts = _coerce_timestamp(event.get("timestamp"))
                if ts is not None and (latest is None or ts > latest):
                    latest = ts
            return latest
        except (CliError, OSError):
            return None

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
            project_path=_string_or_none(_native_payload(session).get("project_path")),
            updated_at=_coerce_timestamp(session.get("last_activity_at")),
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


def find_copilot_session_ref_by_id(*, targets: tuple[Path, ...], session_id: str) -> CopilotSessionRef | None:
    for target in targets:
        if not target.is_dir():
            if target.is_file() and target.stem == session_id and target.suffix == ".jsonl":
                session = read_copilot_session(target)
                if session is not None:
                    return _copilot_session_ref_from_session(session)
            continue
        dir_candidate = target / session_id
        if dir_candidate.is_dir():
            session = read_copilot_session(dir_candidate)
            if session is not None:
                return _copilot_session_ref_from_session(session)
        file_candidate = target / f"{session_id}.jsonl"
        if file_candidate.is_file():
            session = read_copilot_session(file_candidate)
            if session is not None:
                return _copilot_session_ref_from_session(session)
    return None


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
            project_path=_read_copilot_project_path(events_path),
            updated_at=_safe_path_mtime(events_path) or _safe_path_mtime(path),
        )

    if path.is_file() and path.suffix == ".jsonl":
        return CopilotSession(
            native_session_id=path.stem,
            events_path=path,
            project_path=_read_copilot_project_path(path),
            updated_at=_safe_path_mtime(path),
        )

    return None


def _copilot_session_ref_from_session(session: CopilotSession) -> CopilotSessionRef:
    return CopilotSessionRef(
        native_session_id=session.native_session_id,
        events_path=session.events_path,
        source_ref_id=session.source_ref_id,
        project_path=session.project_path,
        updated_at=session.updated_at,
    )


def _native_payload(session: dict[str, Any]) -> dict[str, object]:
    native = session.get("native")
    if isinstance(native, dict):
        return native
    return {}


def _read_copilot_project_path(events_path: Path) -> str | None:
    try:
        with events_path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(obj, dict) or obj.get("type") != "session.start":
                    continue
                data = obj.get("data")
                if not isinstance(data, dict):
                    return None
                context = data.get("context")
                if not isinstance(context, dict):
                    return None
                return _string_or_none(context.get("gitRoot")) or _string_or_none(context.get("cwd"))
    except OSError:
        return None
    return None


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
        project_path=existing.project_path or session.project_path,
        updated_at=_max_timestamp(existing.updated_at, session.updated_at),
    )


def _sort_copilot_sessions(sessions: tuple[CopilotSession, ...]) -> tuple[CopilotSession, ...]:
    return tuple(sorted(sessions, key=lambda session: session.native_session_id))


__all__ = [
    "CopilotSession",
    "CopilotSessionRef",
    "discover_copilot_session_refs",
    "discover_copilot_sessions",
    "find_copilot_sessions",
    "load_copilot_session",
]
