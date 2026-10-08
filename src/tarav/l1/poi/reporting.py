"""POIs that were reported to an agent: retention, lookup, and their Context view.

A POI exists only while its check runs. A surface that shows one keeps what
was shown, so that the agent can ask for its context afterwards.
"""

from __future__ import annotations

import inspect
import json
import logging
import os
from collections.abc import Iterable, Iterator, Mapping
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from tarav.l0.kernel import TaravClass, TaravObject, TypeShip, entity
from tarav.l1.context import ContextBuilder, ContextFolder
from tarav.l1.context.query import ContextCandidate, IdentityContextQuery
from tarav.l1.search import SearchEngine, SearchHit, SearchQuery

from .primitives import IdentifiedPOI, POI, POIDetails
from .workflow import POI_WORKFLOW_SHIP

REPORTED_POI_VIEW = "reported-poi"
EXAMPLE_ID_LENGTH = 12
_LOG = logging.getLogger(__name__)


def guidance_of(poi_type: type[POI]) -> dict[str, list[str]]:
    """What a POI Type declares for its readers.

    A Type sets `read_first` (what to read before acting) and `may_do` (the
    responses open to the reader, including whether to raise it to the User)
    as tuples of sentences. Both default to nothing declared.
    """
    return {"read_first": [str(item) for item in getattr(poi_type, "read_first", ())],
            "may_do": [str(item) for item in getattr(poi_type, "may_do", ())]}


# tarav.breadcrumb d473114f4ea9f30435e91f06d6f8d4428f199fca20c04a03a96256fd57c646a3
def context_instruction(example_id: str | None = None) -> list[str]:
    """The one instruction a surface prints before listing POIs."""
    lines = [
        "Before acting on any POI, open its context:",
        f"  tarav context --id <poi-id> --view {REPORTED_POI_VIEW}",
    ]
    if example_id:
        lines.append(f"  e.g. tarav context --id {example_id[:EXAMPLE_ID_LENGTH]} "
                     f"--view {REPORTED_POI_VIEW}")
    lines.append("List POI ids with `tarav check --project --by identity`; "
                 "see `tarav context --help` for navigation and other views.")
    return lines


def reports_root() -> Path:
    """Machine-local folder of retained reports, one file per Project id.

    ``TARAV_CHECK_REPORTS`` relocates it, which test suites use.
    """
    override = os.getenv("TARAV_CHECK_REPORTS")
    if override:
        return Path(override).expanduser().resolve()
    home = os.getenv("TARAV_HOME")
    base = Path(home).expanduser() if home else Path.home() / ".tarav"
    return base.resolve() / "check-reports"


def _class_record(cls: type) -> dict[str, object]:
    help_ = cls.help() if hasattr(cls, "help") else {}
    return {"type": entity(cls).name,
            "description": inspect.cleandoc(cls.__dict__.get("__doc__") or ""),
            "python_class": f"{cls.__module__}.{cls.__qualname__}",
            "source_path": help_.get("source_path"), "source_line": help_.get("source_line")}


def reported_record(poi: IdentifiedPOI) -> dict[str, object]:
    """Everything the reporting process knows about one POI, as plain data."""
    check = getattr(poi, "check", None)
    return {
        "id": poi.identity, "message": poi.message,
        "situation": poi.situation, "subject": poi.subject, "evidence": poi.evidence,
        "details": deepcopy(getattr(poi, "details", {})),
        "poi_type": _class_record(type(poi)),
        "raised_by": _class_record(type(check)) if check is not None else None,
        "guidance": guidance_of(type(poi)),
    }


