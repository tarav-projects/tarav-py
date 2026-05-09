from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import sqlite3


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
    from agentos.chat.extractors.opencode import connect_opencode_db

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


def _glob_paths(root: Path, pattern: str) -> tuple[Path, ...]:
    if root.is_file():
        return (root,) if root.match(pattern) else ()
    if not root.is_dir():
        return ()
    try:
        return tuple(sorted(root.glob(pattern)))
    except OSError:
        return ()


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


def _coalesce_timestamp(*values: float | None) -> float | None:
    timestamps = [value for value in values if value is not None]
    if not timestamps:
        return None
    return max(timestamps)


__all__ = [
    "OpencodeSession",
    "OpencodeSessionRef",
    "discover_opencode_session_refs",
    "discover_opencode_sessions",
    "find_opencode_sessions",
    "load_opencode_session",
    "query_opencode_sessions",
]
