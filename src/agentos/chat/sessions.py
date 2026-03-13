from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote


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
class ProviderInstance:
    family: str
    homes: tuple[tuple[str, Path], ...] = ()
    direct_targets: tuple[Path, ...] = ()
    grep_targets: tuple[Path, ...] = ()
    sqlite_db_paths: tuple[Path, ...] = ()
    is_default: bool = False

    def homes_map(self) -> dict[str, Path]:
        return {key: path for key, path in self.homes}

    def identity_key(self) -> tuple[object, ...]:
        return (
            self.family,
            tuple((key, str(path)) for key, path in self.homes),
            tuple(str(path) for path in self.direct_targets),
            tuple(str(path) for path in self.grep_targets),
            tuple(str(path) for path in self.sqlite_db_paths),
        )

    def summary(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "family": self.family,
            "is_default": self.is_default,
        }
        if self.homes:
            payload["homes"] = {key: str(path) for key, path in self.homes}
        if self.direct_targets:
            payload["direct_targets"] = [str(path) for path in self.direct_targets]
        if self.grep_targets:
            payload["grep_targets"] = [str(path) for path in self.grep_targets]
        if self.sqlite_db_paths:
            payload["sqlite_db_paths"] = [str(path) for path in self.sqlite_db_paths]
        return payload

    def uri_component(self) -> str:
        parts: list[str] = []
        if self.homes:
            parts.extend(f"home:{key}={path}" for key, path in self.homes)
        else:
            parts.extend(f"direct:{path}" for path in self.direct_targets)
            parts.extend(f"sqlite:{path}" for path in self.sqlite_db_paths)
        if not parts:
            parts.append(f"family:{self.family}")
        return quote("|".join(parts), safe="")


@dataclass(frozen=True)
class SessionSource:
    provider_instance: ProviderInstance
    native_session_id: str

    @property
    def provider_family(self) -> str:
        return self.provider_instance.family

    @property
    def provider(self) -> str:
        return self.provider_family

    @property
    def session_id(self) -> str:
        return self.native_session_id

    def source_identity_key(self) -> tuple[object, ...]:
        return (
            self.provider_family,
            self.provider_instance.identity_key(),
            self.native_session_id,
        )

    def canonical_findings(self) -> tuple[dict[str, Any], ...]:
        return ()

    def primary_artifact_path(self) -> Path | None:
        return None

    def sort_timestamp(self) -> float | None:
        return None

    def merge(self, other: SessionSource) -> SessionSource:
        raise TypeError(f"cannot merge {type(self).__name__} with {type(other).__name__}")

    def display_name(self) -> str | None:
        return None

    def display_name_field(self) -> str | None:
        return None

    def native_fields(self) -> dict[str, Any]:
        return {"session_id": self.native_session_id}

    def query_fields(self) -> tuple[tuple[str, str], ...]:
        return (("session_id", self.native_session_id),)

    def matches_query(self, query: str) -> bool:
        return any(value == query for _, value in self.query_fields())

    def matched_field(self, query: str) -> str:
        for field_name, value in self.query_fields():
            if value == query:
                return field_name
        return "query"

    def supplemental_findings(
        self,
        *,
        query: str,
        matched_field: str,
    ) -> tuple[dict[str, Any], ...]:
        return ()


def _merge_requires_same_identity(left: SessionSource, right: SessionSource) -> bool:
    return type(left) is type(right) and left.source_identity_key() == right.source_identity_key()


def _build_chat_session_uri(source: SessionSource) -> str:
    return (
        f"agentos://chat-session/{quote(source.provider_family, safe='')}/"
        f"{source.provider_instance.uri_component()}/"
        f"{quote(source.native_session_id, safe='')}"
    )


@dataclass(frozen=True)
class ChatSession:
    source: SessionSource

    @property
    def uri(self) -> str:
        return _build_chat_session_uri(self.source)

    @property
    def provider_family(self) -> str:
        return self.source.provider_family

    @property
    def provider_instance(self) -> ProviderInstance:
        return self.source.provider_instance

    @property
    def provider(self) -> str:
        return self.provider_family

    @property
    def session_id(self) -> str:
        return self.source.session_id

    def canonical_findings(self) -> tuple[dict[str, Any], ...]:
        return self.source.canonical_findings()

    def primary_artifact_path(self) -> Path | None:
        return self.source.primary_artifact_path()

    def sort_timestamp(self) -> float | None:
        return self.source.sort_timestamp()

    def merge(self, other: ChatSession) -> ChatSession:
        if self.uri != other.uri:
            raise TypeError(f"cannot merge distinct chat sessions: {self.uri} != {other.uri}")
        return ChatSession(source=self.source.merge(other.source))

    def display_name(self) -> str | None:
        return self.source.display_name()

    def display_name_field(self) -> str | None:
        return self.source.display_name_field()

    def native_fields(self) -> dict[str, Any]:
        return self.source.native_fields()

    def matches_query(self, query: str) -> bool:
        return self.source.matches_query(query)

    def matched_field(self, query: str) -> str:
        return self.source.matched_field(query)

    def supplemental_findings(
        self,
        *,
        query: str,
        matched_field: str,
    ) -> tuple[dict[str, Any], ...]:
        return self.source.supplemental_findings(query=query, matched_field=matched_field)


