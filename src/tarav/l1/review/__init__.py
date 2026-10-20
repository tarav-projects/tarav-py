"""Explicit review evidence about a bounded change, separate from support."""

from typing import Literal

from pydantic import Field, model_validator

from tarav.l0.kernel import (
    LoadedRecord, Ship, TaravClass, TaravEntity, TaravWorkflow, TypedState,
    TypeShip, WorkflowShip, entity,
)
from tarav.l1.grounding import SubjectState
from tarav.l1.references import Reference

REVIEW_WORKFLOW_SHIP = WorkflowShip("a50d3c71-9fb3-428e-ae71-37ac312742ba")


class ReviewWorkflow(TaravWorkflow):
    constitution = "Retain explicit review evidence without conflating it with substantive support."

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("8cd9bcab-dc36-4933-8a30-bd9f5749856d"),
                          name="Tarav.Workflow.Review", workflow=REVIEW_WORKFLOW_SHIP)

    @classmethod
    def _workflow_id(cls):
        return REVIEW_WORKFLOW_SHIP


# tarav.breadcrumb b490de416de6
class VerbatimReview(TypedState, TaravEntity):
    """One token approval of a presented operation and exact bounded target set."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("e33e537c-d89e-49d6-8c58-799568cb63dc"),
                          name="Tarav.Review.Verbatim", workflow=REVIEW_WORKFLOW_SHIP)

    class RecordInterface(TaravEntity.RecordInterface):
        destination: Ship
        operation: Literal["add", "modify", "remove", "review"]
        before: list[SubjectState.RecordInterface]
        after: list[SubjectState.RecordInterface]
        token: str = Field(min_length=1, pattern=r"^\S+$")
        proposal: Reference.RecordInterface
        approval: Reference.RecordInterface

        @model_validator(mode="after")
        def bounded_change(self):
            if self.operation in ("add", "review") and (self.before or not self.after):
                raise ValueError("Add/review needs after states and no before states")
            if self.operation == "remove" and (not self.before or self.after):
                raise ValueError("Remove needs before states and no after states")
            if self.operation == "modify" and (not self.before or not self.after):
                raise ValueError("Modify needs before and after states")
            for states in (self.before, self.after):
                if len({state.subject_ship for state in states}) != len(states):
                    raise ValueError("A review target set cannot repeat a Ship")
            return self

    def __init__(self, *, id, destination, operation, before=(), after=(), token,
                 proposal, approval):
        super().__init__(id)
        self.typed = self.records.parse_record({
            "type": entity(type(self)).name, "id": str(id),
            "destination": str(destination), "operation": operation,
            "before": [state.records.to_record() for state in before],
            "after": [state.records.to_record() for state in after], "token": token,
            "proposal": proposal.records.to_record(), "approval": approval.records.to_record(),
        })

    def presentation(self):
        """Whitespace may wrap this payload; case and punctuation retain meaning."""
        lines = [f"Target: {self.typed.destination}", f"Operation: {self.typed.operation}"]
        for heading, states in (("Before", self.typed.before), ("After", self.typed.after)):
            lines.append(f"{heading}:")
            lines.extend(f"- {state.subject_ship}: {state.payload['text']}" for state in states)
        return "\n".join(lines)

    @classmethod
    def _from_record(cls, loaded: LoadedRecord):
        obj = cls.__new__(cls)
        TaravEntity.__init__(obj, loaded.data.id)
        obj.typed = loaded.data
        return obj

    class Records(TaravEntity.Records):
        def record_example(self):
            source = {"type": "Tarav.Chatlas.Reference.Turn", "locator": {
                "session_identity": "0" * 64, "turn_address": "0" * 64, "turn_hash": "0" * 64}}
            return {"type": entity(self._owner).name,
                    "id": "4ff001b2-7909-4e71-b316-93b4cc547930",
                    "destination": "6a51f247-3857-4205-bf48-12b44bb1648b", "operation": "review",
                    "before": [], "after": [SubjectState.records.record_example()],
                    "token": "review:example", "proposal": source, "approval": source}


REVIEW_RECORD_TYPES = (VerbatimReview,)
