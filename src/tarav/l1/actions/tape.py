"""The tape of an action: the important events of its life, in order.

Each event is an entry of its own Type, appended and never changed. The
action's state is read from it: open or closed, by which exit, since when,
and the closing record of each time it closed, so reopening forgets nothing.
Git keeps every other change of the record.

Status entries (opened, closed, reopened) hold the state of the repositories
the suites above the action's checks declare: HEAD, and whether it was
clean. After a status change, the first clean state seen of each repository
is an entry of its own. What changed between two of those commits is a
`git diff`.
"""

from __future__ import annotations

from copy import deepcopy

from tarav.l0._core.git_repository import repository_states
from tarav.l0.kernel import TaravClass, TaravObject, TypeRegistry, TypeShip, entity

from .workflow import ACTIONS_WORKFLOW_SHIP
from tarav.l0.kernel import LoadedRecord


# tarav.breadcrumb 0da79fa1ca3d
# tarav.breadcrumb 68adbb4e9eec
class TapeEntry(TaravObject):
    """One event on an action's tape: when it happened, and what its Type adds."""

    class RecordInterface(TaravObject.RecordInterface):
        at: str

    def __init__(self, fields: dict) -> None:
        super().__init__()
        self.fields = dict(fields)

    @classmethod
    def _from_record(cls, loaded: LoadedRecord):
        values = loaded.data.model_dump(mode="json", exclude_unset=True)
        values.pop("type", None)
        return cls(values)

    def _to_record(self):
        return {**super()._to_record(), **self.fields}

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("2312097f-28b5-4161-ad3e-6f4b2aab8253"),
                          name="Tarav.Actions.Tape.Entry", workflow=ACTIONS_WORKFLOW_SHIP)

    class Records(TaravObject.Records):
        def record_example(self) -> dict[str, object]:
            return {"type": entity(self._owner).name, "at": "2026-10-14T00:00:00+00:00"}


class StatusChange(TapeEntry):
    """The action opened, closed or reopened; with the repository states known then."""

    class RecordInterface(TapeEntry.RecordInterface):
        repositories: dict | None = None

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("eaf9e9b7-4031-4a9b-8f93-c2e51a737d9a"),
                          name="Tarav.Actions.Tape.StatusChange", workflow=ACTIONS_WORKFLOW_SHIP)


class Opened(StatusChange):
    """The action opened: the first entry of every tape."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("09d745e0-0889-44bf-b121-fa2d76dc038d"),
                          name="Tarav.Actions.Tape.Opened", workflow=ACTIONS_WORKFLOW_SHIP)


class Reopened(StatusChange):
    """A closed action opened again, because the way it closed says so."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("e241926c-3bd0-43e5-bd58-125d0fa46a97"),
                          name="Tarav.Actions.Tape.Reopened", workflow=ACTIONS_WORKFLOW_SHIP)


class Closed(StatusChange):
    """The action closed by an exit; `closing` is the record that exit leaves.

    An `error` exit (a failed opening, an abort) leaves no closing record.
    """

    class RecordInterface(StatusChange.RecordInterface):
        exit: str
        closing: dict | None = None

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("b551875d-77fe-4ab4-b4c8-25cc653a3335"),
                          name="Tarav.Actions.Tape.Closed", workflow=ACTIONS_WORKFLOW_SHIP)

    class Records(StatusChange.Records):
        def record_example(self) -> dict[str, object]:
            return {**super().record_example(), "exit": "error"}


class Clean(TapeEntry):
    """A repository seen clean for the first time since the last status change."""

    class RecordInterface(TapeEntry.RecordInterface):
        repositories: dict

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("c974191f-1ca7-410b-a5c0-9efd7991a665"),
                          name="Tarav.Actions.Tape.Clean", workflow=ACTIONS_WORKFLOW_SHIP)

    class Records(TapeEntry.Records):
        def record_example(self) -> dict[str, object]:
            return {**super().record_example(), "repositories": {
                "/example": {"commit": "0" * 40, "clean": True}}}


