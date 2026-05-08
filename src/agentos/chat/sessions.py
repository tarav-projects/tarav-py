from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from agentos._core.sequences import _unique_paths, _unique_strings
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


def _earliest_timestamp(*values: float | None) -> float | None:
    timestamps = [value for value in values if value is not None]
    if not timestamps:
        return None
    return min(timestamps)



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
class SessionProviderIdentity:
    family: str
    identity: tuple[object, ...]
    uri_key: str
    fingerprint: str
    summary_payload: dict[str, Any]

    def identity_key(self) -> tuple[object, ...]:
        return self.identity

    def uri_component(self) -> str:
        return self.uri_key

    def summary(self) -> dict[str, Any]:
        return dict(self.summary_payload)

    def matches_fingerprint_prefix(self, prefix: str) -> bool:
        return self.fingerprint.startswith(prefix)


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


@dataclass(frozen=True)
class ChatSessionRecord:
    provider_identity: SessionProviderIdentity
    native_session_id: str

    @property
    def provider_family(self) -> str:
        return self.provider_identity.family

    @property
    def provider(self) -> str:
        return self.provider_family

    @property
    def session_id(self) -> str:
        return self.native_session_id

    def record_identity_key(self) -> tuple[object, ...]:
        return (
            self.provider_family,
            self.provider_identity.identity_key(),
            self.native_session_id,
        )

    def backing_artifacts(self) -> tuple[BackingArtifact, ...]:
        return ()

    def primary_backing_artifact(self) -> BackingArtifact | None:
        artifacts = self.backing_artifacts()
        if not artifacts:
            return None
        return artifacts[0]

    def canonical_findings(self) -> tuple[dict[str, Any], ...]:
        return ()

    def primary_artifact_path(self) -> Path | None:
        primary_artifact = self.primary_backing_artifact()
        if primary_artifact is None:
            return None
        return primary_artifact.path

    def created_timestamp(self) -> float | None:
        return None

    def sort_timestamp(self) -> float | None:
        return None

    def merge(self, other: ChatSessionRecord) -> ChatSessionRecord:
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


def _merge_requires_same_identity(left: ChatSessionRecord, right: ChatSessionRecord) -> bool:
    return type(left) is type(right) and left.record_identity_key() == right.record_identity_key()


def _build_chat_session_uri(record: ChatSessionRecord) -> str:
    return (
        f"agentos://chat-session/{quote(record.provider_family, safe='')}/"
        f"{record.provider_identity.uri_component()}/"
        f"{quote(record.native_session_id, safe='')}"
    )


@dataclass(frozen=True)
class ChatSession:
    record: ChatSessionRecord

    def query_fields(self) -> tuple[tuple[str, str], ...]:
        return (
            ("uri", self.uri),
            ("provider_instance_fingerprint", self.provider_identity.fingerprint),
        ) + self.record.query_fields()

    @property
    def uri(self) -> str:
        return _build_chat_session_uri(self.record)

    @property
    def provider_family(self) -> str:
        return self.record.provider_family

    @property
    def provider_identity(self) -> SessionProviderIdentity:
        return self.record.provider_identity

    @property
    def provider(self) -> str:
        return self.provider_family

    @property
    def session_id(self) -> str:
        return self.record.session_id

    def backing_artifacts(self) -> tuple[BackingArtifact, ...]:
        return self.record.backing_artifacts()

    def primary_backing_artifact(self) -> BackingArtifact | None:
        return self.record.primary_backing_artifact()

    def canonical_findings(self) -> tuple[dict[str, Any], ...]:
        return self.record.canonical_findings()

    def primary_artifact_path(self) -> Path | None:
        return self.record.primary_artifact_path()

    def created_timestamp(self) -> float | None:
        return self.record.created_timestamp()

    def sort_timestamp(self) -> float | None:
        return self.record.sort_timestamp()

    def merge(self, other: ChatSession) -> ChatSession:
        if self.uri != other.uri:
            raise TypeError(f"cannot merge distinct chat sessions: {self.uri} != {other.uri}")
        return ChatSession(record=self.record.merge(other.record))

    def display_name(self) -> str | None:
        return self.record.display_name()

    def display_name_field(self) -> str | None:
        return self.record.display_name_field()

    def native_fields(self) -> dict[str, Any]:
        return self.record.native_fields()

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
        return self.record.supplemental_findings(query=query, matched_field=matched_field)


