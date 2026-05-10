from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3

from agentos._core.errors import CliError
from agentos.agent.primitives import SessionSource
from agentos.agent.session_utils import (
    coalesce_timestamp as _coalesce_timestamp,
    coerce_timestamp as _coerce_timestamp,
    glob_paths as _glob_paths,
    primary_source_path as _primary_source_path,
    safe_path_mtime as _safe_path_mtime,
)


OPENCODE_PROVIDER = "opencode"


@dataclass(frozen=True)
class OpencodeSessionRef:
    native_session_id: str
    diff_path: Path | None = None
    sqlite_db_path: Path | None = None
    updated_at: float | None = None

    @property
    def provider(self) -> str:
        return OPENCODE_PROVIDER

    def display_name(self) -> str | None:
        return None

    def display_name_field(self) -> str | None:
        return None

    def native_ref_metadata(self) -> dict[str, object]:
        return {}

    def sort_timestamp(self) -> float | None:
        return _coalesce_timestamp(
            self.updated_at,
            _safe_path_mtime(self.diff_path),
            _safe_path_mtime(self.sqlite_db_path),
        )

    def to_session(self) -> "OpencodeSession":
        return OpencodeSession(
            native_session_id=self.native_session_id,
            diff_path=self.diff_path,
            sqlite_db_path=self.sqlite_db_path,
            updated_at=self.updated_at,
        )


@dataclass(frozen=True)
class OpencodeSession:
    native_session_id: str
    diff_path: Path | None = None
    sqlite_db_path: Path | None = None
    updated_at: float | None = None

    @property
    def provider(self) -> str:
        return OPENCODE_PROVIDER

    def sources(self) -> tuple[SessionSource, ...]:
        sources = []
        if self.diff_path is not None:
            sources.append(SessionSource(role="session_diff", path=self.diff_path))
        if self.sqlite_db_path is not None:
            sources.append(
                SessionSource(
                    role="sqlite_session_row",
                    path=self.sqlite_db_path,
                    storage_kind="sqlite_row",
                    locator={
                        "kind": "sqlite_row_match",
                        "table": "session",
                        "key": {"id": self.native_session_id},
                    },
                )
            )
        return tuple(sources)

    def created_timestamp(self) -> float | None:
        source_path = _primary_source_path(self.sources())
        if source_path is None or not source_path.exists():
            return None

        try:
            from agentos.agent.extractors.opencode import (
                load_opencode_session_messages,
                resolve_opencode_db_path,
            )

            db_path = (
                source_path
                if source_path.name == "opencode.db"
                else resolve_opencode_db_path(source_path)
            )
            messages = load_opencode_session_messages(
                db_path=db_path,
                session_id=self.native_session_id,
            )
            if messages:
                return _coerce_timestamp(messages[0].get("time_created"))
        except (CliError, OSError, sqlite3.Error):
            return None
        return None

    def merge(self, other: OpencodeSession) -> OpencodeSession:
        if self.native_session_id != other.native_session_id:
            raise TypeError(
                f"cannot merge OpenCode sessions: {self.native_session_id} != {other.native_session_id}"
            )
        return OpencodeSession(
            native_session_id=self.native_session_id,
            diff_path=self.diff_path or other.diff_path,
            sqlite_db_path=self.sqlite_db_path or other.sqlite_db_path,
            updated_at=_coalesce_timestamp(self.updated_at, other.updated_at),
        )


def discover_opencode_sessions(
    *,
    targets: tuple[Path, ...],
    sqlite_db_paths: tuple[Path, ...],
) -> tuple[OpencodeSession, ...]:
    sessions_by_id: dict[str, OpencodeSession] = {}

    for target in targets:
        for path in _glob_paths(target, "*.json"):
            _merge_opencode_session(
                sessions_by_id,
                OpencodeSession(
                    native_session_id=path.stem,
                    diff_path=path,
                    updated_at=_safe_path_mtime(path),
                ),
            )

    for sqlite_db_path in sqlite_db_paths:
        for session in query_opencode_sessions(sqlite_db_path):
            _merge_opencode_session(sessions_by_id, session)

    return _sort_opencode_sessions(tuple(sessions_by_id.values()))


