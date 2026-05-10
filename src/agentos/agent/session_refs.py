from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from agentos._core.errors import CliError
from agentos.claude.session import ClaudeSessionRef
from agentos.codex.session import CodexSessionRef
from agentos.copilot.session import CopilotSessionRef
from agentos.gemini.session import GeminiSessionRef
from agentos.openclaw.session import OpenclawSessionRef
from agentos.opencode.session import OpencodeSessionRef
from agentos.pi.session import PiSessionRef


ProviderSessionRef = (
    ClaudeSessionRef
    | CodexSessionRef
    | CopilotSessionRef
    | GeminiSessionRef
    | OpenclawSessionRef
    | OpencodeSessionRef
    | PiSessionRef
)


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


def _coalesce_timestamp(*values: float | None) -> float | None:
    timestamps = [value for value in values if value is not None]
    if not timestamps:
        return None
    return max(timestamps)


def _build_path_finding(
    *,
    provider: str,
    path: Path,
) -> dict[str, Any]:
    return {
        "provider": provider,
        "strategy": "path",
        "match_kind": "directory" if path.is_dir() else "file",
        "path": str(path),
    }


@dataclass(frozen=True)
class BackingArtifact:
    role: str
    path: Path
    storage_kind: str | None = None
    locator: dict[str, Any] | None = None

    def normalized_storage_kind(self) -> str:
        if self.storage_kind is not None:
            return self.storage_kind
        if self.path.is_dir():
            return "directory"
        return "file"

    def summary(self, *, extractable: bool) -> dict[str, Any]:
        return {
            "role": self.role,
            "storage_kind": self.normalized_storage_kind(),
            "path": str(self.path),
            "locator": self.locator,
            "extractable": extractable,
        }


def session_ref_id(session_ref: ProviderSessionRef) -> str:
    return session_ref.native_session_id


def session_ref_backing_artifacts(session_ref: ProviderSessionRef) -> tuple[BackingArtifact, ...]:
    if isinstance(session_ref, ClaudeSessionRef):
        return tuple(
            BackingArtifact(
                role="transcript" if path.suffix == ".jsonl" else "metadata",
                path=path,
            )
            for path in session_ref.artifact_paths
        )
    if isinstance(session_ref, CodexSessionRef):
        artifacts = [
            BackingArtifact(role="transcript", path=path)
            for path in session_ref.rollout_paths
        ]
        artifacts.extend(
            BackingArtifact(
                role="session_index",
                path=path,
                locator={
                    "kind": "jsonl_record_match",
                    "match": {"id": session_ref.native_session_id},
                },
            )
            for path in session_ref.index_paths
        )
        return tuple(artifacts)
    if isinstance(session_ref, CopilotSessionRef):
        artifacts = [BackingArtifact(role="transcript", path=session_ref.events_path)]
        if session_ref.events_path.name == "events.jsonl":
            artifacts.append(
                BackingArtifact(
                    role="session_root",
                    path=session_ref.events_path.parent,
                    storage_kind="directory",
                )
            )
        return tuple(artifacts)
    if isinstance(session_ref, GeminiSessionRef):
        return tuple(
            BackingArtifact(role="transcript", path=path)
            for path in session_ref.artifact_paths
        )
    if isinstance(session_ref, PiSessionRef):
        return tuple(
            BackingArtifact(role="transcript", path=path)
            for path in session_ref.artifact_paths
        )
    if isinstance(session_ref, OpenclawSessionRef):
        artifacts: list[BackingArtifact] = []
        if session_ref.transcript_path is not None:
            artifacts.append(
                BackingArtifact(role="transcript", path=session_ref.transcript_path)
            )
        if session_ref.sessions_index_path is not None:
            locator: dict[str, Any]
            if session_ref.session_keys:
                locator = {
                    "kind": "json_object_keys",
                    "keys": list(session_ref.session_keys),
                }
            else:
                locator = {
                    "kind": "json_object_value_match",
                    "match": {"sessionId": session_ref.native_session_id},
                }
            artifacts.append(
                BackingArtifact(
                    role="session_index",
                    path=session_ref.sessions_index_path,
                    locator=locator,
                )
            )
        return tuple(artifacts)
    if isinstance(session_ref, OpencodeSessionRef):
        artifacts = []
        if session_ref.diff_path is not None:
            artifacts.append(
                BackingArtifact(role="session_diff", path=session_ref.diff_path)
            )
        if session_ref.sqlite_db_path is not None:
            artifacts.append(
                BackingArtifact(
                    role="sqlite_session_row",
                    path=session_ref.sqlite_db_path,
                    storage_kind="sqlite_row",
                    locator={
                        "kind": "sqlite_row_match",
                        "table": "session",
                        "key": {"id": session_ref.native_session_id},
                    },
                )
            )
        return tuple(artifacts)
    return ()