@dataclass(frozen=True)
class ClaudeCodeSessionRecord(ChatSessionRecord):
    artifact_paths: tuple[Path, ...]
    source_kind: str = "project"
    title: str | None = None
    updated_at: float | None = None

    def backing_artifacts(self) -> tuple[BackingArtifact, ...]:
        artifacts: list[BackingArtifact] = []
        for path in self.artifact_paths:
            role = "transcript" if path.suffix == ".jsonl" else "metadata"
            artifacts.append(
                BackingArtifact(
                    role=role,
                    path=path,
                )
            )
        return tuple(artifacts)

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

    def merge(self, other: ChatSessionRecord) -> ChatSessionRecord:
        if not _merge_requires_same_identity(self, other):
            return super().merge(other)
        assert isinstance(other, ClaudeCodeSessionRecord)

        source_kind = self.source_kind if self.source_kind == other.source_kind else "mixed"
        return ClaudeCodeSessionRecord(
            provider_identity=self.provider_identity,
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
class CodexSessionRecord(ChatSessionRecord):
    artifact_paths: tuple[Path, ...] = ()
    thread_name: str | None = None
    index_paths: tuple[Path, ...] = ()
    updated_at: float | None = None

    def backing_artifacts(self) -> tuple[BackingArtifact, ...]:
        artifacts = [
            BackingArtifact(
                role="transcript",
                path=path,
            )
            for path in self.artifact_paths
        ]
        artifacts.extend(
            BackingArtifact(
                role="session_index",
                path=path,
                locator={
                    "kind": "jsonl_record_match",
                    "match": {"id": self.session_id},
                },
            )
            for path in self.index_paths
        )
        return tuple(artifacts)

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

    def merge(self, other: ChatSessionRecord) -> ChatSessionRecord:
        if not _merge_requires_same_identity(self, other):
            return super().merge(other)
        assert isinstance(other, CodexSessionRecord)

        return CodexSessionRecord(
            provider_identity=self.provider_identity,
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
class CopilotCliSessionRecord(ChatSessionRecord):
    session_root: Path | None = None
    session_file: Path | None = None
    updated_at: float | None = None

    def backing_artifacts(self) -> tuple[BackingArtifact, ...]:
        artifacts: list[BackingArtifact] = []
        if self.session_file is not None:
            artifacts.append(
                BackingArtifact(
                    role="transcript",
                    path=self.session_file,
                )
            )
        elif self.session_root is not None:
            events_path = self.session_root / "events.jsonl"
            if events_path.is_file():
                artifacts.append(
                    BackingArtifact(
                        role="transcript",
                        path=events_path,
                    )
                )
        if self.session_root is not None:
            artifacts.append(
                BackingArtifact(
                    role="session_root",
                    path=self.session_root,
                    storage_kind="directory",
                )
            )
        return tuple(artifacts)

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

    def merge(self, other: ChatSessionRecord) -> ChatSessionRecord:
        if not _merge_requires_same_identity(self, other):
            return super().merge(other)
        assert isinstance(other, CopilotCliSessionRecord)

        return CopilotCliSessionRecord(
            provider_identity=self.provider_identity,
            native_session_id=self.native_session_id,
            session_root=self.session_root or other.session_root,
            session_file=self.session_file or other.session_file,
            updated_at=_coalesce_timestamp(self.updated_at, other.updated_at),
        )


@dataclass(frozen=True)
class GeminiCliSessionRecord(ChatSessionRecord):
    artifact_paths: tuple[Path, ...]
    updated_at: float | None = None

    def backing_artifacts(self) -> tuple[BackingArtifact, ...]:
        return tuple(
            BackingArtifact(
                role="transcript",
                path=path,
            )
            for path in self.artifact_paths
        )

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

    def merge(self, other: ChatSessionRecord) -> ChatSessionRecord:
        if not _merge_requires_same_identity(self, other):
            return super().merge(other)
        assert isinstance(other, GeminiCliSessionRecord)

        return GeminiCliSessionRecord(
            provider_identity=self.provider_identity,
            native_session_id=self.native_session_id,
            artifact_paths=_unique_paths(self.artifact_paths + other.artifact_paths),
            updated_at=_coalesce_timestamp(self.updated_at, other.updated_at),
        )


@dataclass(frozen=True)
class PiSessionRecord(ChatSessionRecord):
    artifact_paths: tuple[Path, ...]
    cwd: str | None = None
    model_provider: str | None = None
    model_id: str | None = None
    thinking_level: str | None = None
    started_at: float | None = None
    updated_at: float | None = None

    def backing_artifacts(self) -> tuple[BackingArtifact, ...]:
        return tuple(
            BackingArtifact(
                role="transcript",
                path=path,
            )
            for path in self.artifact_paths
        )

    def canonical_findings(self) -> tuple[dict[str, Any], ...]:
        return tuple(
            _build_path_finding(provider=self.provider_family, path=path) for path in self.artifact_paths
        )

    def primary_artifact_path(self) -> Path | None:
        if not self.artifact_paths:
            return None
        return self.artifact_paths[0]

    def created_timestamp(self) -> float | None:
        return self.started_at

    def sort_timestamp(self) -> float | None:
        return _coalesce_timestamp(
            self.updated_at,
            self.started_at,
            *(safe_path_mtime(path) for path in self.artifact_paths),
        )

    def merge(self, other: ChatSessionRecord) -> ChatSessionRecord:
        if not _merge_requires_same_identity(self, other):
            return super().merge(other)
        assert isinstance(other, PiSessionRecord)

        cwd = self.cwd if self.cwd == other.cwd else self.cwd or other.cwd
        model_provider = (
            self.model_provider
            if self.model_provider == other.model_provider
            else self.model_provider or other.model_provider
        )
        model_id = self.model_id if self.model_id == other.model_id else self.model_id or other.model_id
        thinking_level = (
            self.thinking_level
            if self.thinking_level == other.thinking_level
            else self.thinking_level or other.thinking_level
        )
        return PiSessionRecord(
            provider_identity=self.provider_identity,
            native_session_id=self.native_session_id,
            artifact_paths=_unique_paths(self.artifact_paths + other.artifact_paths),
            cwd=cwd,
            model_provider=model_provider,
            model_id=model_id,
            thinking_level=thinking_level,
            started_at=_earliest_timestamp(self.started_at, other.started_at),
            updated_at=_coalesce_timestamp(self.updated_at, other.updated_at),
        )

    def native_fields(self) -> dict[str, Any]:
        payload = super().native_fields()
        if self.cwd is not None:
            payload["cwd"] = self.cwd
        if self.model_provider is not None:
            payload["model_provider"] = self.model_provider
        if self.model_id is not None:
            payload["model_id"] = self.model_id
        if self.thinking_level is not None:
            payload["thinking_level"] = self.thinking_level
        return payload

    def query_fields(self) -> tuple[tuple[str, str], ...]:
        fields = list(super().query_fields())
        if self.cwd is not None:
            fields.append(("cwd", self.cwd))
        if self.model_id is not None:
            fields.append(("model_id", self.model_id))
        if self.model_provider is not None:
            fields.append(("model_provider", self.model_provider))
        return tuple(fields)


@dataclass(frozen=True)
class OpenclawSessionRecord(ChatSessionRecord):
    transcript_path: Path | None = None
    sessions_index_path: Path | None = None
    session_keys: tuple[str, ...] = ()
    agent_id: str | None = None
    updated_at: float | None = None

    def backing_artifacts(self) -> tuple[BackingArtifact, ...]:
        artifacts: list[BackingArtifact] = []
        if self.transcript_path is not None:
            artifacts.append(
                BackingArtifact(
                    role="transcript",
                    path=self.transcript_path,
                )
            )
        if self.sessions_index_path is not None:
            locator: dict[str, Any]
            if self.session_keys:
                locator = {
                    "kind": "json_object_keys",
                    "keys": list(self.session_keys),
                }
            else:
                locator = {
                    "kind": "json_object_value_match",
                    "match": {"sessionId": self.session_id},
                }
            artifacts.append(
                BackingArtifact(
                    role="session_index",
                    path=self.sessions_index_path,
                    locator=locator,
                )
            )
        return tuple(artifacts)

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

    def merge(self, other: ChatSessionRecord) -> ChatSessionRecord:
        if not _merge_requires_same_identity(self, other):
            return super().merge(other)
        assert isinstance(other, OpenclawSessionRecord)

        agent_id = self.agent_id if self.agent_id == other.agent_id else self.agent_id or other.agent_id
        return OpenclawSessionRecord(
            provider_identity=self.provider_identity,
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
class OpencodeSessionRecord(ChatSessionRecord):
    diff_path: Path | None = None
    sqlite_db_path: Path | None = None
    updated_at: float | None = None

    def backing_artifacts(self) -> tuple[BackingArtifact, ...]:
        artifacts: list[BackingArtifact] = []
        if self.diff_path is not None:
            artifacts.append(
                BackingArtifact(
                    role="session_diff",
                    path=self.diff_path,
                )
            )
        if self.sqlite_db_path is not None:
            artifacts.append(
                BackingArtifact(
                    role="sqlite_session_row",
                    path=self.sqlite_db_path,
                    storage_kind="sqlite_row",
                    locator={
                        "kind": "sqlite_row_match",
                        "table": "session",
                        "key": {"id": self.session_id},
                    },
                )
            )
        return tuple(artifacts)

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

    def merge(self, other: ChatSessionRecord) -> ChatSessionRecord:
        if not _merge_requires_same_identity(self, other):
            return super().merge(other)
        assert isinstance(other, OpencodeSessionRecord)

        return OpencodeSessionRecord(
            provider_identity=self.provider_identity,
            native_session_id=self.native_session_id,
            diff_path=self.diff_path or other.diff_path,
            sqlite_db_path=self.sqlite_db_path or other.sqlite_db_path,
            updated_at=_coalesce_timestamp(self.updated_at, other.updated_at),
        )


__all__ = [
    "BackingArtifact",
    "ChatSession",
    "ClaudeCodeSessionRecord",
    "CodexSessionRecord",
    "CopilotCliSessionRecord",
    "GeminiCliSessionRecord",
    "PiSessionRecord",
    "OpenclawSessionRecord",
    "OpencodeSessionRecord",
    "SessionProviderIdentity",
    "ChatSessionRecord",
    "coerce_timestamp",
    "safe_path_mtime",
]
