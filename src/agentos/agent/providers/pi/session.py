# $kw: ^agentos-provider-pi-session --from Agent.Navigable.Codebase --note [DF] provider-specific behavior lives beneath the agent provider namespace --supp ^c20260811-62u
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from agentos._core.sequences import _unique_paths
from agentos.agent.primitives import SessionSource
from agentos.agent.session_utils import (
    coalesce_timestamp as _coalesce_timestamp,
    coerce_timestamp as _coerce_timestamp,
    glob_paths as _glob_paths,
    safe_path_mtime as _safe_path_mtime,
    string_or_none as _string_or_none,
)


PI_PROVIDER = "pi"


@dataclass(frozen=True)
class PiSessionRef:
    native_session_id: str
    artifact_paths: tuple[Path, ...]
    cwd: str | None = None
    model_provider: str | None = None
    model_id: str | None = None
    thinking_level: str | None = None
    started_at: float | None = None
    updated_at: float | None = None

    @property
    def provider(self) -> str:
        return PI_PROVIDER

    def matches_query(self, query: str) -> bool:
        return query == self.native_session_id

    def display_name(self) -> str | None:
        return None

    def display_name_field(self) -> str | None:
        return None

    def native_ref_metadata(self) -> dict[str, object]:
        payload: dict[str, object] = {}
        if self.cwd is not None:
            payload["cwd"] = self.cwd
        if self.model_provider is not None:
            payload["model_provider"] = self.model_provider
        if self.model_id is not None:
            payload["model_id"] = self.model_id
        if self.thinking_level is not None:
            payload["thinking_level"] = self.thinking_level
        return payload

    def sort_timestamp(self) -> float | None:
        return _coalesce_timestamp(
            self.updated_at,
            self.started_at,
            *(_safe_path_mtime(path) for path in self.artifact_paths),
        )

    def to_session(self) -> "PiSession":
        return PiSession(
            native_session_id=self.native_session_id,
            artifact_paths=self.artifact_paths,
            cwd=self.cwd,
            model_provider=self.model_provider,
            model_id=self.model_id,
            thinking_level=self.thinking_level,
            started_at=self.started_at,
            updated_at=self.updated_at,
        )


@dataclass(frozen=True)
class PiSession:
    native_session_id: str
    artifact_paths: tuple[Path, ...]
    cwd: str | None = None
    model_provider: str | None = None
    model_id: str | None = None
    thinking_level: str | None = None
    started_at: float | None = None
    updated_at: float | None = None

    @property
    def provider(self) -> str:
        return PI_PROVIDER

    def sources(self) -> tuple[SessionSource, ...]:
        return tuple(
            SessionSource(role="transcript", path=path)
            for path in self.artifact_paths
        )

    def created_timestamp(self) -> float | None:
        return self.started_at

    def merge(self, other: PiSession) -> PiSession:
        if self.native_session_id != other.native_session_id:
            raise TypeError(f"cannot merge Pi sessions: {self.native_session_id} != {other.native_session_id}")

        return PiSession(
            native_session_id=self.native_session_id,
            artifact_paths=_unique_paths(self.artifact_paths + other.artifact_paths),
            cwd=self.cwd if self.cwd == other.cwd else self.cwd or other.cwd,
            model_provider=(
                self.model_provider
                if self.model_provider == other.model_provider
                else self.model_provider or other.model_provider
            ),
            model_id=self.model_id if self.model_id == other.model_id else self.model_id or other.model_id,
            thinking_level=(
                self.thinking_level
                if self.thinking_level == other.thinking_level
                else self.thinking_level or other.thinking_level
            ),
            started_at=_earliest_timestamp(self.started_at, other.started_at),
            updated_at=_coalesce_timestamp(self.updated_at, other.updated_at),
        )


def discover_pi_sessions(*, targets: tuple[Path, ...]) -> tuple[PiSession, ...]:
    sessions_by_id: dict[str, PiSession] = {}

    for target in targets:
        for path in _glob_paths(target, "**/*.jsonl"):
            session = read_pi_session(path)
            if session is not None:
                _merge_pi_session(sessions_by_id, session)

    return _sort_pi_sessions(tuple(sessions_by_id.values()))


def discover_pi_session_refs(*, targets: tuple[Path, ...]) -> tuple[PiSessionRef, ...]:
    return tuple(
        _pi_session_ref_from_session(session)
        for session in discover_pi_sessions(targets=targets)
    )


