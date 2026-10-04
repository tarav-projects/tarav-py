"""Independently runnable, bound checks and their execution snapshots."""

from collections.abc import Iterable, Mapping
from copy import deepcopy
from typing import Literal

from tarav.l0.kernel import (
    LiteRecord,
    TaravClass,
    TaravObject,
    TaravType,
    TaravWorkflow,
    TypeShip,
    WorkflowShip,
    entity,
)
from tarav.l1.poi import IdentifiedPOI, POI, POIDetails, POIProvider, POIError

CHECKS_WORKFLOW_SHIP = WorkflowShip("44fc55a7-771e-4b63-8b38-6641a5069fc7")


class ChecksWorkflow(TaravWorkflow):
    workflow_name = "checks"
    constitution = "Run bounded checks and expose their results without prescribing responses."

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("f8d341a7-1774-42e1-a806-c6fd6a18ae3b"),
                          name="Tarav.Workflow.Checks", workflow=CHECKS_WORKFLOW_SHIP)

    @classmethod
    def _workflow_id(cls):
        return CHECKS_WORKFLOW_SHIP


class CheckProvider(TaravType):
    """Optional subject capability; checks are already bound when exposed."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("fb89da94-f920-47a1-979e-1ed8e521ea13"),
                          name="Tarav.Checks.Provider", workflow=CHECKS_WORKFLOW_SHIP)

    @property
    def checks(self) -> Iterable["Check"]:
        raise NotImplementedError


# tarav.breadcrumb 8f9efe635d3ac2a87d8d913d499580f8a2fc652d3424a6c5b5df282dd09714c5
class Check(TaravObject):
    """Reusable behavior bound to the inputs of one execution."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("b119e6eb-cc5e-4da6-8296-1d33e9f4e303"),
                          name="Tarav.Checks.Check", workflow=CHECKS_WORKFLOW_SHIP)

    def run(self) -> "CheckResult":
        result = self._run()
        if not isinstance(result, CheckResult):
            raise TypeError("Check._run() must return CheckResult")
        if result.check is not self:
            raise ValueError("CheckResult belongs to a different Check")
        return result

    def _run(self) -> "CheckResult":
        raise NotImplementedError


class Situation(LiteRecord):
    """The detached input and acceptance scope of a SituationCheck."""


