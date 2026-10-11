"""Blessings: closing a POI's action although its situation still exists.

A blessing is one of the ways a POI's action closes. Taking that path leaves
a Blessing, the closing record, which keeps who blessed, why, and on what
evidence. The POI can still be raised; its action stays closed.

These Types belong to the Blessings workflow. They live beside the Actions
code because they are built from it, and the Blessings package stays free of
imports from Actions.
"""

from __future__ import annotations

from tarav.l0.kernel import LiteRecord, TaravClass, TypeShip
from tarav.l1.assertions import Assertable
from tarav.l1.checks import CheckPOI, CheckResult, SituationCheck
from tarav.l1.operator_context import OPERATOR_CONTEXT_WORKFLOW_SHIP, OperatorContext
from tarav.l1.poi import fingerprint

from tarav.l1.blessings.workflow import BLESSINGS_WORKFLOW_SHIP

from . import OPERATOR, ActionRun, Closing, StepAction

BLESSED = "blessed"

_assertion_provider = None
_score_provider = None


def bind_blessing_assertion_services(*, assertions, scores) -> None:
    """Compose higher-layer scoring behavior without reversing l1 imports."""

    global _assertion_provider, _score_provider
    if not callable(assertions) or not callable(scores):
        raise TypeError("Blessing assertion services must be callable")
    _assertion_provider = assertions
    _score_provider = scores


class BlessingInput(OperatorContext):
    """An operator's reason for blessing a POI's action, and the evidence offered for it."""

    class RecordInterface(OperatorContext.RecordInterface):
        reason: str
        support: list[dict] = []

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("6f4a2d7e-1c39-4b85-a0d6-3e9b7c5f1a28"),
                          name="Tarav.Blessings.Input",
                          workflow=OPERATOR_CONTEXT_WORKFLOW_SHIP)

    class Records(OperatorContext.Records):
        def record_example(self) -> dict[str, object]:
            return {**super().record_example(), "reason": "Accepted as it is.", "support": []}


class BlessingWithoutReason(CheckPOI):
    """A blessing was attempted and its input gives no reason."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("b3e8c1f5-9d27-4a60-8c4b-7f2e5a9d0c13"),
                          name="Tarav.Blessings.WithoutReason",
                          workflow=BLESSINGS_WORKFLOW_SHIP)


class BlessingNotPermitted(CheckPOI):
    """A blessing was attempted on the action of a POI whose Type does not allow it."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("f4c81d27-6b39-4e05-a7d2-9c1e5b8f3a64"),
                          name="Tarav.Blessings.NotPermitted",
                          workflow=BLESSINGS_WORKFLOW_SHIP)


class BlessingInputCheck(SituationCheck):
    """Does the POI's Type allow a blessing, and does the operator's input give a reason?"""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("d7a5f3b9-2e61-4c08-9b7d-1a4c8e6f2d35"),
                          name="Tarav.Blessings.InputCheck",
                          workflow=BLESSINGS_WORKFLOW_SHIP)

    def __init__(self, run: ActionRun, context: OperatorContext) -> None:
        super().__init__(situation={"run": str(run.id), "context": str(context.id)})
        self._reason = context.fields.get("reason")
        self._support = context.fields.get("support", [])
        self._event = run.data.get("event") or {}

    def _run(self) -> CheckResult:
        pois = []
        if not self._event.get("blessable"):
            pois.append(self.poi(
                BlessingNotPermitted,
                message=f"{(self._event.get('poi') or {}).get('type')} does not allow a blessing"))
        if not (isinstance(self._reason, str) and self._reason.strip()):
            pois.append(self.poi(BlessingWithoutReason,
                                 message="The blessing input gives no reason"))
        return CheckResult(self, status="completed", pois=pois)


# tarav.breadcrumb 63c7d5fd87c8a0c3f766c40dd61a2ca4f1acf559427b3490a780b1238ee81567
# tarav.breadcrumb 0e5a757eeb2c8fc966625261321583680b2aa03a38505f9e71758dd7ea0878eb
class Blessing(Closing, Assertable):
    """The record of an action closed although its POI's situation still exists.

    It keeps the actor, the reason, the evidence offered and the POI as it
    stood. Like any object it can declare assertions; scores belong to the
    scoring system and attach to those assertions, never to this record.
    """

    class RecordInterface(Closing.RecordInterface):
        actor: dict | None
        reason: str
        support: list[dict]
        poi: dict
        context: str

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("5e581ff4-10d4-4b32-a9bc-193330e85e59"),
                          name="Tarav.Blessings.Blessing", workflow=BLESSINGS_WORKFLOW_SHIP)

    @classmethod
    def fields(cls, action: StepAction, run: ActionRun,
               context: OperatorContext | None) -> dict:
        if context is None:
            raise ValueError("A blessing needs the operator's input")
        return {"actor": (run.data["sessions"] or [None])[-1],
                "reason": context.fields["reason"].strip(),
                "support": list(context.fields.get("support") or []),
                "poi": (run.data.get("event") or {}).get("poi") or {},
                "context": str(context.id)}

    @classmethod
    def reopens(cls, record: dict | None, poi: object) -> bool:
        return False  # the situation is expected to still exist

    @property
    def assertions(self):
        """The typed Assertions this exact blessing declares."""
        if _assertion_provider is None:
            raise RuntimeError("Blessing Assertion service has not been composed")
        return _assertion_provider(self)

    def score_vector(self, repository):
        """Read scorer-owned results by Assertion identity without copying scores here."""
        if _score_provider is None:
            raise RuntimeError("Blessing scoring service has not been composed")
        return _score_provider(self, repository)

    class Records(Closing.Records):
        def validate_record(self, value):
            data = super().validate_record(value)
            poi = value["poi"]
            try:
                TypeShip(poi["class_id"])
                LiteRecord.from_json_value(poi["situation"])
                expected = fingerprint([poi["class_id"], poi["situation"]])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("A Blessing keeps the identified POI it blesses") from exc
            if poi.get("id") != expected:
                raise ValueError("A Blessing's POI identity does not match its situation")
            if not value["reason"].strip():
                raise ValueError("A Blessing needs a reason")
            return data

        def record_example(self) -> dict[str, object]:
            poi = {"type": "Example.BlessablePOI",
                   "class_id": "b21f7c50-0a4d-4e63-9c18-5d7e3f2a6b90",
                   "message": "Synthetic POI", "situation": {"example": "situation"}}
            poi["id"] = fingerprint([poi["class_id"], poi["situation"]])
            return {**super().record_example(), "exit": BLESSED, "by": OPERATOR,
                    "actor": {"provider": "example", "session_id": "example"},
                    "reason": "Synthetic Record example", "support": [], "poi": poi,
                    "context": "2f0d6c1e-8a47-4b93-9d5e-7c3a1b6f4e80"}


BLESSING_RECORD_TYPES = (Blessing, BlessingInput)

__all__ = [
    "BLESSED", "BLESSING_RECORD_TYPES", "Blessing", "BlessingInput", "BlessingInputCheck",
    "BlessingNotPermitted", "BlessingWithoutReason", "bind_blessing_assertion_services",
]
