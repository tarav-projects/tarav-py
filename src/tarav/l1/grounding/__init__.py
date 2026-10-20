"""Retained claims that evidence supports an identified subject state."""

import hashlib
import json

from pydantic import Field, model_validator

from tarav.l0.kernel import (
    LoadedRecord, Ship, TaravClass, TaravEntity, TaravObject, TaravWorkflow,
    TypedState, TypeShip, WorkflowShip, entity,
)
from tarav.l1.references import Reference

GROUNDING_WORKFLOW_SHIP = WorkflowShip("c137b972-9141-44d6-88ca-8aa18664049e")


class GroundingWorkflow(TaravWorkflow):
    constitution = "Retain attributed support relationships without asserting their semantic adequacy."

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("e1bacf98-37bf-4bfa-8fef-05b059b781df"),
                          name="Tarav.Workflow.Grounding", workflow=GROUNDING_WORKFLOW_SHIP)

    @classmethod
    def _workflow_id(cls):
        return GROUNDING_WORKFLOW_SHIP


def state_digest(ship, type_ship, payload):
    value = [str(ship), str(type_ship), payload]
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


# tarav.breadcrumb 8307cb68b925
class SubjectState(TypedState, TaravObject):
    """An inspectable state coordinate; no general history or succession policy."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("e3bcfc53-16dc-46f5-8ac3-83997bcbf35e"),
                          name="Tarav.Grounding.SubjectState", workflow=GROUNDING_WORKFLOW_SHIP)

    class RecordInterface(TaravObject.RecordInterface):
        subject_ship: Ship
        subject_type: TypeShip
        payload: dict
        digest: str = Field(pattern=r"^[0-9a-f]{64}$")

        @model_validator(mode="after")
        def content_matches(self):
            if self.digest != state_digest(self.subject_ship, self.subject_type, self.payload):
                raise ValueError("Subject state digest disagrees with its snapshot")
            return self

    def __init__(self, subject_ship, subject_type, payload):
        super().__init__()
        payload = json.loads(json.dumps(payload, allow_nan=False))
        self.typed = self.records.parse_record({
            "type": entity(type(self)).name, "subject_ship": str(subject_ship),
            "subject_type": str(subject_type), "payload": payload,
            "digest": state_digest(subject_ship, subject_type, payload),
        })

    class Records(TaravObject.Records):
        def record_example(self):
            return self._owner(Ship("3c2713da-cd9b-43ed-95fe-5c5a18d10fa6"),
                               entity(SubjectState).id, {"text": "Example"}).records.to_record()

    def ships(self):
        return (*super().ships(), self.typed.subject_ship, self.typed.subject_type)


class SupportMember(TypedState, TaravObject):
    """One substantive source, with optional contextual references."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("8746150d-fd92-4304-a19d-8aa0e7443226"),
                          name="Tarav.Grounding.SupportMember", workflow=GROUNDING_WORKFLOW_SHIP)

    class RecordInterface(TaravObject.RecordInterface):
        source: Reference.RecordInterface
        neighborhood: list[Reference.RecordInterface] = Field(default_factory=list)

    def __init__(self, source, *, neighborhood=()):
        super().__init__()
        self.typed = self.records.parse_record({
            "type": entity(type(self)).name, "source": source.records.to_record(),
            "neighborhood": [ref.records.to_record() for ref in neighborhood],
        })

    class Records(TaravObject.Records):
        def record_example(self):
            return {"type": entity(self._owner).name,
                    "source": {"type": "Tarav.Reference.File", "locator": "/example/source"},
                    "neighborhood": []}


# tarav.breadcrumb e436a0dd5675
class SupportSet(TypedState, TaravEntity):
    """Evidence for exactly one captured subject state; review is independent."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("149c948c-e024-47f3-af08-0421fe950c80"),
                          name="Tarav.Grounding.SupportSet", workflow=GROUNDING_WORKFLOW_SHIP)

    class RecordInterface(TaravEntity.RecordInterface):
        subject: SubjectState.RecordInterface
        members: list[SupportMember.RecordInterface]
        producer: Reference.RecordInterface | None = None

    def __init__(self, *, id, subject, members=(), producer=None):
        super().__init__(id)
        self.typed = self.records.parse_record({
            "type": entity(type(self)).name, "id": str(id),
            "subject": subject.records.to_record(),
            "members": [member.records.to_record() for member in members],
            "producer": producer.records.to_record() if producer is not None else None,
        })

    @classmethod
    def _from_record(cls, loaded: LoadedRecord):
        obj = cls.__new__(cls)
        TaravEntity.__init__(obj, loaded.data.id)
        obj.typed = loaded.data
        return obj

    class Records(TaravEntity.Records):
        def record_example(self):
            return self._owner(id=Ship("d862c270-70f4-488d-ae32-45fbf64ce1de"),
                               subject=SubjectState.records.from_record(
                                   SubjectState.records.record_example())).records.to_record()

    def ships(self):
        return (*super().ships(), self.typed.subject.subject_ship)


GROUNDING_RECORD_TYPES = (SubjectState, SupportMember, SupportSet)
