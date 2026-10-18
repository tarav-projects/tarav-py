"""The Normal Models index: a SQLite database derived from the JSON cache.

Chatlas produces and caches Normal Models; this index holds their messages and
Turns in one file, ``index/normal-models.sqlite``, for any consumer to query.
It is built only from the cached JSON parts and keeps only what lookups need
(who, where, side, text, which Turn); full records stay in the JSON cache.
Each indexed part records the version of the cache part it consumed, so a
session is fresh while those versions still match. Queries are read-only;
updating is explicit.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Any

from tarav.l1.chatlas.normal_model_cache import NormalModelCache
from tarav.l1.chatlas.paths import default_chatlas_root

JsonObject = dict[str, Any]

INDEX_PATH = Path("index") / "normal-models.sqlite"
INDEX_SCHEMA_VERSION = 2
INDEXED_PARTS = ("messages", "turns")
POLICIES = ("missing", "stale", "all")
SESSION_FACTS = ("provider", "instance", "session_id", "project_path", "last_activity_at")

# tarav.breadcrumb ac4e1f989ab7
_SCHEMA = """
create table if not exists sessions(
    identity text primary key, provider text, instance text, session_id text,
    project_path text, last_activity_at text);
create table if not exists parts(
    identity text, part text, version text, primary key(identity, part));
create table if not exists messages(
    id integer primary key, identity text, position integer, message_address text,
    turn_hash text, side text, text text);
create index if not exists messages_session on messages(identity, position);
create table if not exists turns(
    id integer primary key, identity text, position integer, turn_address text,
    turn_hash text, side text);
create index if not exists turns_session on turns(identity, position);
create index if not exists turns_hash on turns(identity, turn_hash);
create virtual table if not exists messages_fts using fts5(
    text, content='messages', content_rowid='id', tokenize='unicode61 remove_diacritics 2');
