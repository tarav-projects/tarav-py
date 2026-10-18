"""Typed objects an operator places for other workflows to take.

An operator (an agent, or anyone acting) writes its input here. A consuming
workflow does not receive it from the operator: it takes it from this place,
where it can validate it and keep what it read.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from tarav.l0.kernel import FileRecord, Ship, TaravClass, TaravEntity, TypeShip, entity
from tarav.l1.poi import fingerprint
from tarav.l1.records import RecordRegistry

from .workflow import OPERATOR_CONTEXT_WORKFLOW_SHIP, OperatorContextWorkflow


# tarav.breadcrumb 7b34e9c3c7d0
# tarav.breadcrumb 4090ac5315ff
class OperatorContext(TaravEntity, FileRecord):
    """One input object. It may name a Project, a session, both or neither.

    Subtypes declare the fields their consumer needs in `RecordInterface`.
    The object may be edited after it was placed; a consumer that cares keeps
    the hash of what it took.
    """

    class RecordInterface(TaravEntity.RecordInterface):
        created_at: str
        project: dict | None = None
        session: dict | None = None

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("70d530e3-5419-41b8-9d62-5f9ae38ea53e"),
            name="Tarav.OperatorContext",
            workflow=OPERATOR_CONTEXT_WORKFLOW_SHIP,
        )

    def __init__(self, id: Ship, *, created_at: str, project: dict | None = None,
                 session: dict | None = None, **fields: object) -> None:
        super().__init__(id)
        self.created_at = created_at
        self.project = project
        self.session = session
        self.fields = dict(fields)

    @classmethod
    def new(cls, *, project: dict | None = None, session: dict | None = None,
            **fields: object):
        return cls(Ship(str(uuid4())), created_at=datetime.now(timezone.utc).isoformat(),
                   project=project, session=session, **fields)

    @classmethod
    def _from_record(cls, data):
        values = data.model_dump(mode="json", exclude_unset=True)
        values.pop("type", None)
        values.pop("id")
        return cls(data.id, **values)

    def _to_record(self):
        record = {**super()._to_record(), "created_at": self.created_at, **self.fields}
        if self.project is not None:
            record["project"] = self.project
        if self.session is not None:
            record["session"] = self.session
        return record

    class Records(TaravEntity.Records):
        def validate_record(self, value):
            data = super().validate_record(value)
            if datetime.fromisoformat(data.created_at).tzinfo is None:
                raise ValueError("Operator Context time must include a timezone")
            return data

        def record_example(self) -> dict[str, object]:
            return {"type": entity(self._owner).name,
                    "id": "d2ee1731-2cf2-4b7f-a8e1-7781db5b14a8",
                    "created_at": "2026-10-09T00:00:00+00:00"}


@dataclass(frozen=True)
class Intake:
    """What a consumer took: the object, its record as read, and that record's hash."""

    context: OperatorContext
    record: dict
    hash: str

    @property
    def id(self) -> str:
        return str(self.context.id)


# tarav.breadcrumb c0bf38cbd139
class OperatorContextStore:
    """The workflow's partition of the Record Registry: one record per object."""

    def __init__(self, registry: RecordRegistry | None = None) -> None:
        self.map = (registry or RecordRegistry()).for_workflow(OperatorContextWorkflow)

    def put(self, context: OperatorContext) -> str:
        """Place an object, or replace the one with the same identity."""
        if not isinstance(context, OperatorContext):
            raise TypeError("Expected an OperatorContext")
        self.map.create()
        key = str(context.id)
        if self.map.path(key).is_file():
            if self.map.load(key).records.to_record() == context.records.to_record():
                return key
            self.map.replace(key, context)
        else:
            self.map.insert(key, context)
        self.map.commit((key,), f"Place operator context {key}")
        return key

    def names(self) -> tuple[str, ...]:
        self.map.create()
        return self.map.names()

    def load(self, key: str) -> OperatorContext:
        self.map.create()
        loaded = self.map.load(key)
        if not isinstance(loaded, OperatorContext):
            raise TypeError(f"Record {key} is not an Operator Context")
        return loaded

    def take(self, key: str, *, expected: type[OperatorContext] = OperatorContext) -> Intake:
        """Read one object for a consumer, validated, with the hash of what was read."""
        context = self.load(key)
        if not isinstance(context, expected):
            raise TypeError(
                f"Operator Context {key} is {entity(type(context)).name}, "
                f"not {entity(expected).name}"
            )
        record = context.records.to_record()
        return Intake(context, record, fingerprint(record))


OPERATOR_CONTEXT_RECORD_TYPES = (OperatorContext,)

__all__ = [
    "Intake", "OPERATOR_CONTEXT_RECORD_TYPES", "OPERATOR_CONTEXT_WORKFLOW_SHIP",
    "OperatorContext", "OperatorContextStore", "OperatorContextWorkflow",
]
