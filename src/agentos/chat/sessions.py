from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


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


def _unique_paths(paths: tuple[Path, ...]) -> tuple[Path, ...]:
    unique_paths: list[Path] = []
    seen_paths: set[Path] = set()

    for path in paths:
        if path in seen_paths:
            continue
        seen_paths.add(path)
        unique_paths.append(path)

    return tuple(unique_paths)


def _unique_strings(values: tuple[str, ...]) -> tuple[str, ...]:
    unique_values: list[str] = []
    seen_values: set[str] = set()

    for value in values:
        if value in seen_values:
            continue
        seen_values.add(value)
        unique_values.append(value)

    return tuple(unique_values)


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
class ChatSession:
    provider: str
    session_id: str

    def canonical_findings(self) -> tuple[dict[str, Any], ...]:
        return ()

    def primary_artifact_path(self) -> Path | None:
        return None

    def sort_timestamp(self) -> float | None:
        return None

    def merge(self, other: ChatSession) -> ChatSession:
        raise TypeError(f"cannot merge {type(self).__name__} with {type(other).__name__}")


@dataclass(frozen=True)
class ClaudeCodeChatSession(ChatSession):
    artifact_paths: tuple[Path, ...]
    source_kind: str = "project"
    title: str | None = None
    updated_at: float | None = None
    provider: str = field(default="claude-code", init=False)

    def canonical_findings(self) -> tuple[dict[str, Any], ...]:
        return tuple(_build_path_finding(provider=self.provider, path=path) for path in self.artifact_paths)

    def primary_artifact_path(self) -> Path | None:
        if not self.artifact_paths:
            return None
        return self.artifact_paths[0]

    def sort_timestamp(self) -> float | None:
        return _coalesce_timestamp(
            self.updated_at,
            *(safe_path_mtime(path) for path in self.artifact_paths),
        )

    def merge(self, other: ChatSession) -> ChatSession:
        if not isinstance(other, ClaudeCodeChatSession) or other.session_id != self.session_id:
            return super().merge(other)

        source_kind = self.source_kind if self.source_kind == other.source_kind else "mixed"
        return ClaudeCodeChatSession(
            session_id=self.session_id,
            artifact_paths=_unique_paths(self.artifact_paths + other.artifact_paths),
            source_kind=source_kind,
            title=self.title or other.title,
            updated_at=_coalesce_timestamp(self.updated_at, other.updated_at),
        )


@dataclass(frozen=True)
class CodexChatSession(ChatSession):
    artifact_paths: tuple[Path, ...] = ()
    thread_name: str | None = None
    index_paths: tuple[Path, ...] = ()
    updated_at: float | None = None
    provider: str = field(default="codex", init=False)

    def canonical_findings(self) -> tuple[dict[str, Any], ...]:
        return tuple(_build_path_finding(provider=self.provider, path=path) for path in self.artifact_paths)

    def primary_artifact_path(self) -> Path | None:
        if not self.artifact_paths:
            return None
        return self.artifact_paths[0]

    def sort_timestamp(self) -> float | None:
        return _coalesce_timestamp(
            self.updated_at,
            *(safe_path_mtime(path) for path in self.artifact_paths),
        )

    def merge(self, other: ChatSession) -> ChatSession:
        if not isinstance(other, CodexChatSession) or other.session_id != self.session_id:
            return super().merge(other)

        return CodexChatSession(
            session_id=self.session_id,
            artifact_paths=_unique_paths(self.artifact_paths + other.artifact_paths),
            thread_name=self.thread_name or other.thread_name,
            index_paths=_unique_paths(self.index_paths + other.index_paths),
            updated_at=_coalesce_timestamp(self.updated_at, other.updated_at),
        )


@dataclass(frozen=True)
class CopilotCliChatSession(ChatSession):
    session_root: Path | None = None
    session_file: Path | None = None
    updated_at: float | None = None
    provider: str = field(default="copilot-cli", init=False)

    def canonical_findings(self) -> tuple[dict[str, Any], ...]:
        findings: list[dict[str, Any]] = []
        if self.session_root is not None:
            findings.append(_build_path_finding(provider=self.provider, path=self.session_root))
        if self.session_file is not None:
            findings.append(_build_path_finding(provider=self.provider, path=self.session_file))
        return tuple(findings)

    def primary_artifact_path(self) -> Path | None:
        if self.session_file is not None:
            return self.session_file
        if self.session_root is None:
            return None

        events_path = self.session_root / "events.jsonl"
        if events_path.is_file():
            return events_path
        return None

    def sort_timestamp(self) -> float | None:
        return _coalesce_timestamp(
            self.updated_at,
            safe_path_mtime(self.session_file),
            safe_path_mtime(self.session_root),
        )

    def merge(self, other: ChatSession) -> ChatSession:
        if not isinstance(other, CopilotCliChatSession) or other.session_id != self.session_id:
            return super().merge(other)

        return CopilotCliChatSession(
            session_id=self.session_id,
            session_root=self.session_root or other.session_root,
            session_file=self.session_file or other.session_file,
            updated_at=_coalesce_timestamp(self.updated_at, other.updated_at),
        )