def find_pi_sessions(*, targets: tuple[Path, ...], query: str) -> tuple[PiSession, ...]:
    sessions_by_id: dict[str, PiSession] = {}
    for session_ref in discover_pi_session_refs(targets=targets):
        if session_ref.matches_query(query):
            session = session_ref.to_session()
            _merge_pi_session(sessions_by_id, session)
    return _sort_pi_sessions(tuple(sessions_by_id.values()))


def load_pi_session(session_ref: PiSessionRef) -> PiSession:
    return session_ref.to_session()


def read_pi_session(path: Path) -> PiSession | None:
    first_obj = _read_first_jsonl_object(path)
    if first_obj is None or first_obj.get("type") != "session":
        return None

    session_id = _string_or_none(first_obj.get("id"))
    if session_id is None:
        return None

    if not _has_pi_session_signature(path):
        return None

    cwd = _string_or_none(first_obj.get("cwd"))
    started_at = _coerce_timestamp(first_obj.get("timestamp"))
    updated_at = _safe_path_mtime(path) or started_at
    model_provider: str | None = None
    model_id: str | None = None
    thinking_level: str | None = None

    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                obj = _json_line_object(line)
                if obj is None:
                    continue

                record_type = obj.get("type")
                if record_type == "model_change" and (model_provider is None or model_id is None):
                    provider = _string_or_none(obj.get("provider"))
                    candidate_model_id = _string_or_none(obj.get("modelId"))
                    model_provider = model_provider or provider
                    model_id = model_id or candidate_model_id
                    continue

                if record_type == "thinking_level_change" and thinking_level is None:
                    thinking_level = _string_or_none(obj.get("thinkingLevel"))
    except OSError:
        return None

    return PiSession(
        native_session_id=session_id,
        artifact_paths=(path,),
        cwd=cwd,
        model_provider=model_provider,
        model_id=model_id,
        thinking_level=thinking_level,
        started_at=started_at,
        updated_at=updated_at,
    )


def _pi_session_ref_from_session(session: PiSession) -> PiSessionRef:
    return PiSessionRef(
        native_session_id=session.native_session_id,
        artifact_paths=session.artifact_paths,
        cwd=session.cwd,
        model_provider=session.model_provider,
        model_id=session.model_id,
        thinking_level=session.thinking_level,
        started_at=session.started_at,
        updated_at=session.updated_at,
    )


def _has_pi_session_signature(path: Path) -> bool:
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                obj = _json_line_object(line)
                if obj is None:
                    continue

                record_type = obj.get("type")
                if record_type == "model_change":
                    provider = _string_or_none(obj.get("provider"))
                    model_id = _string_or_none(obj.get("modelId"))
                    if provider is not None and model_id is not None:
                        return True
                    continue

                if record_type == "thinking_level_change" and _string_or_none(obj.get("thinkingLevel")) is not None:
                    return True

                if record_type == "custom_message":
                    return True

                if record_type != "message":
                    continue

                message = obj.get("message")
                if not isinstance(message, dict):
                    continue
                if message.get("role") == "toolResult":
                    return True
                metadata = message.get("metadata")
                if isinstance(metadata, dict) and metadata:
                    return True
                content = message.get("content")
                if not isinstance(content, list):
                    continue
                for item in content:
                    if isinstance(item, dict) and item.get("type") in {"thinking", "toolCall"}:
                        return True
    except OSError:
        return False

    return False


def _read_first_jsonl_object(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                obj = _json_line_object(line)
                if obj is not None:
                    return obj
    except OSError:
        return None

    return None


def _json_line_object(line: str) -> dict[str, Any] | None:
    line = line.strip()
    if not line:
        return None
    try:
        obj = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    return obj


def _merge_pi_session(sessions_by_id: dict[str, PiSession], session: PiSession) -> None:
    existing = sessions_by_id.get(session.native_session_id)
    if existing is None:
        sessions_by_id[session.native_session_id] = session
        return
    sessions_by_id[session.native_session_id] = existing.merge(session)


def _sort_pi_sessions(sessions: tuple[PiSession, ...]) -> tuple[PiSession, ...]:
    return tuple(sorted(sessions, key=lambda session: session.native_session_id))


def _earliest_timestamp(*values: float | None) -> float | None:
    timestamps = [value for value in values if value is not None]
    if not timestamps:
        return None
    return min(timestamps)


__all__ = [
    "PiSession",
    "PiSessionRef",
    "discover_pi_session_refs",
    "discover_pi_sessions",
    "find_pi_sessions",
    "load_pi_session",
    "read_pi_session",
]
