"""Search across indexed chats, as an engine for Tarav's Search workflow.

Search knows nothing of Chatlas; Chatlas knows how to search its own data.
The engine reads the Normal Models index (``index/normal-models.sqlite``) as
it is. A query names what it searches, turns by default or messages, how text
matches (words, a full-text expression, or a substring), and which sessions.
Flags on the query run chosen pipeline stages for those sessions first.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l1.chatlas.identity import CHATLAS_WORKFLOW_SHIP
from tarav.l1.chatlas.index_time import parse_chatlas_index_timestamp
from tarav.l1.chatlas.normal_models_index import NormalModelsIndex
from tarav.l1.chatlas.query import JsonObject
from tarav.l1.chatlas.stages import ChatlasStages
from tarav.l1.search import SearchEngine, SearchHit, SearchQuery

TARGETS = ("turns", "messages")
SESSION_FACTS = ("identity", "provider", "instance", "session_id", "project_path",
                 "last_activity_at")
MESSAGE_FACTS = ("position", "message_address", "turn_hash", "side", "text")


# tarav.breadcrumb 59462ed55719
# tarav.breadcrumb 96b8209e7af7
class ChatlasSearchQuery(SearchQuery):
    """Find turns or messages in selected sessions of the Normal Models index.

    ``text`` matches its words as a phrase, ``match`` is a full-text (FTS5)
    expression, ``contains`` a case-insensitive substring; given together,
    all must hold. ``capture``, ``cache`` and ``index`` run those stages for
    the selected sessions before searching.
    """

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("b6f3a2d4-6c1e-4f0a-9d7b-2e58c4a1f903"),
            name="Chatlas.Search.Query",
            workflow=CHATLAS_WORKFLOW_SHIP,
        )

    def __init__(
        self,
        text: str | None = None,
        *,
        match: str | None = None,
        contains: str | None = None,
        target: str = "turns",
        side: str | None = None,
        provider: str | None = None,
        project: str | None = None,
        since: str | None = None,
        until: str | None = None,
        capture: bool = False,
        cache: bool = False,
        index: bool = False,
        **options,
    ) -> None:
        super().__init__(**options)
        if target not in TARGETS:
            raise ValueError(f"Chatlas search target must be one of {', '.join(TARGETS)}")
        if side not in (None, "user", "agent"):
            raise ValueError("Chatlas search side must be user or agent")
        for name, value in (("text", text), ("match", match), ("contains", contains)):
            if value is not None and not value.strip():
                raise ValueError(f"Chatlas search {name} must not be empty")
        for name, value in (("since", since), ("until", until)):
            if value is not None and parse_chatlas_index_timestamp(value) is None:
                raise ValueError(f"Chatlas search {name} must be an ISO timestamp")
        self.text, self.match, self.contains = text, match, contains
        self.target, self.side = target, side
        self.provider, self.project, self.since, self.until = provider, project, since, until
        self.capture, self.cache, self.index = capture, cache, index

    # tarav.breadcrumb a1dae755eadd
    def fts(self) -> str | None:
        """The full-text expression: the words of ``text`` as a phrase, and ``match``."""
        parts = []
        if self.text is not None:
            parts.append('"' + self.text.replace('"', '""') + '"')
        if self.match is not None:
            parts.append(f"({self.match})")
        return " AND ".join(parts) or None

    # tarav.breadcrumb addeb1d6da74
    def stages(self) -> tuple[str, ...]:
        return tuple(name for name in ("capture", "cache", "index") if getattr(self, name))


# tarav.breadcrumb 145c6f21a360
@dataclass(frozen=True, slots=True)
class ChatlasSearchHit:
    """One turn or message, with its session's facts as the index holds them.

    ``messages`` are the hit message, or every message of the hit turn in
    order. Full records stay in the JSON cache.
    """

    session: JsonObject
    target: str
    turn: JsonObject | None
    messages: tuple[JsonObject, ...]


# tarav.breadcrumb 3cdac710a169
# tarav.breadcrumb cb26ab1d9194
class ChatlasSearchEngine(SearchEngine):
    """Search the Normal Models index, newest session activity first."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("4e9d1c7a-3b25-4a8f-b6e0-91f2d5c8a374"),
            name="Chatlas.Search.Engine",
            workflow=CHATLAS_WORKFLOW_SHIP,
        )

    def __init__(self, *, chatlas_root: Path | None = None) -> None:
        self.chatlas_root = chatlas_root

    class Search(SearchEngine.Search):
        def accepts(self, query: SearchQuery) -> bool:
            return isinstance(query, ChatlasSearchQuery)

        def _iter_hits(self, query: ChatlasSearchQuery) -> Iterator[SearchHit]:
            if query.stages():
                ChatlasStages(chatlas_root=self.obj.chatlas_root).run(
                    stages=query.stages(), provider=query.provider, project=query.project,
                    since=query.since, until=query.until,
                )
            index = NormalModelsIndex(chatlas_root=self.obj.chatlas_root)
            sql, parameters = _messages_sql(query)
            seen: set[tuple[str, str]] = set()
            for row in index.rows(sql, parameters):
                session = {key: row[key] for key in SESSION_FACTS}
                message = {key: row[key] for key in MESSAGE_FACTS}
                if query.target == "messages":
                    yield SearchHit(ChatlasSearchHit(session, "messages", None, (message,)))
                    continue
                key = (row["identity"], row["turn_hash"])
                if row["turn_hash"] is None or key in seen:
                    continue
                seen.add(key)
                turn, messages = _turn(index, *key)
                yield SearchHit(ChatlasSearchHit(session, "turns", turn, messages))


