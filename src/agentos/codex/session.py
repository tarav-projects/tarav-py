from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from agentos._core.errors import CliError
from agentos.agent.primitives import SessionSource
from agentos.agent.session_utils import (
    artifact_paths_by_role as _artifact_paths_by_role,
    coalesce_timestamp as _coalesce_timestamp,
    coerce_timestamp as _coerce_timestamp,
    created_timestamp_from_turns as _created_timestamp_from_turns,
    glob_paths as _glob_paths,
    primary_source_path as _primary_source_path,
    primary_transcript_artifact as _primary_transcript_artifact,
    safe_path_mtime as _safe_path_mtime,
    source_ref_id_for_artifact as _source_ref_id_for_artifact,
    string_or_none as _string_or_none,
)


CODEX_PROVIDER = "codex"


@dataclass(frozen=True)
class CodexSessionRef:
    native_session_id: str
    rollout_paths: tuple[Path, ...] = ()
    source_ref_id: str | None = None
    thread_name: str | None = None
    cwd: str | None = None
    index_paths: tuple[Path, ...] = ()
    updated_at: float | None = None

    @property
    def provider(self) -> str:
        return CODEX_PROVIDER

    @property
    def rollout_path(self) -> Path | None:
        if not self.rollout_paths:
            return None
        return self.rollout_paths[0]

    @property
    def session_id(self) -> str:
        return self.native_session_id

    def matches_query(self, query: str) -> bool:
        return query in {self.native_session_id, self.thread_name}

    def display_name(self) -> str | None:
        return self.thread_name

    def display_name_field(self) -> str | None:
        if self.thread_name is None:
            return None
        return "thread_name"

    def native_ref_metadata(self) -> dict[str, object]:
        payload: dict[str, object] = {}
        if self.thread_name is not None:
            payload["thread_name"] = self.thread_name
        if self.cwd is not None:
            payload["cwd"] = self.cwd
        return payload

    def supplemental_findings(
        self,
        *,
        provider: str,
        query: str,
        matched_field: str,
    ) -> tuple[dict[str, object], ...]:
        return tuple(
            {
                "provider": provider,
                "strategy": "index",
                "match_kind": "exact",
                "path": str(path),
                "matched_field": matched_field,
                "matched_value": query,
                "session_id": self.native_session_id,
                "thread_name": self.thread_name,
            }
            for path in self.index_paths
        )

    def sort_timestamp(self) -> float | None:
        return _coalesce_timestamp(
            self.updated_at,
            *(_safe_path_mtime(path) for path in self.rollout_paths),
        )

    def to_session(self) -> "CodexSession":
        return CodexSession(
            native_session_id=self.native_session_id,
            rollout_paths=self.rollout_paths,
            source_ref_id=self.source_ref_id,
            thread_name=self.thread_name,
            cwd=self.cwd,
            index_paths=self.index_paths,
            updated_at=self.updated_at,
        )

    def merge(self, other: "CodexSessionRef") -> "CodexSessionRef":
        if self.native_session_id != other.native_session_id:
            raise TypeError(
                f"cannot merge Codex session refs: {self.native_session_id} != {other.native_session_id}"
            )
        return CodexSessionRef(
            native_session_id=self.native_session_id,
            rollout_paths=_unique_paths(self.rollout_paths + other.rollout_paths),
            source_ref_id=self.source_ref_id or other.source_ref_id,
            thread_name=self.thread_name or other.thread_name,
            cwd=self.cwd or other.cwd,
            index_paths=_unique_paths(self.index_paths + other.index_paths),
            updated_at=_coalesce_timestamp(self.updated_at, other.updated_at),
        )

    @classmethod
    def from_chatlas_session_payload(
        cls,
        session: dict[str, Any],
        *,
        sources: list[dict[str, object]],
    ) -> "CodexSessionRef | None":
        if session.get("provider") != CODEX_PROVIDER:
            return None

        native_session_id = _string_or_none(session.get("session_id"))
        if native_session_id is None:
            return None

        primary_artifact = _primary_transcript_artifact(session)
        if primary_artifact is None:
            return None
        rollout_path_text = _string_or_none(primary_artifact.get("path"))
        if rollout_path_text is None:
            return None

        return cls(
            native_session_id=native_session_id,
            rollout_paths=(Path(rollout_path_text),),
            source_ref_id=_source_ref_id_for_artifact(primary_artifact, sources=sources),
            thread_name=_string_or_none(session.get("display_name")),
            cwd=_string_or_none(_native_payload(session).get("cwd")),
            index_paths=tuple(
                Path(path_text)
                for path_text in _artifact_paths_by_role(session, role="session_index")
            ),
            updated_at=_coerce_timestamp(session.get("last_activity_at")),
        )


