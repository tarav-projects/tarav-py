"""Search across indexed chats, as an engine for Tarav's Search workflow.

Search knows nothing of Chatlas; Chatlas knows how to search its own data.
A query names what it searches, turns by default or messages, and which
sessions, through facts their Session Index rows already carry.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
import logging
from pathlib import Path
import sys

from tarav.l0._core.errors import CliError
from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l1.chatlas.identity import CHATLAS_WORKFLOW_SHIP
from tarav.l1.chatlas.index_store import load_chatlas_session_index_rows
from tarav.l1.chatlas.index_time import (
    chatlas_index_timestamp_sort_value,
    parse_chatlas_index_timestamp,
)
from tarav.l1.chatlas.normal_model_cache import CachedPart, NormalModelCache
from tarav.l1.chatlas.query import (
    ChatlasQuery,
    ChatlasQueryEngine,
    ChatlasQueryError,
    ChatlasTurnMatch,
    JsonObject,
)
from tarav.l1.search import SearchEngine, SearchHit, SearchQuery

logger = logging.getLogger(__name__)

TARGETS = ("turns", "messages")
NORMALIZED_PROVIDERS = ("codex", "claude-code")
SESSION_FACTS = ("provider", "instance", "session_id", "identity_hash",
                 "project_path", "last_activity_at", "raw_version")


# tarav.breadcrumb 59462ed55719
# tarav.breadcrumb 96b8209e7af7
class ChatlasSearchQuery(SearchQuery):
    """Find turns or messages, by literal text and side, in selected sessions."""

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
        target: str = "turns",
        side: str | None = None,
        provider: str | None = None,
        project: str | None = None,
        since: str | None = None,
        until: str | None = None,
        times: bool = False,
        build_missing: bool = True,
        **options,
    ) -> None:
        super().__init__(**options)
        if target not in TARGETS:
            raise ValueError(f"Chatlas search target must be one of {', '.join(TARGETS)}")
        if side not in (None, "user", "agent"):
            raise ValueError("Chatlas search side must be user or agent")
        if text is not None and not text:
            raise ValueError("Chatlas search text must not be empty")
        for name, value in (("since", since), ("until", until)):
            if value is not None and parse_chatlas_index_timestamp(value) is None:
                raise ValueError(f"Chatlas search {name} must be an ISO timestamp")
        self.text = text
        self.target = target
        self.side = side
        self.provider = provider
        self.project = project
        self.since = since
        self.until = until
        self.times = times
        self.build_missing = build_missing

    def parts(self) -> tuple[str, ...]:
        """The cached parts this query reads."""
        if self.target == "messages":
            return ("main", "messages")
        return ("main", "turns", "messages", *(("events",) if self.times else ()))

    def selects(self, row: JsonObject) -> bool:
        if row.get("provider") not in NORMALIZED_PROVIDERS:
            return False
        if self.provider is not None and row.get("provider") != self.provider:
            return False
        if self.project is not None and not _within(row.get("project_path"), self.project):
            return False
        activity = chatlas_index_timestamp_sort_value(row.get("last_activity_at"))
        if self.since is not None and activity < chatlas_index_timestamp_sort_value(self.since):
            return False
        if self.until is not None and activity > chatlas_index_timestamp_sort_value(self.until):
            return False
        return True


# tarav.breadcrumb 145c6f21a360
@dataclass(frozen=True, slots=True)
class ChatlasSearchHit:
    """One turn or message, its session's index facts, and the parts it was read from."""

    session: JsonObject
    target: str
    turn: ChatlasTurnMatch | None
    message: JsonObject | None
    parts: dict[str, CachedPart]


# tarav.breadcrumb 3cdac710a169
# tarav.breadcrumb cb26ab1d9194
class ChatlasSearchEngine(SearchEngine):
    """Search the cached Normal Models of indexed sessions, newest activity first.

    A stale cache is searched as stored and its hits say so; a missing one is
    built unless the query declines. A session that cannot be built is skipped.
    """

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

    def rows(self, query: ChatlasSearchQuery) -> list[JsonObject]:
        index = load_chatlas_session_index_rows(
            chatlas_root=self.chatlas_root,
            providers=(query.provider,) if query.provider is not None else None,
        )
        return sorted(
            (row for row in index.rows if query.selects(row)),
            key=lambda row: chatlas_index_timestamp_sort_value(row.get("last_activity_at")),
            reverse=True,
        )

    class Search(SearchEngine.Search):
        def accepts(self, query: SearchQuery) -> bool:
            return isinstance(query, ChatlasSearchQuery)

        def _iter_hits(self, query: ChatlasSearchQuery) -> Iterator[SearchHit]:
            for row in self.obj.rows(query):
                try:
                    yield from self._session_hits(query, row)
                except (CliError, ChatlasQueryError) as exc:
                    logger.debug("Chatlas search skipped %s: %s", row.get("identity_hash"), exc)

        def _session_hits(self, query: ChatlasSearchQuery, row: JsonObject) -> Iterator[SearchHit]:
            cache = NormalModelCache(row, chatlas_root=self.obj.chatlas_root)
            standing = cache.parts()
            if not all(standing[name].present for name in query.parts()):
                if not query.build_missing:
                    return
                cache.build()
                standing = cache.parts()
            model = cache.model()
            session = {key: row.get(key) for key in SESSION_FACTS}
            parts = {name: standing[name] for name in query.parts()}
            if query.target == "messages":
                needle = query.text.casefold() if query.text is not None else None
                for message in reversed(list(model.iter_messages())):
                    if query.side is not None and message.get("side") != query.side:
                        continue
                    if needle is not None and needle not in str(message.get("text", "")).casefold():
                        continue
                    yield SearchHit(ChatlasSearchHit(session, "messages", None, message, parts))
                return
            result = ChatlasQueryEngine(model).run(ChatlasQuery(
                side=query.side, text_contains=query.text, order="newest",
                limit=sys.maxsize, times=query.times,
            ))
            for match in result.matches:
                yield SearchHit(ChatlasSearchHit(session, "turns", match, None, parts))


def _within(path: object, prefix: str) -> bool:
    if not isinstance(path, str):
        return False
    root = prefix.rstrip("/")
    return path == root or path.startswith(root + "/")


__all__ = [
    "ChatlasSearchEngine",
    "ChatlasSearchHit",
    "ChatlasSearchQuery",
    "TARGETS",
]