@dataclass(frozen=True)
class GeminiCliChatSession(ChatSession):
    artifact_paths: tuple[Path, ...]
    updated_at: float | None = None
    provider: str = field(default="gemini-cli", init=False)

    def canonical_findings(self) -> tuple[dict[str, Any], ...]:
        return tuple(_build_path_finding(provider=self.provider, path=path) for path in self.artifact_paths)

    def primary_artifact_path(self) -> Path | None:
        if not self.artifact_paths:
            return None
        return self.artifact_paths[0]

    def sort_timestamp(self) -> float | None:
        return _coalesce_timestamp(
            self.updated_at,
            *(safe_path_mtime(path) for path in self.artifact_paths),
        )

    def merge(self, other: ChatSession) -> ChatSession:
        if not isinstance(other, GeminiCliChatSession) or other.session_id != self.session_id:
            return super().merge(other)

        return GeminiCliChatSession(
            session_id=self.session_id,
            artifact_paths=_unique_paths(self.artifact_paths + other.artifact_paths),
            updated_at=_coalesce_timestamp(self.updated_at, other.updated_at),
        )


@dataclass(frozen=True)
class OpenclawChatSession(ChatSession):
    transcript_path: Path | None = None
    sessions_index_path: Path | None = None
    session_keys: tuple[str, ...] = ()
    agent_id: str | None = None
    updated_at: float | None = None
    provider: str = field(default="openclaw", init=False)

    def canonical_findings(self) -> tuple[dict[str, Any], ...]:
        if self.transcript_path is not None:
            return (_build_path_finding(provider=self.provider, path=self.transcript_path),)
        if self.sessions_index_path is not None:
            return (_build_path_finding(provider=self.provider, path=self.sessions_index_path),)
        return ()

    def primary_artifact_path(self) -> Path | None:
        return self.transcript_path

    def sort_timestamp(self) -> float | None:
        return _coalesce_timestamp(
            self.updated_at,
            safe_path_mtime(self.transcript_path),
            safe_path_mtime(self.sessions_index_path),
        )

    def merge(self, other: ChatSession) -> ChatSession:
        if not isinstance(other, OpenclawChatSession) or other.session_id != self.session_id:
            return super().merge(other)

        agent_id = self.agent_id if self.agent_id == other.agent_id else self.agent_id or other.agent_id
        return OpenclawChatSession(
            session_id=self.session_id,
            transcript_path=self.transcript_path or other.transcript_path,
            sessions_index_path=self.sessions_index_path or other.sessions_index_path,
            session_keys=_unique_strings(self.session_keys + other.session_keys),
            agent_id=agent_id,
            updated_at=_coalesce_timestamp(self.updated_at, other.updated_at),
        )


@dataclass(frozen=True)
class OpencodeChatSession(ChatSession):
    diff_path: Path | None = None
    sqlite_db_path: Path | None = None
    updated_at: float | None = None
    provider: str = field(default="opencode", init=False)

    def canonical_findings(self) -> tuple[dict[str, Any], ...]:
        findings: list[dict[str, Any]] = []
        if self.diff_path is not None:
            findings.append(_build_path_finding(provider=self.provider, path=self.diff_path))
        if self.sqlite_db_path is not None:
            findings.append(
                {
                    "provider": self.provider,
                    "strategy": "sqlite",
                    "match_kind": "sqlite_row",
                    "path": str(self.sqlite_db_path),
                }
            )
        return tuple(findings)

    def primary_artifact_path(self) -> Path | None:
        return self.diff_path or self.sqlite_db_path

    def sort_timestamp(self) -> float | None:
        return _coalesce_timestamp(
            self.updated_at,
            safe_path_mtime(self.diff_path),
            safe_path_mtime(self.sqlite_db_path),
        )

    def merge(self, other: ChatSession) -> ChatSession:
        if not isinstance(other, OpencodeChatSession) or other.session_id != self.session_id:
            return super().merge(other)

        return OpencodeChatSession(
            session_id=self.session_id,
            diff_path=self.diff_path or other.diff_path,
            sqlite_db_path=self.sqlite_db_path or other.sqlite_db_path,
            updated_at=_coalesce_timestamp(self.updated_at, other.updated_at),
        )


__all__ = [
    "ChatSession",
    "ClaudeCodeChatSession",
    "CodexChatSession",
    "CopilotCliChatSession",
    "GeminiCliChatSession",
    "OpenclawChatSession",
    "OpencodeChatSession",
    "coerce_timestamp",
    "safe_path_mtime",
]
