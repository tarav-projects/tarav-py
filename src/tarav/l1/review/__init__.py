"""Explicit review evidence about a bounded change, separate from support."""

from typing import Literal

from pydantic import Field, model_validator

from tarav.l0.kernel import (
    LoadedRecord, Ship, TaravClass, TaravEntity, TaravWorkflow, TypedState,
    TypeShip, WorkflowShip, entity,
)
from tarav.l1.grounding import resolve_subject
from tarav.l0.kernel.current import current_records
from tarav.l1.references import Reference

REVIEW_WORKFLOW_SHIP = WorkflowShip("a50d3c71-9fb3-428e-ae71-37ac312742ba")


def review_presentation(destination, operation, *, before=(), after=(), records=None):
    """Render the proposed change before any approval reference exists."""
    lines = [f"Target: {destination}", f"Operation: {operation}"]
    for heading, states in (("Before", before), ("After", after)):
        lines.append(f"{heading}:")
        states = [resolve_subject(state, records=records) for state in states]
        if len({state.subject_ship for state in states}) != len(states):
            raise ValueError("A review target set cannot repeat a Ship")
        for state in states:
            lines.extend((f"- {state.subject_ship}: {state.payload['text']}",
                          f"  State: {state.digest}"))
    return "\n".join(lines)


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
        before: list[Reference.RecordInterface]
        after: list[Reference.RecordInterface]
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
                if len({state.model_dump_json() for state in states}) != len(states):
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

    def presentation(self, *, records=None):
        """Whitespace may wrap this payload; case and punctuation retain meaning."""
        return review_presentation(self.typed.destination, self.typed.operation,
                                   before=self.typed.before, after=self.typed.after, records=records)

    def ships(self):
        references = [current_records().from_record(state.model_dump(mode="json"))
                      for state in (*self.typed.before, *self.typed.after)]
        return tuple(dict.fromkeys((*super().ships(), self.typed.destination,
                                    *(ship for ref in references for ship in ref.ships()))))

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
                    "before": [], "after": [
                        {"type": "Tarav.Reference.GitFile", "locator": {
                            "repository": "/example/notebook", "commit": "0" * 40,
                            "path": "records/3c2713da-cd9b-43ed-95fe-5c5a18d10fa6.json"}}],
                    "token": "review:example", "proposal": source, "approval": source}


REVIEW_RECORD_TYPES = (VerbatimReview,)