"""


@dataclass(frozen=True, slots=True)
class IndexedPart:
    """One part of one session in the index, against the cache part it reflects."""

    name: str
    indexed_version: str | None
    cache_version: str | None

    @property
    def state(self) -> str:
        if self.indexed_version is None:
            return "missing"
        if self.cache_version is not None and self.indexed_version == self.cache_version:
            return "fresh"
        return "stale"


@dataclass(frozen=True, slots=True)
class IndexUpdate:
    """What one update did, by session identity."""

    indexed: tuple[str, ...]
    skipped: tuple[str, ...]
    failed: tuple[tuple[str, str], ...]


# tarav.breadcrumb b0d87403173a
# tarav.breadcrumb 5f489875a871
# tarav.breadcrumb ee5fb80b7cd1
class NormalModelsIndex:
    """The derived database of cached Normal Model messages and Turns."""

    def __init__(self, *, chatlas_root: Path | None = None) -> None:
        self.chatlas_root = (chatlas_root or default_chatlas_root()).expanduser().resolve()
        self.path = self.chatlas_root / INDEX_PATH

    def standing(self, rows: Iterable[JsonObject]) -> dict[str, dict[str, IndexedPart]]:
        """Per session and part: the indexed version against the cache version now."""
        rows = list(rows)
        indexed: dict[tuple[str, str], str] = {}
        if self.path.exists():
            for item in self.query("select identity, part, version from parts"):
                indexed[(item["identity"], item["part"])] = item["version"]
        result: dict[str, dict[str, IndexedPart]] = {}
        for row in rows:
            identity = str(row["identity_hash"])
            cache = NormalModelCache(row, chatlas_root=self.chatlas_root).parts()
            result[identity] = {
                part: IndexedPart(part, indexed.get((identity, part)),
                                  cache[part].raw_version if cache[part].present else None)
                for part in INDEXED_PARTS
            }
        return result

    def update(self, rows: Iterable[JsonObject], *, policy: str = "stale") -> IndexUpdate:
        """Index the selected sessions from their JSON cache, one transaction each.

        ``missing`` indexes sessions never indexed, ``stale`` also those whose
        cache changed since, ``all`` every selected session. A session without
        its cached messages and Turns is skipped; the index never reads raw.
        """
        if policy not in POLICIES:
            raise ValueError(f"index policy must be one of {', '.join(POLICIES)}")
        rows = list(rows)
        standing = self.standing(rows)
        indexed, skipped, failed = [], [], []
        connection = self._connect(write=True)
        try:
            for row in rows:
                identity = str(row["identity_hash"])
                parts = standing[identity]
                if any(part.cache_version is None for part in parts.values()):
                    skipped.append(identity)
                    continue
                states = {part.state for part in parts.values()}
                if policy == "missing" and states != {"missing"}:
                    continue
                if policy == "stale" and states == {"fresh"}:
                    continue
                try:
                    self._index_session(connection, row, parts)
                except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
                    failed.append((identity, f"{type(exc).__name__}: {exc}"))
                    continue
                indexed.append(identity)
        finally:
            connection.close()
        return IndexUpdate(tuple(indexed), tuple(skipped), tuple(failed))

    # tarav.breadcrumb 122be7e1e81a
    def query(self, sql: str, parameters: Sequence[object] | Mapping[str, object] = ()) -> list[JsonObject]:
        """Run read-only SQL over the index and return its rows as dicts."""
        connection = self._connect(write=False)
        try:
            cursor = connection.execute(sql, parameters)
            names = [column[0] for column in cursor.description or ()]
            return [dict(zip(names, values)) for values in cursor.fetchall()]
        finally:
            connection.close()

    def _connect(self, *, write: bool) -> sqlite3.Connection:
        if write:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self.path, timeout=30)
            connection.execute("pragma journal_mode=wal")
            version = connection.execute("pragma user_version").fetchone()[0]
            if version not in (0, INDEX_SCHEMA_VERSION):
                connection.close()
                raise ValueError(f"{self.path} has schema {version}; delete it to rebuild")
            connection.executescript(_SCHEMA)
            connection.execute(f"pragma user_version = {INDEX_SCHEMA_VERSION}")
            return connection
        if not self.path.exists():
            raise FileNotFoundError(f"no Normal Models index at {self.path}")
        return sqlite3.connect(f"{self.path.as_uri()}?mode=ro", uri=True, timeout=30)

    def _index_session(self, connection: sqlite3.Connection, row: JsonObject,
                       parts: dict[str, IndexedPart]) -> None:
        identity = str(row["identity_hash"])
        cache = NormalModelCache(row, chatlas_root=self.chatlas_root)
        turns = list(cache.rows("turns"))
        messages = list(cache.rows("messages"))
        turn_of_message = {
            ref["message_address"]: turn["turn_hash"]
            for turn in turns for ref in turn.get("message_refs", [])
        }
        with connection:
            connection.execute(
                "insert into messages_fts(messages_fts, rowid, text) "
                "select 'delete', id, text from messages where identity = ?", (identity,))
            for table in ("messages", "turns", "parts", "sessions"):
                connection.execute(f"delete from {table} where identity = ?", (identity,))
            connection.execute(
                "insert into sessions values (?, ?, ?, ?, ?, ?)",
                (identity, *(row.get(key) for key in SESSION_FACTS)))
            for position, message in enumerate(messages):
                cursor = connection.execute(
                    "insert into messages(identity, position, message_address, turn_hash,"
                    " side, text) values (?, ?, ?, ?, ?, ?)",
                    (identity, position, message["message_address"],
                     turn_of_message.get(message["message_address"]), message["side"],
                     message["text"]))
                connection.execute("insert into messages_fts(rowid, text) values (?, ?)",
                                   (cursor.lastrowid, message["text"]))
            connection.executemany(
                "insert into turns(identity, position, turn_address, turn_hash, side)"
                " values (?, ?, ?, ?, ?)",
                [(identity, position, turn["turn_address"], turn["turn_hash"], turn["side"])
                 for position, turn in enumerate(turns)])
            connection.executemany(
                "insert into parts values (?, ?, ?)",
                [(identity, name, part.cache_version) for name, part in parts.items()])


__all__ = [
    "INDEX_PATH",
    "INDEXED_PARTS",
    "IndexUpdate",
    "IndexedPart",
    "NormalModelsIndex",
]