class ReportedPOIStore:
    """Best effort: the last report of each Project, replaced on every run."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root is not None else reports_root()

    def retain(self, pois: Iterable[POI], *, project: Mapping[str, object]) -> bool:
        try:
            records: dict[str, dict[str, object]] = {}
            for poi in pois:
                if isinstance(poi, IdentifiedPOI):
                    records.setdefault(poi.identity, reported_record(poi))
            self.root.mkdir(parents=True, exist_ok=True)
            target = self.root / f"{project['id']}.json"
            temporary = target.with_suffix(".tmp")
            temporary.write_text(json.dumps({
                "project": dict(project),
                "reported_at": datetime.now(timezone.utc).isoformat(),
                "pois": list(records.values()),
            }, default=str), encoding="utf-8")
            os.replace(temporary, target)
            return True
        except Exception:
            _LOG.warning("Could not retain reported POIs", exc_info=True)
            return False

    def reports(self) -> Iterator[dict[str, object]]:
        if not self.root.is_dir():
            return
        for path in sorted(self.root.glob("*.json")):
            try:
                yield json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue

    def find(self, identifier: str) -> list[ReportedPOI]:
        return [ReportedPOI(record, project=report.get("project") or {},
                            reported_at=str(report.get("reported_at") or ""))
                for report in self.reports() for record in report.get("pois", ())
                if str(record.get("id", "")).startswith(identifier)]


# tarav.breadcrumb c5060ce8bf710d413da1686969e5e450b369f1b6185db23bcc47f6fd9d2f291e
class ReportedPOI(TaravObject):
    """A POI as it was reported to an agent by some surface, kept for its context."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("3d7e1a96-5c0b-4e82-a3f7-9b1c4d6e8f05"),
                          name="Tarav.POI.Reported", workflow=POI_WORKFLOW_SHIP)

    def __init__(self, record: Mapping[str, object], *, project: Mapping[str, object],
                 reported_at: str = "") -> None:
        super().__init__()
        self.record = deepcopy(dict(record))
        self.project = dict(project)
        self.reported_at = reported_at

    @property
    def identity(self) -> str:
        return str(self.record["id"])

    def summary(self) -> dict[str, object]:
        return {"id": self.identity, "message": self.record.get("message"),
                "poi_type": (self.record.get("poi_type") or {}).get("type"),
                "project": self.project, "reported_at": self.reported_at}

    def obj_context(self, builder) -> None:
        builder.add("summary", opener=lambda: _value(self.summary()),
                    description="Identifier, message, Type, Project and when it was reported.")
        builder.add("record", opener=lambda: _value(self.record),
                    description="The complete retained record.")


def _value(value: object) -> POIDetails:
    return POIDetails.records.from_record(
        {"type": entity(POIDetails).name, "value": deepcopy(value)})


class ReportedPOIContext(ContextFolder):
    """What to know before acting on a POI that a surface reported."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("a94c6e2b-1f37-4d58-8b06-2e5d7c9f1a36"),
                          name="Tarav.POI.Reported.Context", workflow=POI_WORKFLOW_SHIP)

    @classmethod
    def for_subject(cls, subject):
        if not isinstance(subject, ReportedPOI):
            raise TypeError(f"{REPORTED_POI_VIEW} supports only reported POIs")
        record, guidance = subject.record, subject.record.get("guidance") or {}

        def populate(builder: ContextBuilder) -> None:
            builder.add("poi-type", opener=lambda: _value(record.get("poi_type")),
                        description="What this kind of POI is, and where its class is defined.")
            builder.add("raised-by", opener=lambda: _value(record.get("raised_by")),
                        description="The check that raised it, and where that check is defined.")
            builder.add("finding", opener=lambda: _value({
                "id": record.get("id"), "message": record.get("message"),
                "situation": record.get("situation"),
                "details": record.get("details"), "project": subject.project,
                "reported_at": subject.reported_at,
            }), description="What exactly was found in this instance.")
            builder.add("read-first", opener=lambda: _value(
                guidance.get("read_first") or
                ["This POI Type declares nothing to read; inspect poi-type and raised-by."]),
                description="What the POI Type asks you to read before acting.")
            builder.add("may-do", opener=lambda: _value(
                guidance.get("may_do") or
                ["This POI Type declares no response. A POI is a signal, not an "
                 "instruction: decide with the User whether and how to act."]),
                description="The responses open to you, and whether to raise it to the User.")

        return cls(subject, populate)


class ReportedPOIResolver(SearchEngine):
    """Find a reported POI by its identity or a unique prefix of it."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("6f0b3c8d-4e21-4a79-9c5a-7d2e8f1b0a47"),
                          name="Tarav.POI.Reported.Resolver", workflow=POI_WORKFLOW_SHIP)

    def __init__(self, store: ReportedPOIStore | None = None) -> None:
        self._store = store

    @property
    def store(self) -> ReportedPOIStore:
        return self._store if self._store is not None else ReportedPOIStore()

    class Search(SearchEngine.Search):
        def accepts(self, query: SearchQuery) -> bool:
            return (isinstance(query, IdentityContextQuery)
                    and len(query.identifier) >= 2
                    and all(char in "0123456789abcdef" for char in query.identifier))

        def _iter_hits(self, query: IdentityContextQuery) -> Iterator[SearchHit]:
            for reported in self.obj.store.find(query.identifier):
                yield SearchHit(ContextCandidate(
                    reported, reported.identity,
                    f"{reported.record.get('message')} "
                    f"[{(reported.record.get('poi_type') or {}).get('type')}]"))


__all__ = [
    "REPORTED_POI_VIEW",
    "ReportedPOI",
    "ReportedPOIContext",
    "ReportedPOIResolver",
    "ReportedPOIStore",
    "context_instruction",
    "guidance_of",
    "reported_record",
    "reports_root",
]