# tarav.breadcrumb 5144aff51cd9
class ClosingAttempt(TapeEntry):
    """An operator or the loop tried an exit; its tests passed or did not."""

    class RecordInterface(TapeEntry.RecordInterface):
        exit: str
        by: str
        passed: bool
        results: list

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("72da3881-4223-41de-bdc3-84e809ee749d"),
                          name="Tarav.Actions.Tape.ClosingAttempt", workflow=ACTIONS_WORKFLOW_SHIP)

    class Records(TapeEntry.Records):
        def record_example(self) -> dict[str, object]:
            return {**super().record_example(), "exit": "done", "by": "operator",
                    "passed": True, "results": []}


TAPE_ENTRY_TYPES = (TapeEntry, StatusChange, Opened, Reopened, Closed, Clean, ClosingAttempt)
_ENTRIES = TypeRegistry(TapeEntry, TAPE_ENTRY_TYPES)
OPENED, REOPENED, CLOSED, CLEAN = (entity(cls).name for cls in (Opened, Reopened, Closed, Clean))
STATUS = (OPENED, REOPENED, CLOSED)


def entry(record: dict) -> TapeEntry:
    """One entry of a tape as an object of its Type."""
    return _ENTRIES.from_record(record)


def _append(run, entry_type: type[TapeEntry], **fields) -> dict:
    record = {"type": entity(entry_type).name,
              **{key: value for key, value in fields.items() if value is not None}}
    entry(record)  # an entry that does not validate is never written
    run.data.setdefault("tape", []).append(record)
    return record


# writing

def opened(run, *, at: str, states: dict | None = None) -> dict:
    return _append(run, Opened, at=at, repositories=deepcopy(states) or None)


def reopened(run, *, at: str, states: dict | None = None) -> dict:
    return _append(run, Reopened, at=at, repositories=deepcopy(states) or None)


def closed(run, exit: str, *, at: str, closing: dict | None = None,
           states: dict | None = None) -> dict:
    """Close the action on its tape. Taken outside a run of the checks, a closing
    reads the state of the action's repositories now."""
    if not states and repositories(run):
        states = repository_states(repositories(run))
    return _append(run, Closed, at=at, exit=exit, closing=closing,
                   repositories=deepcopy(states) or None)


def attempt(run, exit: str, *, by: str, at: str, passed: bool, results: list) -> dict:
    return _append(run, ClosingAttempt, at=at, exit=exit, by=by, passed=passed, results=results)


def clean(run, states: dict | None, *, at: str) -> bool:
    """Append each repository seen clean for the first time since the last status change."""
    known = repositories(run)
    if not states or not known:
        return False
    phase = _phase(run)
    added = False
    for root, state in sorted(states.items()):
        if not state["clean"] or root not in known or _clean_in(phase, root):
            continue
        phase.append(_append(run, Clean, at=at, repositories={root: dict(state)}))
        added = True
    return added


# reading

def status_entries(run) -> list[dict]:
    return [item for item in run.data["tape"] if item["type"] in STATUS]


def last_status(run) -> dict:
    return status_entries(run)[-1]


def repositories(run) -> list[str]:
    """The repositories the latest status change knew."""
    for item in reversed(status_entries(run)):
        if item.get("repositories"):
            return sorted(item["repositories"])
    return []


def waiting(run) -> list[str]:
    """The repositories with no clean state since the last status change."""
    phase = _phase(run)
    return [root for root in repositories(run) if not _clean_in(phase, root)]


def _phase(run) -> list[dict]:
    """The entries since the last status change, that change included."""
    tape = run.data["tape"]
    for index in range(len(tape) - 1, -1, -1):
        if tape[index]["type"] in STATUS:
            return tape[index:]
    return list(tape)


def _clean_in(entries: list[dict], root: str) -> bool:
    return any(((item.get("repositories") or {}).get(root) or {}).get("clean")
               for item in entries)


__all__ = [
    "CLEAN", "CLOSED", "Clean", "Closed", "ClosingAttempt", "OPENED", "Opened", "REOPENED",
    "Reopened", "STATUS", "StatusChange", "TAPE_ENTRY_TYPES", "TapeEntry", "attempt",
    "clean", "closed", "entry", "last_status", "opened", "reopened", "repositories",
    "status_entries", "waiting",
]