def session_ref_display_name(session_ref: ProviderSessionRef) -> str | None:
    if isinstance(session_ref, ClaudeSessionRef):
        return session_ref.title
    if isinstance(session_ref, CodexSessionRef):
        return session_ref.thread_name
    return None


def session_ref_display_name_field(session_ref: ProviderSessionRef) -> str | None:
    if isinstance(session_ref, ClaudeSessionRef) and session_ref.title is not None:
        return "title"
    if isinstance(session_ref, CodexSessionRef) and session_ref.thread_name is not None:
        return "thread_name"
    return None


def session_ref_native_payload(session_ref: ProviderSessionRef) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if isinstance(session_ref, ClaudeSessionRef) and session_ref.title is not None:
        payload["title"] = session_ref.title
    if isinstance(session_ref, CodexSessionRef) and session_ref.thread_name is not None:
        payload["thread_name"] = session_ref.thread_name
    if isinstance(session_ref, PiSessionRef):
        if session_ref.cwd is not None:
            payload["cwd"] = session_ref.cwd
        if session_ref.model_provider is not None:
            payload["model_provider"] = session_ref.model_provider
        if session_ref.model_id is not None:
            payload["model_id"] = session_ref.model_id
        if session_ref.thinking_level is not None:
            payload["thinking_level"] = session_ref.thinking_level
    if isinstance(session_ref, OpenclawSessionRef):
        if session_ref.session_keys:
            payload["session_keys"] = list(session_ref.session_keys)
        if session_ref.agent_id is not None:
            payload["agent_id"] = session_ref.agent_id
    return payload