def _messages_sql(query: ChatlasSearchQuery) -> tuple[str, list[object]]:
    joins, where, parameters = [], [], []
    if query.fts() is not None:
        joins.append("join messages_fts on messages_fts.rowid = m.id")
        where.append("messages_fts match ?")
        parameters.append(query.fts())
    if query.contains is not None:
        where.append("instr(lower(m.text), lower(?)) > 0")
        parameters.append(query.contains)
    if query.side is not None:
        where.append("m.side = ?")
        parameters.append(query.side)
    if query.provider is not None:
        where.append("s.provider = ?")
        parameters.append(query.provider)
    if query.project is not None:
        root = query.project.rstrip("/")
        where.append("(s.project_path = ? or substr(s.project_path, 1, ?) = ?)")
        parameters += [root, len(root) + 1, root + "/"]
    if query.since is not None:
        where.append("julianday(s.last_activity_at) >= julianday(?)")
        parameters.append(query.since)
    if query.until is not None:
        where.append("julianday(s.last_activity_at) <= julianday(?)")
        parameters.append(query.until)
    sql = (
        "select s.identity, s.provider, s.instance, s.session_id, s.project_path,"
        " s.last_activity_at, m.position, m.message_address, m.turn_hash, m.side, m.text"
        " from messages m join sessions s on s.identity = m.identity "
        + " ".join(joins)
        + (" where " + " and ".join(where) if where else "")
        + " order by julianday(s.last_activity_at) desc, s.identity, m.position desc"
    )
    return sql, parameters


def _turn(index: NormalModelsIndex, identity: str, turn_hash: str) -> tuple[JsonObject, tuple]:
    (turn,) = index.query(
        "select position, turn_address, turn_hash, side from turns"
        " where identity = ? and turn_hash = ?", (identity, turn_hash))
    messages = index.query(
        "select position, message_address, turn_hash, side, text from messages"
        " where identity = ? and turn_hash = ? order by position", (identity, turn_hash))
    return turn, tuple(messages)


__all__ = [
    "ChatlasSearchEngine",
    "ChatlasSearchHit",
    "ChatlasSearchQuery",
    "TARGETS",
]