@dataclass(frozen=True)
class ClaudeCodeSessionSource(SessionSource):
    artifact_paths: tuple[Path, ...]
    source_kind: str = "project"
    title: str | None = None
    updated_at: float | None = None

    def canonical_findings(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            _build_path_finding(provider=self.provider_family, path=path) for path in self.artifact_paths
        )

    def primary_artifact_path(self) -> Path | None:
        if not self.artifact_paths:
            return None
        return self.artifact_paths[0]

    def sort_timestamp(self) -> float | None:
        return _coalesce_timestamp(
            self.updated_at,
            *(safe_path_mtime(path) for path in self.artifact_paths),
        )

    def merge(self, other: SessionSource) -> SessionSource:
        if not _merge_requires_same_identity(self, other):
            return super().merge(other)
        assert isinstance(other, ClaudeCodeSessionSource)

        source_kind = self.source_kind if self.source_kind == other.source_kind else "mixed"
        return ClaudeCodeSessionSource(
            provider_instance=self.provider_instance,
            native_session_id=self.native_session_id,
            artifact_paths=_unique_paths(self.artifact_paths + other.artifact_paths),
            source_kind=source_kind,
            title=self.title or other.title,
            updated_at=_coalesce_timestamp(self.updated_at, other.updated_at),
        )

    def display_name(self) -> str | None:
        return self.title

    def display_name_field(self) -> str | None:
        if self.title is None:
            return None
        return "title"

    def native_fields(self) -> dict[str, Any]:
        payload = super().native_fields()
        if self.title is not None:
            payload["title"] = self.title
        return payload

    def query_fields(self) -> tuple[tuple[str, str], ...]:
        fields = list(super().query_fields())
        if self.title is not None:
            fields.append(("title", self.title))
        return tuple(fields)


@dataclass(frozen=True)
class CodexSessionSource(SessionSource):
    artifact_paths: tuple[Path, ...] = ()
    thread_name: str | None = None
    index_paths: tuple[Path, ...] = ()
    updated_at: float | None = None

    def canonical_findings(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            _build_path_finding(provider=self.provider_family, path=path) for path in self.artifact_paths
        )

    def primary_artifact_path(self) -> Path | None:
        if not self.artifact_paths:
            return None
        return self.artifact_paths[0]

    def sort_timestamp(self) -> float | None:
        return _coalesce_timestamp(
            self.updated_at,
            *(safe_path_mtime(path) for path in self.artifact_paths),
        )

    def merge(self, other: SessionSource) -> SessionSource:
        if not _merge_requires_same_identity(self, other):
            return super().merge(other)
        assert isinstance(other, CodexSessionSource)

        return CodexSessionSource(
            provider_instance=self.provider_instance,
            native_session_id=self.native_session_id,
            artifact_paths=_unique_paths(self.artifact_paths + other.artifact_paths),
            thread_name=self.thread_name or other.thread_name,
            index_paths=_unique_paths(self.index_paths + other.index_paths),
            updated_at=_coalesce_timestamp(self.updated_at, other.updated_at),
        )

    def display_name(self) -> str | None:
        return self.thread_name

    def display_name_field(self) -> str | None:
        if self.thread_name is None:
            return None
        return "thread_name"

    def native_fields(self) -> dict[str, Any]:
        payload = super().native_fields()
        if self.thread_name is not None:
            payload["thread_name"] = self.thread_name
        return payload

    def query_fields(self) -> tuple[tuple[str, str], ...]:
        fields = list(super().query_fields())
        if self.thread_name is not None:
            fields.append(("thread_name", self.thread_name))
        return tuple(fields)

    def supplemental_findings(
        self,
        *,
        query: str,
        matched_field: str,
    ) -> tuple[dict[str, Any], ...]:
        findings: list[dict[str, Any]] = []
        for path in self.index_paths:
            findings.append(
                {
                    "provider": self.provider_family,
                    "strategy": "index",
                    "match_kind": "exact",
                    "path": str(path),
                    "matched_field": matched_field,
                    "matched_value": query,
                    "session_id": self.session_id,
                    "thread_name": self.thread_name,
                }
            )
        return tuple(findings)


@dataclass(frozen=True)
class CopilotCliSessionSource(SessionSource):
    session_root: Path | None = None
    session_file: Path | None = None
    updated_at: float | None = None

    def canonical_findings(self) -> tuple[dict[str, Any], ...]:
        findings: list[dict[str, Any]] = []
        if self.session_root is not None:
            findings.append(_build_path_finding(provider=self.provider_family, path=self.session_root))
        if self.session_file is not None:
            findings.append(_build_path_finding(provider=self.provider_family, path=self.session_file))
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

    def merge(self, other: SessionSource) -> SessionSource:
        if not _merge_requires_same_identity(self, other):
            return super().merge(other)
        assert isinstance(other, CopilotCliSessionSource)

        return CopilotCliSessionSource(
            provider_instance=self.provider_instance,
            native_session_id=self.native_session_id,
            session_root=self.session_root or other.session_root,
            session_file=self.session_file or other.session_file,
            updated_at=_coalesce_timestamp(self.updated_at, other.updated_at),
        )


