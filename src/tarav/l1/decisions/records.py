"""The minimal, attributed Decision record. This workflow owns no storage."""

import json
from datetime import datetime

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