def discover_opencode_session_refs(
    *,
    targets: tuple[Path, ...],
    sqlite_db_paths: tuple[Path, ...],
) -> tuple[OpencodeSessionRef, ...]:
    return tuple(
        _opencode_session_ref_from_session(session)
        for session in discover_opencode_sessions(
            targets=targets,
            sqlite_db_paths=sqlite_db_paths,
        )
    )


def find_opencode_sessions(
    *,
    targets: tuple[Path, ...],
    sqlite_db_paths: tuple[Path, ...],
    query: str,
) -> tuple[OpencodeSession, ...]:
    sessions_by_id: dict[str, OpencodeSession] = {}

    for target in targets:
        session_file = target / f"{query}.json"
        if session_file.is_file():
            _merge_opencode_session(
                sessions_by_id,
                OpencodeSession(
                    native_session_id=query,
                    diff_path=session_file,
                    updated_at=_safe_path_mtime(session_file),
                ),
            )

    for sqlite_db_path in sqlite_db_paths:
        for session in query_opencode_sessions(sqlite_db_path, session_id=query):
            _merge_opencode_session(sessions_by_id, session)

    return _sort_opencode_sessions(tuple(sessions_by_id.values()))


def load_opencode_session(session_ref: OpencodeSessionRef) -> OpencodeSession:
    return session_ref.to_session()


def query_opencode_sessions(
    sqlite_db_path: Path,
    *,
    session_id: str | None = None,
) -> tuple[OpencodeSession, ...]:
    from agentos.agent.extractors.opencode import connect_opencode_db

    try:
        connection = connect_opencode_db(sqlite_db_path)
    except sqlite3.Error:
        return ()

    sessions: list[OpencodeSession] = []
    try:
        try:
            if session_id is None:
                cursor = connection.execute("SELECT id, time_updated FROM session ORDER BY id")
            else:
                cursor = connection.execute(
                    "SELECT id, time_updated FROM session WHERE id = ? ORDER BY id",
                    (session_id,),
                )
            rows = cursor.fetchall()
        except sqlite3.Error:
            if session_id is None:
                cursor = connection.execute("SELECT id FROM session ORDER BY id")
            else:
                cursor = connection.execute(
                    "SELECT id FROM session WHERE id = ? ORDER BY id",
                    (session_id,),
                )
            rows = [(row_id, None) for (row_id,) in cursor.fetchall()]
    except sqlite3.Error:
        return ()
    finally:
        connection.close()

    for row_id, time_updated in rows:
        if not isinstance(row_id, str) or not row_id:
            continue
        sessions.append(
            OpencodeSession(
                native_session_id=row_id,
                sqlite_db_path=sqlite_db_path,
                updated_at=_coerce_timestamp(time_updated),
            )
        )

    return tuple(sessions)


def _opencode_session_ref_from_session(session: OpencodeSession) -> OpencodeSessionRef:
    return OpencodeSessionRef(
        native_session_id=session.native_session_id,
        diff_path=session.diff_path,
        sqlite_db_path=session.sqlite_db_path,
        updated_at=session.updated_at,
    )


def _merge_opencode_session(
    sessions_by_id: dict[str, OpencodeSession],
    session: OpencodeSession,
) -> None:
    existing = sessions_by_id.get(session.native_session_id)
    if existing is None:
        sessions_by_id[session.native_session_id] = session
        return
    sessions_by_id[session.native_session_id] = existing.merge(session)


def _sort_opencode_sessions(sessions: tuple[OpencodeSession, ...]) -> tuple[OpencodeSession, ...]:
    return tuple(sorted(sessions, key=lambda session: session.native_session_id))


__all__ = [
    "OpencodeSession",
    "OpencodeSessionRef",
    "discover_opencode_session_refs",
    "discover_opencode_sessions",
    "find_opencode_sessions",
    "load_opencode_session",
    "query_opencode_sessions",
]
