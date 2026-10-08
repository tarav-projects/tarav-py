"""A Project's Decisions, retained together in one append-only place."""

import json
from pathlib import Path

from tarav.l0.kernel import current_records, entity
from tarav.l1.blessings import BlessingAssessmentRecord, BlessingRecord, BlessingStore
from tarav.l1.decisions import Decision


DECISIONS_PATH = Path(".tarav") / "decisions"


# tarav.breadcrumb 544b4812a29cde0185b634ce3fa3acd98f68daaf3e33ca64d46b79cff0f2f8df
class ProjectDecisions:
    """Every Decision subtype of one Project, one file per Record.

    The Decisions workflow owns the Type and no storage; this store is a
    Project feature. Workflows may keep Decisions elsewhere, but the Project's
    decisions are the ones retained here. Records are written once and never
    rewritten, so concurrent writers never share a file.
    """

    def __init__(self, project, *, record_types=None):
        self.project = project
        self.root = (Path(project.root) / DECISIONS_PATH).resolve()
        self._record_types = record_types

    def _types(self):
        types = (self._record_types if self._record_types is not None
                 else current_records().record_types)
        return {entity(cls).name: cls for cls in types}

    def add(self, decision):
        if not isinstance(decision, Decision):
            raise TypeError("Expected a Decision")
        record = decision.records.to_record()
        if self._types().get(record["type"]) is not type(decision):
            raise TypeError("Decision type is not registered")
        self.root.mkdir(parents=True, exist_ok=True)
        with (self.root / f"{decision.id}.json").open("x", encoding="utf-8") as handle:
            json.dump(record, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
        return decision

    # tarav.breadcrumb b87f901e5e8fc1cfbe90a587a3be5868e6b782d3c6bb4250176c399d5d8de9ee
    def snapshot(self, *, decision_type=Decision):
        """Records of `decision_type` or any subtype; other registered Records are skipped."""
        if not (isinstance(decision_type, type) and issubclass(decision_type, Decision)):
            raise TypeError("Expected a Decision type")
        records, findings = [], []
        if not self.root.exists():
            return {"records": records, "findings": findings}
        types = self._types()
        for path in sorted(self.root.glob("*.json")):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
                name = record["type"]
            except (OSError, ValueError, TypeError, KeyError) as exc:
                findings.append({"kind": "invalid-decision-record", "path": str(path),
                                 "detail": str(exc)})
                continue
            cls = types.get(name)
            if cls is None:
                findings.append({"kind": "unknown-decision-type", "path": str(path),
                                 "detail": str(name)})
                continue
            if not issubclass(cls, decision_type):
                continue
            try:
                cls.records.validate_record(record)
                if path.stem != record["id"]:
                    raise ValueError("Decision filename disagrees with identity")
            except (ValueError, TypeError, KeyError) as exc:
                findings.append({"kind": "invalid-decision-record", "path": str(path),
                                 "detail": str(exc)})
                continue
            records.append(record)
        return {"records": records, "findings": findings}

    def load(self, identity):
        types = self._types()
        for record in self.snapshot()["records"]:
            if record["id"] == str(identity):
                return types[record["type"]].records.from_record(record)
        raise KeyError(identity)

    def blessings(self):
        """The Project's blessings: a BlessingStore over this same directory."""
        types = tuple(self._types().values())
        return BlessingStore(
            self.root,
            record_types=tuple(cls for cls in types
                               if issubclass(cls, (BlessingRecord, BlessingAssessmentRecord))
                               and cls not in (BlessingRecord, BlessingAssessmentRecord)),
            other_decision_types=tuple(cls for cls in types
                                       if issubclass(cls, Decision)
                                       and not issubclass(cls, BlessingRecord)),
        )
