# $kw: ^agentos-provider-claude-code-session --from Agent.Navigable.Codebase --note [DF] provider-specific behavior lives beneath the agent provider namespace --supp ^c20260811-62u
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from tarav.l0._core.errors import CliError
from tarav.l1.agent.primitives import SessionSource
from tarav.l1.agent.session_utils import (
    coerce_timestamp as _coerce_timestamp,
    created_timestamp_from_turns as _created_timestamp_from_turns,
    glob_paths as _glob_paths,
    primary_source_path as _primary_source_path,
    primary_transcript_artifact as _primary_transcript_artifact,
    safe_path_mtime as _safe_path_mtime,
    source_ref_id_for_artifact as _source_ref_id_for_artifact,
    string_or_none as _string_or_none,
)


CLAUDE_PROVIDER = "claude-code"


@dataclass(frozen=True)
class ClaudeSessionRef:
    native_session_id: str
    artifact_paths: tuple[Path, ...]
    source_ref_id: str | None = None
    title: str | None = None
    cwd: str | None = None
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

    def display_name(self) -> str | None:
        return self.title

    def display_name_field(self) -> str | None:
        if self.title is None:
            return None
        return "title"

    def native_ref_metadata(self) -> dict[str, object]:
        payload: dict[str, object] = {}
        if self.title is not None:
            payload["title"] = self.title
        if self.cwd is not None:
            payload["cwd"] = self.cwd
        return payload

    def sort_timestamp(self) -> float | None:
        return _coalesce_timestamp(
            _coerce_timestamp(self.updated_at),
            *(_safe_path_mtime(path) for path in self.artifact_paths),
        )

    def to_session(self) -> "ClaudeSession":
        return ClaudeSession(
            native_session_id=self.native_session_id,
            artifact_paths=self.artifact_paths,
            source_ref_id=self.source_ref_id,
            title=self.title,
            cwd=self.cwd,
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
    cwd: str | None = None
    source_kind: str = "project"
    updated_at: float | str | None = None

    @property
    def provider(self) -> str:
        return CLAUDE_PROVIDER

    @property
    def transcript_path(self) -> Path:
        return self.artifact_paths[0]

    def sources(self) -> tuple[SessionSource, ...]:
        return tuple(
            SessionSource(
                role="transcript" if path.suffix == ".jsonl" else "metadata",
                path=path,
            )
            for path in self.artifact_paths
        )

    def created_timestamp(self) -> float | None:
        artifact = _primary_source_path(self.sources())
        if artifact is None or not artifact.exists():
            return None

        try:
            if artifact.suffix == ".jsonl":
                from tarav.l1.agent.providers.claude_code.extractor import (
                    extract_dialog_from_claude_code_session,
                )

                return _created_timestamp_from_turns(
                    extract_dialog_from_claude_code_session(artifact, raw=False)
                )
            if artifact.suffix == ".json":
                obj = json.loads(artifact.read_text(encoding="utf-8", errors="ignore"))
                if isinstance(obj, dict):
                    return _coerce_timestamp(obj.get("createdAt")) or _coerce_timestamp(
                        obj.get("lastActivityAt")
                    )
        except (CliError, OSError, json.JSONDecodeError):
            return None
        return None

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
            cwd=_string_or_none(_native_payload(session).get("cwd")),
            updated_at=_string_or_none(session.get("last_activity_at")),
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
            cwd=self.cwd or other.cwd,
            source_kind=source_kind,
            updated_at=_coalesce_timestamp(self.updated_at, other.updated_at),
        )


def discover_claude_sessions(*, targets: tuple[Path, ...]) -> tuple[ClaudeSession, ...]:
    sessions_by_id: dict[str, ClaudeSession] = {}

    for target in targets:
        for path in _glob_paths(target, "**/*.jsonl"):
            session = read_claude_project_session(path)
            if session is not None:
                _merge_claude_session(sessions_by_id, session)

    return _sort_claude_sessions(tuple(sessions_by_id.values()))


def discover_claude_session_refs(*, targets: tuple[Path, ...]) -> tuple[ClaudeSessionRef, ...]:
    return tuple(
        _claude_session_ref_from_session(session)
        for session in discover_claude_sessions(targets=targets)
    )


def find_claude_session_ref_by_id(*, targets: tuple[Path, ...], session_id: str) -> ClaudeSessionRef | None:
    filename = f"{session_id}.jsonl"
    for target in targets:
        if target.is_file() and target.name == filename:
            session = read_claude_project_session(target)
            if session is not None:
                return _claude_session_ref_from_session(session)
            continue
        if not target.is_dir():
            continue
        for match in sorted(target.rglob(filename)):
            if not match.is_file():
                continue
            session = read_claude_project_session(match)
            if session is not None:
                return _claude_session_ref_from_session(session)
    return None


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
        cwd=_string_or_none(first_obj.get("cwd")) if first_obj is not None else None,
        source_kind="project",
        updated_at=updated_at,
    )


def _claude_session_ref_from_session(session: ClaudeSession) -> ClaudeSessionRef:
    return ClaudeSessionRef(
        native_session_id=session.native_session_id,
        artifact_paths=session.artifact_paths,
        source_ref_id=session.source_ref_id,
        title=session.title,
        cwd=session.cwd,
        source_kind=session.source_kind,
        updated_at=session.updated_at,
    )


def _native_payload(session: dict[str, Any]) -> dict[str, object]:
    native = session.get("native")
    if isinstance(native, dict):
        return native
    return {}


def _is_claude_project_session_artifact(path: Path) -> bool:
    if path.suffix != ".jsonl":
        return False
    return "subagents" not in path.parts


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


__all__ = [
    "ClaudeSession",
    "ClaudeSessionRef",
    "discover_claude_session_refs",
    "discover_claude_sessions",
    "find_claude_sessions",
    "load_claude_session",
    "read_claude_project_session",
]