@dataclass(frozen=True)
class CodexSession:
    native_session_id: str
    rollout_paths: tuple[Path, ...] = ()
    source_ref_id: str | None = None
    thread_name: str | None = None
    cwd: str | None = None
    index_paths: tuple[Path, ...] = ()
    updated_at: float | None = None

    @property
    def provider(self) -> str:
        return CODEX_PROVIDER

    @property
    def rollout_path(self) -> Path | None:
        if not self.rollout_paths:
            return None
        return self.rollout_paths[0]

    @property
    def session_id(self) -> str:
        return self.native_session_id

    def sources(self) -> tuple[SessionSource, ...]:
        sources = [
            SessionSource(role="transcript", path=path)
            for path in self.rollout_paths
        ]
        sources.extend(
            SessionSource(
                role="session_index",
                path=path,
                locator={
                    "kind": "jsonl_record_match",
                    "match": {"id": self.native_session_id},
                },
            )
            for path in self.index_paths
        )
        return tuple(sources)

    def created_timestamp(self) -> float | None:
        artifact = _primary_source_path(self.sources())
        if artifact is None or not artifact.exists():
            return None

        try:
            from agentos.agent.extractors.codex import extract_dialog_from_codex_rollout

            return _created_timestamp_from_turns(
                extract_dialog_from_codex_rollout(artifact, raw=False)
            )
        except (CliError, OSError, json.JSONDecodeError):
            return None

    def dialog_turn_count(self) -> int | None:
        artifact = _primary_source_path(self.sources())
        if artifact is None or not artifact.is_file():
            return None

        try:
            from agentos.agent.extractors.codex import extract_dialog_from_codex_rollout

            return len(extract_dialog_from_codex_rollout(artifact, raw=False))
        except (CliError, OSError, json.JSONDecodeError):
            return None

    def provider_stats(self) -> dict[str, object]:
        return {
            "rollout_artifact_count": len(self.rollout_paths),
            "session_index_count": len(self.index_paths),
            "has_rollout_artifact": any(path.is_file() for path in self.rollout_paths),
            "dialog_turn_count": self.dialog_turn_count(),
        }

    def merge(self, other: "CodexSession") -> "CodexSession":
        return CodexSessionRef(
            native_session_id=self.native_session_id,
            rollout_paths=self.rollout_paths,
            source_ref_id=self.source_ref_id,
            thread_name=self.thread_name,
            cwd=self.cwd,
            index_paths=self.index_paths,
            updated_at=self.updated_at,
        ).merge(
            CodexSessionRef(
                native_session_id=other.native_session_id,
                rollout_paths=other.rollout_paths,
                source_ref_id=other.source_ref_id,
                thread_name=other.thread_name,
                cwd=other.cwd,
                index_paths=other.index_paths,
                updated_at=other.updated_at,
            )
        ).to_session()

    @classmethod
    def from_chatlas_session_payload(
        cls,
        session: dict[str, Any],
        *,
        sources: list[dict[str, object]],
    ) -> "CodexSession | None":
        session_ref = CodexSessionRef.from_chatlas_session_payload(
            session,
            sources=sources,
        )
        if session_ref is None:
            return None
        return session_ref.to_session()


def discover_codex_session_refs(*, targets: tuple[Path, ...]) -> tuple[CodexSessionRef, ...]:
    session_refs_by_id: dict[str, CodexSessionRef] = {}

    for target in targets:
        if target.is_file() and target.name == "session_index.jsonl":
            for session_ref in read_codex_index_session_refs(target):
                _merge_codex_session_ref(session_refs_by_id, session_ref)
            continue
        for path in _glob_paths(target, "**/rollout-*.jsonl"):
            session_ref = read_codex_rollout_session_ref(path)
            if session_ref is not None:
                _merge_codex_session_ref(session_refs_by_id, session_ref)

    return _sort_codex_session_refs(tuple(session_refs_by_id.values()))


def discover_codex_sessions(*, targets: tuple[Path, ...]) -> tuple[CodexSession, ...]:
    return tuple(
        session_ref.to_session()
        for session_ref in discover_codex_session_refs(targets=targets)
    )


def find_codex_session_ref_by_id(*, targets: tuple[Path, ...], session_id: str) -> CodexSessionRef | None:
    # discovery-equivalent point lookup: walk the targets in discovery order and
    # merge every ref carrying the id (rollout matches + session_index entries),
    # so the returned ref equals what discover_codex_session_refs would produce
    pattern = f"*{session_id}*.jsonl"
    session_refs_by_id: dict[str, CodexSessionRef] = {}
    for target in targets:
        if target.is_file() and target.name == "session_index.jsonl":
            for session_ref in read_codex_index_session_refs(target):
                if session_ref.native_session_id == session_id:
                    _merge_codex_session_ref(session_refs_by_id, session_ref)
            continue
        if target.is_file() and session_id in target.stem and target.suffix == ".jsonl":
            ref = read_codex_rollout_session_ref(target)
            if ref is not None and ref.native_session_id == session_id:
                _merge_codex_session_ref(session_refs_by_id, ref)
            continue
        if not target.is_dir():
            continue
        for match in sorted(target.rglob(pattern)):
            if not match.is_file():
                continue
            ref = read_codex_rollout_session_ref(match)
            if ref is not None and ref.native_session_id == session_id:
                _merge_codex_session_ref(session_refs_by_id, ref)
    return session_refs_by_id.get(session_id)


