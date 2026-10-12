"""Finding an action from an identifier, for the Context command."""

from __future__ import annotations

from collections.abc import Callable, Iterator

from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l1.context.query import ContextCandidate, IdentityContextQuery
from tarav.l1.search import SearchEngine, SearchHit, SearchQuery

from . import ACTIONS_WORKFLOW_SHIP, CLOSED, ActionRun, ActionRunStore


def standing(run: ActionRun) -> str:
    """How an action stands, in one word: open, or the exit it closed by."""
    return run.exit if run.state == CLOSED else "open"


# tarav.breadcrumb 800d9e604f294f79cac459869ee807a71c74f36c0661a1e6466357a28dba6d32
class ActionResolver(SearchEngine):
    """Find an action by its own id, or by the id of the POI it follows.

    A unique prefix is enough. The action is what persists, so the id of a
    POI leads to its action; a POI without an action is found nowhere.
    """

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("9e8320ca-87e3-4b7c-9809-f6332cfaa96a"),
                          name="Tarav.Actions.Resolver", workflow=ACTIONS_WORKFLOW_SHIP)

    def __init__(self, store: Callable[[], ActionRunStore] = ActionRunStore) -> None:
        self._store = store

    class Search(SearchEngine.Search):
        def accepts(self, query: SearchQuery) -> bool:
            return (isinstance(query, IdentityContextQuery) and len(query.identifier) >= 2
                    and all(char in "0123456789abcdef-" for char in query.identifier))

        def _iter_hits(self, query: IdentityContextQuery) -> Iterator[SearchHit]:
            wanted = query.identifier
            for run in self.obj._store().list():
                poi = (run.data.get("event") or {}).get("poi") or {}
                if str(run.id).startswith(wanted) or str(poi.get("id", "")).startswith(wanted):
                    label = (f"{poi.get('message')} [{poi.get('type')}]" if poi
                             else run.data["action"])
                    yield SearchHit(ContextCandidate(run, str(run.id),
                                                     f"{label} {standing(run)}"))


__all__ = ["ActionResolver", "standing"]
