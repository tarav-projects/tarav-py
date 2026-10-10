"""Reading the action that follows a POI: a Context view and its resolver."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from copy import deepcopy

from tarav.l0.kernel import TaravClass, TypeShip, entity
from tarav.l1.context import ContextBuilder, ContextFolder
from tarav.l1.context.query import ContextCandidate, IdentityContextQuery
from tarav.l1.poi import POIDetails
from tarav.l1.poi.reporting import REPORTED_POI_VIEW
from tarav.l1.search import SearchEngine, SearchHit, SearchQuery

from . import ACTIONS_WORKFLOW_SHIP, CLOSED, ActionRun, ActionRunStore

POI_ACTION_VIEW = "poi-action"


def _value(content: object) -> POIDetails:
    return POIDetails.records.from_record(
        {"type": entity(POIDetails).name, "value": deepcopy(content)})


def standing(run: ActionRun) -> str:
    """How an action stands, in one word: open, or the exit it closed by."""
    return run.exit if run.state == CLOSED else "open"


# tarav.breadcrumb 0cf74a1ed50374597b1cfc2dd2f20a910232367cc9fe662654df29326b22a4f4
class POIActionContext(ContextFolder):
    """The action a POI spun: how it stands, the event behind it, and how to act on it."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("7d106a7c-1394-437b-b839-8dd4b61433a6"),
                          name="Tarav.Actions.POI.Context", workflow=ACTIONS_WORKFLOW_SHIP)

    @classmethod
    def for_subject(cls, subject):
        if not isinstance(subject, ActionRun) or not subject.data.get("event"):
            raise TypeError(f"{POI_ACTION_VIEW} supports only the actions of POIs")
        data, run_id = subject.data, str(subject.id)
        event = data["event"]

        def populate(builder: ContextBuilder) -> None:
            builder.add("standing", opener=lambda: _value({
                "standing": standing(subject), "state": data["state"], "exit": data["exit"],
                "opened_at": data["opened_at"], "closed_at": data["closed_at"],
                "first_opened_at": data["started_at"]}),
                description="Open, or the exit it closed by. `gone` and `dismissed` are "
                            "different endings: read which one.")
            builder.add("poi", opener=lambda: _value(event.get("poi")),
                        description="The POI as it was raised when this action opened.")
            builder.add("check", opener=lambda: _value({
                **(event.get("check") or {}), "subject": data.get("subject")}),
                description="The check that raised it and what that check examines. A "
                            "check that names neither closes this action only in a whole run.")
            builder.add("dismissal", opener=lambda: _value(
                data["output"] if data["exit"] == "dismissed" else
                "Not dismissed. A dismissal records who dismissed it and why."),
                description="The reason and the operator, when it was dismissed.")
            builder.add("closings", opener=lambda: _value(data["closings"]),
                        description="Each attempt to take an exit, by whom, and its tests.")
            builder.add("acting", opener=lambda: _value([
                "tarav operator-context put --type Tarav.Actions.POI.DismissalInput "
                "--data '{\"reason\": \"<why>\"}'",
                f"tarav action close --run {run_id} --exit dismissed --context <input id>",
                "Dismissing overrules the check for this exact situation; it needs a reason. "
                "The exit `gone` is taken when the check no longer raises the POI.",
                "The skill module tarav-pkg/references/step-actions.md describes the loop."]),
                description="The commands that act on this action.")
            builder.add("history", opener=lambda: _value(
                [f"git -C <actions registry> log -p -- records/{run_id}.json",
                 "The record holds the current state. Its past states are the Git history "
                 "of its file in the Actions registry; `tarav action list` prints the "
                 "registry's location."]),
                description="Where the earlier states of this action are.")
            builder.add("reported", opener=lambda: _value(
                [f"tarav context --id {(event.get('poi') or {}).get('id')} "
                 f"--view {REPORTED_POI_VIEW}",
                 "Opens the POI as last reported on this machine, with its Type's notes. "
                 "Absent when it was not in the last report."]),
                description="The command that opens the reported POI.")

        return cls(subject, populate)


class POIActionResolver(SearchEngine):
    """Find a POI's action by the POI identity or the action id, for the action view."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("9e8320ca-87e3-4b7c-9809-f6332cfaa96a"),
                          name="Tarav.Actions.POI.Resolver", workflow=ACTIONS_WORKFLOW_SHIP)

    def __init__(self, store: Callable[[], ActionRunStore] = ActionRunStore) -> None:
        self._store = store

    class Search(SearchEngine.Search):
        def accepts(self, query: SearchQuery) -> bool:
            return (isinstance(query, IdentityContextQuery)
                    and query.view == POI_ACTION_VIEW and len(query.identifier) >= 2
                    and all(char in "0123456789abcdef-" for char in query.identifier))

        def _iter_hits(self, query: IdentityContextQuery) -> Iterator[SearchHit]:
            wanted = query.identifier
            for run in self.obj._store().list():
                poi = (run.data.get("event") or {}).get("poi") or {}
                if not poi:
                    continue
                if str(poi.get("id", "")).startswith(wanted) or str(run.id).startswith(wanted):
                    yield SearchHit(ContextCandidate(
                        run, str(run.id),
                        f"{poi.get('message')} [{poi.get('type')}] {standing(run)}"))


__all__ = ["POIActionContext", "POIActionResolver", "POI_ACTION_VIEW", "standing"]