def find_codex_sessions(*, targets: tuple[Path, ...], query: str) -> tuple[CodexSession, ...]:
    sessions_by_id: dict[str, CodexSession] = {}
    for session_ref in discover_codex_session_refs(targets=targets):
        if session_ref.matches_query(query):
            session = session_ref.to_session()
            _merge_codex_session(sessions_by_id, session)
    return _sort_codex_sessions(tuple(sessions_by_id.values()))


def read_codex_rollout_session_ref(path: Path) -> CodexSessionRef | None:
    meta_obj = _read_codex_session_meta(path)
    if meta_obj is None:
        return None

    payload = meta_obj.get("payload")
    if not isinstance(payload, dict):
        return None

    session_id = _string_or_none(payload.get("id"))
    if session_id is None:
        return None

    return CodexSessionRef(
        native_session_id=session_id,
        rollout_paths=(path,),
        cwd=_string_or_none(payload.get("cwd")),
        updated_at=_coalesce_timestamp(
            _safe_path_mtime(path),
            _coerce_timestamp(meta_obj.get("timestamp")),
        ),
    )


def read_codex_rollout_session(path: Path) -> CodexSession | None:
    session_ref = read_codex_rollout_session_ref(path)
    if session_ref is None:
        return None
    return session_ref.to_session()


def read_codex_index_session_refs(path: Path) -> tuple[CodexSessionRef, ...]:
    if not path.is_file():
        return ()

    session_refs: list[CodexSessionRef] = []
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
                if not isinstance(obj, dict):
                    continue
                session_id = _string_or_none(obj.get("id"))
                if session_id is None:
                    continue
                session_refs.append(
                    CodexSessionRef(
                        native_session_id=session_id,
                        thread_name=_string_or_none(obj.get("thread_name")),
                        index_paths=(path,),
                        updated_at=_coalesce_timestamp(_coerce_timestamp(obj.get("updated_at")), _safe_path_mtime(path)),
                    )
                )
    except OSError:
        return ()

    return tuple(session_refs)


def read_codex_index_sessions(path: Path) -> tuple[CodexSession, ...]:
    return tuple(
        session_ref.to_session()
        for session_ref in read_codex_index_session_refs(path)
    )


def load_codex_session(session_ref: CodexSessionRef) -> CodexSession:
    return session_ref.to_session()


def _read_codex_session_meta(path: Path) -> dict[str, Any] | None:
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
                if not isinstance(obj, dict):
                    continue
                if obj.get("type") != "session_meta":
                    continue
                payload = obj.get("payload")
                if not isinstance(payload, dict):
                    continue
                if _string_or_none(payload.get("id")) is None:
                    continue
                return obj
    except OSError:
        return None

    return None


def _native_payload(session: dict[str, Any]) -> dict[str, object]:
    native = session.get("native")
    if isinstance(native, dict):
        return native
    return {}


def _merge_codex_session(sessions_by_id: dict[str, CodexSession], session: CodexSession) -> None:
    existing = sessions_by_id.get(session.native_session_id)
    if existing is None:
        sessions_by_id[session.native_session_id] = session
        return
    sessions_by_id[session.native_session_id] = existing.merge(session)


def _merge_codex_session_ref(
    session_refs_by_id: dict[str, CodexSessionRef],
    session_ref: CodexSessionRef,
) -> None:
    existing = session_refs_by_id.get(session_ref.native_session_id)
    if existing is None:
        session_refs_by_id[session_ref.native_session_id] = session_ref
        return
    session_refs_by_id[session_ref.native_session_id] = existing.merge(session_ref)


def _sort_codex_sessions(sessions: tuple[CodexSession, ...]) -> tuple[CodexSession, ...]:
    return tuple(sorted(sessions, key=lambda session: session.native_session_id))


def _sort_codex_session_refs(
    session_refs: tuple[CodexSessionRef, ...],
) -> tuple[CodexSessionRef, ...]:
    return tuple(sorted(session_refs, key=lambda session_ref: session_ref.native_session_id))


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
    "CodexSession",
    "CodexSessionRef",
    "discover_codex_session_refs",
    "discover_codex_sessions",
    "find_codex_sessions",
    "load_codex_session",
    "read_codex_index_session_refs",
    "read_codex_index_sessions",
    "read_codex_rollout_session_ref",
    "read_codex_rollout_session",
]