@dataclass(frozen=True)
class GeminiCliSessionSource(SessionSource):
    artifact_paths: tuple[Path, ...]
    updated_at: float | None = None

    def canonical_findings(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            _build_path_finding(provider=self.provider_family, path=path) for path in self.artifact_paths
        )

    def primary_artifact_path(self) -> Path | None:
        if not self.artifact_paths:
            return None
        return self.artifact_paths[0]

    def sort_timestamp(self) -> float | None:
        return _coalesce_timestamp(
            self.updated_at,
            *(safe_path_mtime(path) for path in self.artifact_paths),
        )

    def merge(self, other: SessionSource) -> SessionSource:
        if not _merge_requires_same_identity(self, other):
            return super().merge(other)
        assert isinstance(other, GeminiCliSessionSource)

        return GeminiCliSessionSource(
            provider_instance=self.provider_instance,
            native_session_id=self.native_session_id,
            artifact_paths=_unique_paths(self.artifact_paths + other.artifact_paths),
            updated_at=_coalesce_timestamp(self.updated_at, other.updated_at),
        )


@dataclass(frozen=True)
class OpenclawSessionSource(SessionSource):
    transcript_path: Path | None = None
    sessions_index_path: Path | None = None
    session_keys: tuple[str, ...] = ()
    agent_id: str | None = None
    updated_at: float | None = None

    def canonical_findings(self) -> tuple[dict[str, Any], ...]:
        if self.transcript_path is not None:
            return (_build_path_finding(provider=self.provider_family, path=self.transcript_path),)
        if self.sessions_index_path is not None:
            return (_build_path_finding(provider=self.provider_family, path=self.sessions_index_path),)
        return ()

    def primary_artifact_path(self) -> Path | None:
        return self.transcript_path

    def sort_timestamp(self) -> float | None:
        return _coalesce_timestamp(
            self.updated_at,
            safe_path_mtime(self.transcript_path),
            safe_path_mtime(self.sessions_index_path),
        )

    def merge(self, other: SessionSource) -> SessionSource:
        if not _merge_requires_same_identity(self, other):
            return super().merge(other)
        assert isinstance(other, OpenclawSessionSource)

        agent_id = self.agent_id if self.agent_id == other.agent_id else self.agent_id or other.agent_id
        return OpenclawSessionSource(
            provider_instance=self.provider_instance,
            native_session_id=self.native_session_id,
            transcript_path=self.transcript_path or other.transcript_path,
            sessions_index_path=self.sessions_index_path or other.sessions_index_path,
            session_keys=_unique_strings(self.session_keys + other.session_keys),
            agent_id=agent_id,
            updated_at=_coalesce_timestamp(self.updated_at, other.updated_at),
        )

    def native_fields(self) -> dict[str, Any]:
        payload = super().native_fields()
        if self.session_keys:
            payload["session_keys"] = list(self.session_keys)
        if self.agent_id is not None:
            payload["agent_id"] = self.agent_id
        return payload

    def query_fields(self) -> tuple[tuple[str, str], ...]:
        return super().query_fields() + tuple(("session_key", key) for key in self.session_keys)


@dataclass(frozen=True)
class OpencodeSessionSource(SessionSource):
    diff_path: Path | None = None
    sqlite_db_path: Path | None = None
    updated_at: float | None = None

    def canonical_findings(self) -> tuple[dict[str, Any], ...]:
        findings: list[dict[str, Any]] = []
        if self.diff_path is not None:
            findings.append(_build_path_finding(provider=self.provider_family, path=self.diff_path))
        if self.sqlite_db_path is not None:
            findings.append(
                {
                    "provider": self.provider_family,
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

    def merge(self, other: SessionSource) -> SessionSource:
        if not _merge_requires_same_identity(self, other):
            return super().merge(other)
        assert isinstance(other, OpencodeSessionSource)

        return OpencodeSessionSource(
            provider_instance=self.provider_instance,
            native_session_id=self.native_session_id,
            diff_path=self.diff_path or other.diff_path,
            sqlite_db_path=self.sqlite_db_path or other.sqlite_db_path,
            updated_at=_coalesce_timestamp(self.updated_at, other.updated_at),
        )


__all__ = [
    "ChatSession",
    "ClaudeCodeSessionSource",
    "CodexSessionSource",
    "CopilotCliSessionSource",
    "GeminiCliSessionSource",
    "OpenclawSessionSource",
    "OpencodeSessionSource",
    "ProviderInstance",
    "SessionSource",
    "coerce_timestamp",
    "safe_path_mtime",
]
