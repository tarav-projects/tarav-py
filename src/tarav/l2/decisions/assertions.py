"""A minimal assessable claim for an attributed Decision record."""

from uuid import UUID

from tarav.l0.kernel import TaravClass, TypeShip, entity
from tarav.l1.decisions import Decision
from tarav.l1.decisions.workflow import DECISIONS_WORKFLOW_SHIP
from tarav.l2.scoring import Assertion, AssertionNamespace


# tarav.breadcrumb 92020c47c5c6
class DecisionReportAssertion(Assertion):
    """The retained account accurately describes this intervention.

    No assessment case is prescribed yet; unassessed remains visible to scoring.
    """

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip("6cc86d48-3edb-4cb5-859e-032925dee23e"),
            name="Tarav.Decisions.Report.Assertion",
            workflow=DECISIONS_WORKFLOW_SHIP,
        )

    @classmethod
    def validate_subject(cls, subject):
        value = super().validate_subject(subject)
        if value.get("type") != "Tarav.Decisions.Record.Reference":
            raise ValueError("Expected a Decision record reference")
        UUID(str(value["decision_id"]))
        TypeShip(value["decision_type_id"])
        return value

    @classmethod
    def from_decision(cls, decision: Decision):
        if not isinstance(decision, Decision):
            raise TypeError("Expected a Decision")
        return cls({
            "type": "Tarav.Decisions.Record.Reference",
            "decision_id": str(decision.id),
            "decision_type_id": str(entity(type(decision)).id),
        })

    class Records(Assertion.Records):
        def record_example(self):
            cls = self._owner
            return cls.from_decision(Decision.records.from_record(Decision.records.record_example())).records.to_record()



def assertions_for_decision(decision: Decision):
    return AssertionNamespace({"main": DecisionReportAssertion.from_decision(decision)})
