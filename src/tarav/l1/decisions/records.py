"""Minimal, attributed Decision records and append-only storage."""

import json
from datetime import datetime
from pathlib import Path

from tarav.l0.kernel import FileRecord, TaravClass, TaravEntity, TypeShip, entity
from tarav.l1.scoring import Assertable

from .workflow import DECISIONS_WORKFLOW_SHIP


_assertion_provider = None


def bind_decision_assertions(provider):
    """Compose assertion construction above l1 without a reverse import."""
    global _assertion_provider
    if not callable(provider):
        raise TypeError("Decision assertion provider must be callable")
    _assertion_provider = provider


def _reference(value):
    if (not isinstance(value, dict) or not isinstance(value.get("type"), str)
            or not value["type"] or not isinstance(value.get("locator"), dict)
            or not value["locator"]):
        raise ValueError("Expected a typed reference with a locator")
    json.dumps(value, allow_nan=False)


# tarav.breadcrumb a4d91364e7bd92efcd0baf818ad4a4bf7f5323014e111a6322b179fae2a8bfc3
class Decision(TaravEntity, FileRecord, Assertable):
    """An attributed intervention; subclasses own its operational meaning."""

    class RecordInterface(TaravEntity.RecordInterface):
        created_at: str
        actor: dict
        rationale: str
        support: list[dict]

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip("2d5389a7-8433-43d1-987b-048fac2282a7"),
            name="Tarav.Decisions.Decision",
            workflow=DECISIONS_WORKFLOW_SHIP,
        )

    @classmethod
    def validate_record(cls, value):
        data = super().validate_record(value)
        stamp = datetime.fromisoformat(data.created_at)
        if stamp.tzinfo is None:
            raise ValueError("Decision time must include a timezone")
        _reference(data.actor)
        if not data.rationale.strip():
            raise ValueError("Decision requires a rationale")
        for item in data.support:
            _reference(item)
        return data

    @property
    def decider(self):
        """The existing `actor` field is the shared semantic role, not a migration."""
        return self.to_record()["actor"]

    @property
    def poi_ids(self) -> tuple[str, ...]:
        return tuple(self.to_record().get("poi_ids", ()))

    @property
    def assertions(self):
        if _assertion_provider is None:
            raise RuntimeError("Decision Assertion service has not been composed")
        return _assertion_provider(self)

    @classmethod
    def record_example(cls):
        return {
            "type": entity(cls).name,
            "id": "9205ba7f-4d2a-43c2-9fe8-9348c85ef447",
            "created_at": "2026-10-03T00:00:00+00:00",
            "actor": {"type": "Example.Actor", "locator": {"name": "example"}},
            "rationale": "Example intervention",
            "support": [],
        }


class Order(Decision):
    """A recorded instruction to change data; recording does not execute it."""

    class RecordInterface(Decision.RecordInterface):
        subjects: list[dict]
        poi_ids: list[str]

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip("e4fb9ce9-5f54-4e27-9c07-f6c326c4bcac"),
            name="Tarav.Decisions.Order",
            workflow=DECISIONS_WORKFLOW_SHIP,
        )

    @classmethod
    def validate_record(cls, value):
        data = super().validate_record(value)
        for subject in data.subjects:
            _reference(subject)
        _validate_poi_ids(data.poi_ids)
        return data

    @classmethod
    def record_example(cls):
        return {
            **super().record_example(),
            "subjects": [{"type": "Example.Data", "locator": {"path": "data.json"}}],
            "poi_ids": [],
        }


class ReportedAction(Decision):
    """A recorded account of an action; evidence can include Git references."""

    class RecordInterface(Decision.RecordInterface):
        subjects: list[dict]
        poi_ids: list[str]

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip("f3e32b49-6f89-4b66-9849-c63891af354e"),
            name="Tarav.Decisions.ReportedAction",
            workflow=DECISIONS_WORKFLOW_SHIP,
        )

    @classmethod
    def validate_record(cls, value):
        data = super().validate_record(value)
        for subject in data.subjects:
            _reference(subject)
        _validate_poi_ids(data.poi_ids)
        return data

    @classmethod
    def record_example(cls):
        return {
            **super().record_example(),
            "subjects": [{"type": "Example.Data", "locator": {"path": "data.json"}}],
            "poi_ids": [],
        }


def _validate_poi_ids(values):
    if any(not isinstance(value, str) or not value for value in values):
        raise ValueError("POI references must be nonempty identities")
    if len(values) != len(set(values)):
        raise ValueError("Duplicate POI reference")


class DecisionStore:
    """Retain non-Blessing decisions; existing blessings stay in BlessingStore."""

    def __init__(self, root, *, record_types=()):
        self.root = Path(root).resolve()
        self.record_types = {}
        for cls in (Order, ReportedAction, *record_types):
            if not issubclass(cls, Decision):
                raise TypeError("Expected a Decision type")
            name = entity(cls).name
            if name in self.record_types and self.record_types[name] is not cls:
                raise ValueError(f"Duplicate Decision type: {name}")
            self.record_types[name] = cls

    def add(self, decision: Decision):
        record = decision.to_record()
        if self.record_types.get(record["type"]) is not type(decision):
            raise TypeError("Decision type is not registered in this store")
        self.root.mkdir(parents=True, exist_ok=True)
        with (self.root / f"{decision.id}.json").open("x", encoding="utf-8") as handle:
            json.dump(record, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
        return decision

    def snapshot(self):
        records, findings = [], []
        if not self.root.exists():
            return {"records": records, "findings": findings}
        for path in sorted(self.root.glob("*.json")):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
                cls = self.record_types[record["type"]]
                cls.validate_record(record)
                if path.stem != record["id"]:
                    raise ValueError("Decision filename disagrees with identity")
            except (OSError, ValueError, TypeError, KeyError) as exc:
                findings.append({"kind": "invalid-decision-record", "path": str(path),
                                 "detail": str(exc)})
                continue
            records.append(record)
        return {"records": records, "findings": findings}

    def load(self, identity):
        for record in self.snapshot()["records"]:
            if record["id"] == str(identity):
                return self.record_types[record["type"]].from_record(record)
        raise KeyError(identity)