def session_ref_created_timestamp(session_ref: ProviderSessionRef) -> float | None:
    if isinstance(session_ref, PiSessionRef):
        return session_ref.started_at

    backing_artifacts = session_ref_backing_artifacts(session_ref)
    if not backing_artifacts:
        return None
    artifact = backing_artifacts[0].path
    if not artifact.exists():
        return None

    try:
        if isinstance(session_ref, CodexSessionRef):
            from agentos.agent.extractors.codex import extract_dialog_from_codex_rollout

            return _created_timestamp_from_turns(
                extract_dialog_from_codex_rollout(artifact, raw=False)
            )
        if isinstance(session_ref, ClaudeSessionRef):
            if artifact.suffix == ".jsonl":
                from agentos.agent.extractors.claude_code import (
                    extract_dialog_from_claude_code_session,
                )

                return _created_timestamp_from_turns(
                    extract_dialog_from_claude_code_session(artifact, raw=False)
                )
            if artifact.suffix == ".json":
                obj = json.loads(artifact.read_text(encoding="utf-8", errors="ignore"))
                if isinstance(obj, dict):
                    return coerce_timestamp(obj.get("createdAt")) or coerce_timestamp(
                        obj.get("lastActivityAt")
                    )
        if isinstance(session_ref, CopilotSessionRef):
            from agentos.agent.extractors.copilot_cli import load_copilot_cli_events

            events = load_copilot_cli_events(artifact)
            first_event_timestamp: float | None = None
            for event in events:
                timestamp = coerce_timestamp(event.get("timestamp"))
                if timestamp is not None and first_event_timestamp is None:
                    first_event_timestamp = timestamp
                if event.get("type") == "session.start":
                    return timestamp
            return first_event_timestamp
        if isinstance(session_ref, GeminiSessionRef):
            from agentos.agent.extractors.gemini_cli import load_gemini_cli_session_data

            session_data = load_gemini_cli_session_data(artifact)
            if isinstance(session_data, dict):
                return coerce_timestamp(session_data.get("startTime"))
        if isinstance(session_ref, OpenclawSessionRef):
            from agentos.agent.extractors.openclaw import load_openclaw_session_records

            records = load_openclaw_session_records(artifact)
            if records:
                return coerce_timestamp(records[0].get("timestamp"))
        if isinstance(session_ref, OpencodeSessionRef):
            from agentos.agent.extractors.opencode import (
                load_opencode_session_messages,
                resolve_opencode_db_path,
            )

            db_path = (
                artifact
                if artifact.name == "opencode.db"
                else resolve_opencode_db_path(artifact)
            )
            messages = load_opencode_session_messages(
                db_path=db_path,
                session_id=session_ref.native_session_id,
            )
            if messages:
                return coerce_timestamp(messages[0].get("time_created"))
    except (CliError, OSError, json.JSONDecodeError):
        return None
    return None


def _created_timestamp_from_turns(turns: list[Any]) -> float | None:
    for turn in turns:
        timestamp = coerce_timestamp(getattr(turn, "timestamp", None))
        if timestamp is not None:
            return timestamp
    return None


def session_ref_sort_timestamp(session_ref: ProviderSessionRef) -> float | None:
    if isinstance(session_ref, ClaudeSessionRef):
        return _coalesce_timestamp(
            coerce_timestamp(session_ref.updated_at),
            *(safe_path_mtime(path) for path in session_ref.artifact_paths),
        )
    if isinstance(session_ref, CodexSessionRef):
        return _coalesce_timestamp(
            session_ref.updated_at,
            *(safe_path_mtime(path) for path in session_ref.rollout_paths),
        )
    if isinstance(session_ref, CopilotSessionRef):
        return _coalesce_timestamp(
            session_ref.updated_at,
            safe_path_mtime(session_ref.events_path),
            safe_path_mtime(session_ref.events_path.parent),
        )
    if isinstance(session_ref, GeminiSessionRef):
        return _coalesce_timestamp(
            session_ref.updated_at,
            *(safe_path_mtime(path) for path in session_ref.artifact_paths),
        )
    if isinstance(session_ref, PiSessionRef):
        return _coalesce_timestamp(
            session_ref.updated_at,
            session_ref.started_at,
            *(safe_path_mtime(path) for path in session_ref.artifact_paths),
        )
    if isinstance(session_ref, OpenclawSessionRef):
        return _coalesce_timestamp(
            session_ref.updated_at,
            safe_path_mtime(session_ref.transcript_path),
            safe_path_mtime(session_ref.sessions_index_path),
        )
    if isinstance(session_ref, OpencodeSessionRef):
        return _coalesce_timestamp(
            session_ref.updated_at,
            safe_path_mtime(session_ref.diff_path),
            safe_path_mtime(session_ref.sqlite_db_path),
        )
    return None


__all__ = [
    "BackingArtifact",
    "ProviderSessionRef",
    "_build_path_finding",
    "_coalesce_timestamp",
    "coerce_timestamp",
    "safe_path_mtime",
    "session_ref_backing_artifacts",
    "session_ref_created_timestamp",
    "session_ref_display_name",
    "session_ref_display_name_field",
    "session_ref_id",
    "session_ref_native_payload",
    "session_ref_sort_timestamp",
]