# tarav.breadcrumb 0fbb6aeabe9a6b2dfb9a5f0b09d35e49a271b44f1cce37d88557bf09e452092f
class CheckPOI(IdentifiedPOI):
    """A POI explained by the bound Check object that produced it."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("20ad2c76-009f-4aae-a564-70b7925664ef"),
                          name="Tarav.Checks.POI", workflow=CHECKS_WORKFLOW_SHIP)

    def __init__(self, check: Check, code: str, message: str, *,
                 situation,
                 details: dict | None = None, failure: bool = True,
                 subject: dict | None = None, evidence: dict | None = None) -> None:
        if not isinstance(check, Check):
            raise TypeError("CheckPOI requires a bound Check object")
        self.check = check
        self.details = deepcopy(details or {})
        if not isinstance(failure, bool):
            raise TypeError("CheckPOI failure must be a boolean")
        self.failure = failure
        super().__init__(code, message,
                         situation=situation,
                         subject=deepcopy(subject if subject is not None else self.details),
                         evidence=deepcopy(evidence if evidence is not None else self.details))

    def as_dict(self, *, detail: bool = False) -> dict[str, object]:
        return {**super().as_dict(detail=detail),
                "check": entity(type(self.check)).to_record(),
                "details": deepcopy(self.details), "failure": self.failure}

    # tarav.breadcrumb 98efb14446fdafc5cbb4a98e2d0d162e31638150e69ea0198d0c4c6c3e0f7cd9
    def obj_context(self, builder) -> None:
        super().obj_context(builder)
        builder.add("check", opener=lambda: self.check)
        builder.add("details", opener=lambda: POIDetails.from_record(
            {"type": entity(POIDetails).name, "value": deepcopy(self.details)}))

    def error(self) -> None:
        raise POIError(self)


# tarav.breadcrumb 17b06b58dc7c456e499067ef1304e2930c95b04b89c82e74b3a378d48ca7789a
class SituationCheck(Check):
    """A Check whose evaluation and POI identity share one input snapshot."""

    SituationType: type[Situation] = Situation

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("08ff8640-a0da-45af-902b-e1e9b42d704c"),
            name="Tarav.Checks.SituationCheck",
            workflow=CHECKS_WORKFLOW_SHIP,
        )

    def __init__(self, *, situation: Mapping[str, object] | LiteRecord) -> None:
        super().__init__()
        situation_type = type(self).SituationType
        if not isinstance(situation_type, type) or not issubclass(situation_type, Situation):
            raise TypeError("SituationType must extend Situation")
        self._situation = situation_type(situation)

    @property
    def situation(self) -> Situation:
        return self._situation

    def obj_context(self, builder) -> None:
        builder.add(
            "situation",
            opener=lambda: POIDetails.from_record({
                "type": entity(POIDetails).name,
                "value": self._situation.to_json_value(),
            }),
        )

    def finding(
        self,
        poi_type: type[CheckPOI],
        *,
        code: str,
        message: str,
        details: dict | None = None,
        failure: bool = True,
        subject: dict | None = None,
        evidence: dict | None = None,
    ) -> CheckPOI:
        """Construct a bound POI using exactly this Check's Situation."""

        if not isinstance(poi_type, type) or not issubclass(poi_type, CheckPOI):
            raise TypeError("SituationCheck findings require a CheckPOI Type")
        return poi_type(
            self,
            code,
            message,
            situation=self._situation,
            details=details,
            failure=failure,
            subject=subject,
            evidence=evidence,
        )

    def run(self) -> "CheckResult":
        result = super().run()
        for poi in result.pois():
            if not isinstance(poi, CheckPOI):
                continue
            poi_situation = LiteRecord.from_json_value(poi.situation)
            if poi_situation.canonical != self._situation.canonical:
                raise ValueError("SituationCheck POI uses a different situation")
        return result


class CheckResult(TaravObject, POIProvider):
    """One execution snapshot; inspecting POIs never reruns its Check."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("d0cd0250-bae5-45a5-b660-6b26115b682b"),
                          name="Tarav.Checks.Result", workflow=CHECKS_WORKFLOW_SHIP)

    def __init__(self, check: Check, *, status: Literal["completed", "incomplete", "failed"],
                 pois: Iterable[POI] = (), data: object = None,
                 reason: str | None = None) -> None:
        super().__init__()
        if status not in ("completed", "incomplete", "failed"):
            raise ValueError("Unknown Check execution status")
        self.check = check
        self.status = status
        self.data = deepcopy(data)
        self.reason = reason
        self._pois = tuple(pois)
        if any(not isinstance(poi, POI) for poi in self._pois):
            raise TypeError("CheckResult POIs must be POIs")
        if any(isinstance(poi, CheckPOI) and poi.check is not check for poi in self._pois):
            raise ValueError("CheckResult contains a POI from another Check")

    def pois(self) -> tuple[POI, ...]:
        return self._pois


def run_checks(checks: Iterable[Check]) -> tuple[CheckResult, ...]:
    """Run selected checks exactly once; exceptions remain visible to callers."""
    return tuple(check.run() for check in checks)


def check_report(results: Iterable[CheckResult]) -> dict[str, object]:
    """Plain, JSON-ready data for executed results; it never reruns a Check."""
    rows = []
    for result in results:
        if not isinstance(result, CheckResult):
            raise TypeError("check_report() expects CheckResults")
        rows.append({
            "check": entity(type(result.check)).name,
            "status": result.status,
            "reason": result.reason,
            "pois": [poi.as_dict() for poi in result.pois()],
        })
    return {
        "checks": len(rows),
        "incomplete": sum(row["status"] != "completed" for row in rows),
        "pois": sum(len(row["pois"]) for row in rows),
        "results": rows,
    }


__all__ = [
    "ChecksWorkflow",
    "Check",
    "CheckPOI",
    "CheckProvider",
    "CheckResult",
    "Situation",
    "SituationCheck",
    "check_report",
    "run_checks",
]
