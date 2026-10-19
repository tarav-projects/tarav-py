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

TARGETS = ("chats", "turns", "messages")
ORDERS = {
    "chats": ("recent", "oldest", "started", "size", "hits", "project"),
    "turns": ("recent", "relevance"),
    "messages": ("recent", "relevance"),
}
SESSION_FACTS = ("identity", "provider", "instance", "session_id", "project_path",
                 "created_at", "last_activity_at")
MESSAGE_FACTS = ("position", "message_address", "turn_hash", "side", "text")


# tarav.breadcrumb 59462ed55719
# tarav.breadcrumb 96b8209e7af7
class ChatlasSearchQuery(SearchQuery):
    """Filter the Normal Models index into chats, turns or messages.

    ``target`` is the level of a row. ``text`` matches its words as a phrase,
    ``match`` is a full-text (FTS5) expression, ``contains`` a
    case-insensitive substring; given together, all must hold, and with none
    every row of the level is listed. Session filters narrow the chats,
    ``order`` sorts the rows and ``offset`` with ``max_hits`` pages them.
    ``capture``, ``cache`` and ``index`` run those stages for the selected
    sessions first.
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
        min_turns: int | None = None,
        order: str = "recent",
        offset: int = 0,
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
        if order not in ORDERS[target]:
            raise ValueError(f"Chatlas {target} order must be one of {', '.join(ORDERS[target])}")
        if offset < 0 or (min_turns is not None and min_turns < 0):
            raise ValueError("Chatlas search offset and min_turns must not be negative")
        self.min_turns, self.order, self.offset = min_turns, order, offset
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
    def has_text(self) -> bool:
        return self.fts() is not None or self.contains is not None

    def stages(self) -> tuple[str, ...]:
        return tuple(name for name in ("capture", "cache", "index") if getattr(self, name))


# tarav.breadcrumb 145c6f21a360
@dataclass(frozen=True, slots=True)
class ChatlasSearchHit:
    """One chat, turn or message, with its session's facts as the index holds them.

    ``messages`` are the hit message, every message of the hit turn in order,
    or a chat's first user message. ``stats`` counts a chat's turns, user
    turns and, when text was given, the turns that match. Full records stay
    in the JSON cache.
    """

    session: JsonObject
    target: str
    turn: JsonObject | None
    messages: tuple[JsonObject, ...]
    stats: JsonObject | None = None


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
            if query.target == "chats":
                sql, parameters = _chats_sql(query)
                for row in index.rows(sql, parameters):
                    first = {"position": 0, "message_address": None, "turn_hash": None,
                             "side": "user", "text": row["first_text"] or ""}
                    stats = {"turns": row["turns"], "user_turns": row["user_turns"],
                             "hits": row["hits"] if query.has_text() else None}
                    yield SearchHit(ChatlasSearchHit(
                        {key: row[key] for key in SESSION_FACTS}, "chats", None, (first,), stats))
                return
            sql, parameters = _rows_sql(query)
            for row in index.rows(sql, parameters):
                session = {key: row[key] for key in SESSION_FACTS}
                if query.target == "messages":
                    message = {key: row[key] for key in MESSAGE_FACTS}
                    yield SearchHit(ChatlasSearchHit(session, "messages", None, (message,)))
                    continue
                turn, messages = _turn(index, row["identity"], row["turn_hash"])
                yield SearchHit(ChatlasSearchHit(session, "turns", turn, messages))


_SESSION_COLUMNS = ("s.identity, s.provider, s.instance, s.session_id, s.project_path,"
                    " s.created_at, s.last_activity_at")
_TURN_COUNT = "(select count(*) from turns t where t.identity = s.identity{side})"


def _text_conditions(query: ChatlasSearchQuery) -> tuple[str, list[str], list[object]]:
    """The join and conditions on messages `m` that the text and side ask for."""
    join, where, parameters = "", [], []
    if query.fts() is not None:
        join = "join messages_fts on messages_fts.rowid = m.id"
        where.append("messages_fts match ?")
        parameters.append(query.fts())
    if query.contains is not None:
        where.append("instr(lower(m.text), lower(?)) > 0")
        parameters.append(query.contains)
    if query.side is not None:
        where.append("m.side = ?")
        parameters.append(query.side)
    return join, where, parameters


def _session_conditions(query: ChatlasSearchQuery) -> tuple[list[str], list[object]]:
    where, parameters = [], []
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
    if query.min_turns is not None:
        where.append(f"{_TURN_COUNT.format(side='')} >= ?")
        parameters.append(query.min_turns)
    return where, parameters


def _page(query: ChatlasSearchQuery) -> tuple[str, list[object]]:
    return " limit ? offset ?", [query.max_hits if query.max_hits is not None else -1, query.offset]


def _chats_sql(query: ChatlasSearchQuery) -> tuple[str, list[object]]:
    hits, parameters = "null", []
    join_hits = ""
    if query.has_text() or query.side is not None:
        join, where, parameters = _text_conditions(query)
        join_hits = (
            "join (select m.identity, count(distinct m.turn_hash) as hits from messages m "
            + join + (" where " + " and ".join(where) if where else "")
            + " group by m.identity) h on h.identity = s.identity"
        )
        hits = "h.hits"
    where, session_parameters = _session_conditions(query)
    order = {
        "recent": "julianday(s.last_activity_at) desc",
        "oldest": "julianday(s.last_activity_at) asc",
        "started": "julianday(s.created_at) desc",
        "size": "turns desc",
        "hits": f"{hits} desc, julianday(s.last_activity_at) desc",
        "project": "s.project_path, julianday(s.last_activity_at) desc",
    }[query.order]
    page, page_parameters = _page(query)
    sql = (
        f"select {_SESSION_COLUMNS}, {_TURN_COUNT.format(side='')} as turns,"
        f" {_TURN_COUNT.format(side=" and t.side = 'user'")} as user_turns, {hits} as hits,"
        " (select text from messages f where f.identity = s.identity and f.side = 'user'"
        "  order by f.position limit 1) as first_text"
        f" from sessions s {join_hits}"
        + (" where " + " and ".join(where) if where else "")
        + f" order by {order}, s.identity" + page
    )
    return sql, [*parameters, *session_parameters, *page_parameters]


def _rows_sql(query: ChatlasSearchQuery) -> tuple[str, list[object]]:
    """Turns (grouped from their messages) or messages, newest chat first or by relevance."""
    join, where, parameters = _text_conditions(query)
    session_where, session_parameters = _session_conditions(query)
    turns = query.target == "turns"
    where = [*where, *session_where, *(["m.turn_hash is not null"] if turns else [])]
    rank = "min(messages_fts.rank)" if turns else "messages_fts.rank"
    position = "max(m.position)" if turns else "m.position"
    recent = f"julianday(s.last_activity_at) desc, s.identity, {position} desc"
    order = f"{rank}, {recent}" if query.order == "relevance" and query.fts() is not None else recent
    page, page_parameters = _page(query)
    sql = (
        f"select {_SESSION_COLUMNS}, {position} as position, m.message_address, m.turn_hash,"
        " m.side, m.text from messages m join sessions s on s.identity = m.identity "
        + join
        + (" where " + " and ".join(where) if where else "")
        + (" group by m.identity, m.turn_hash" if turns else "")
        + f" order by {order}" + page
    )
    return sql, [*parameters, *session_parameters, *page_parameters]


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
