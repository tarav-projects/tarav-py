"""Independently runnable, bound checks and their execution snapshots."""

from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from copy import deepcopy
from typing import Literal

from tarav.l0.kernel import (
    LiteRecord,
    NamespaceBase,
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

    # tarav.breadcrumb 03380d96ad2b3416cfcf50b86c09190ccafb830186ad79d9ea47a34bd84c18e3
    class Checks(NamespaceBase["CheckProvider"]):
        """Bound access to a provider's Checks."""

        # tarav.breadcrumb 64a1988372d66010f27742f66c4dbd78874dd238958e97a63b93cfecd6fefa9a
        def suite(self) -> "CheckSuite":
            """Build the provider's Checks without executing them."""
            raise NotImplementedError(
                f"{entity(type(self.obj)).name} declares no checks"
            )

        def run(self, *, into=None, on_result=None) -> "CheckRun":
            """Run this provider's bound suite."""
            return self.suite().run(into=into, on_result=on_result)

    @property
    def checks(self) -> Checks:
        return type(self).Checks(self)


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

    def __init__(self, check: Check, message: str, *,
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
        super().__init__(message,
                         situation=situation,
                         subject=deepcopy(subject if subject is not None else self.details),
                         evidence=deepcopy(evidence if evidence is not None else self.details))

    def as_dict(self, *, detail: bool = False) -> dict[str, object]:
        return {**super().as_dict(detail=detail),
                "check": entity(type(self.check)).records.to_record(),
                "details": deepcopy(self.details), "failure": self.failure}

    # tarav.breadcrumb 98efb14446fdafc5cbb4a98e2d0d162e31638150e69ea0198d0c4c6c3e0f7cd9
    def obj_context(self, builder) -> None:
        super().obj_context(builder)
        builder.add("check", opener=lambda: self.check)
        builder.add("details", opener=lambda: POIDetails.records.from_record(
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
            opener=lambda: POIDetails.records.from_record({
                "type": entity(POIDetails).name,
                "value": self._situation.to_json_value(),
            }),
        )

    def finding(
        self,
        poi_type: type[CheckPOI],
        *,
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


class CheckRun(TaravObject, POIProvider):
    """Results of one suite execution, in execution order."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("b4ad5cfd-c3bc-41d0-acf9-de7fe1de8118"),
                          name="Tarav.Checks.Run", workflow=CHECKS_WORKFLOW_SHIP)

    def __init__(self) -> None:
        super().__init__()
        self.results: list[CheckResult] = []

    def add(self, result: CheckResult) -> CheckResult:
        if not isinstance(result, CheckResult):
            raise TypeError("CheckRun accepts CheckResults")
        self.results.append(result)
        return result

    def results_of(self, check_type: type[Check] | str) -> tuple[CheckResult, ...]:
        if isinstance(check_type, str):
            return tuple(result for result in self.results
                         if entity(type(result.check)).name == check_type)
        if not isinstance(check_type, type) or not issubclass(check_type, Check):
            raise TypeError("Expected a Check Type or Type name")
        return tuple(result for result in self.results if isinstance(result.check, check_type))

    def pois(self) -> tuple[POI, ...]:
        return tuple(poi for result in self.results for poi in result.pois())

    def summary(self) -> dict[str, object]:
        statuses: Counter[str] = Counter()
        by_type: Counter[str] = Counter()
        by_check: dict[str, dict[str, object]] = {}
        for result in self.results:
            check_name = entity(type(result.check)).name
            statuses[result.status] += 1
            check_row = by_check.setdefault(check_name, {"runs": 0, "by_status": {}, "pois": 0})
            check_row["runs"] += 1
            check_row["pois"] += len(result.pois())
            check_row["by_status"][result.status] = check_row["by_status"].get(result.status, 0) + 1
            for poi in result.pois():
                by_type[entity(type(poi)).name] += 1
        return {
            "checks": len(self.results),
            "by_status": dict(statuses),
            "incomplete": len(self.results) - statuses["completed"],
            "pois": sum(by_type.values()),
            "by_check": by_check,
            "by_type": dict(by_type),
        }

    def _standing(self, poi: POI, store, snapshot) -> str:
        if store is not None and store.accepts(poi):
            if store.standing(poi, snapshot=snapshot)["status"] == "blessed":
                return "blessed"
        return "open"

    def clean(self, *, store=None) -> bool:
        if any(result.status != "completed" for result in self.results):
            return False
        snapshot = store.snapshot() if store is not None else None
        return all(self._standing(poi, store, snapshot) == "blessed" for poi in self.pois())

    def report(
        self, *, by: str = "type", sort: str = "run", offset: int = 0, limit: int = 20,
        type: str | None = None, check: str | None = None,
        store=None, detail: bool = False,
    ) -> dict[str, object]:
        if by not in ("type", "check", "identity"):
            raise ValueError("Unknown CheckRun grouping")
        if sort not in ("run", "count"):
            raise ValueError("Unknown CheckRun sort order")
        if offset < 0 or limit < 1:
            raise ValueError("Expected nonnegative offset and positive limit")
        snapshot = store.snapshot() if store is not None else None
        groups: dict[str, dict[str, object]] = {}
        emission_index = 0
        for result_index, result in enumerate(self.results):
            check_name = entity(result.check.__class__).name
            for poi in result.pois():
                type_name = entity(poi.__class__).name
                if (type is not None and type != type_name
                        or check is not None and check != check_name):
                    continue
                emission_index += 1
                key = {
                    "type": type_name,
                    "check": check_name,
                    "identity": getattr(poi, "identity", f"emission:{emission_index}"),
                }[by]
                row = groups.setdefault(key, {
                    "key": key, "by": by, "pois": 0, "checks": 0,
                    "open": 0, "blessed": 0, "example": getattr(poi, "message", ""),
                    "types": [], "_results": set(),
                })
                row["pois"] += 1
                row[self._standing(poi, store, snapshot)] += 1
                if result_index not in row["_results"]:
                    row["_results"].add(result_index)
                    row["checks"] += 1
                if type_name not in row["types"]:
                    row["types"].append(type_name)
                if detail and "example_poi" not in row:
                    row["example_poi"] = (poi.as_dict(detail=True)
                                          if isinstance(poi, IdentifiedPOI) else poi.as_dict())
        rows = list(groups.values())
        if sort == "count":
            rows.sort(key=lambda row: -row["pois"])
        for row in rows:
            del row["_results"]
        page = rows[offset:offset + limit]
        return {
            "summary": self.summary(),
            "context_example": next(
                (poi.identity for poi in self.pois() if isinstance(poi, IdentifiedPOI)), None),
            "by": by,
            "sort": sort,
            "matching": len(rows),
            "offset": offset,
            "shown": len(page),
            "next_offset": offset + limit if offset + limit < len(rows) else None,
            "items": page,
        }


class CheckSuite(TaravObject):
    """A source of checks or ready results; run() is its only full traversal."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("dc589b3c-9a16-4c3d-8338-50ab6304b2f3"),
                          name="Tarav.Checks.Suite", workflow=CHECKS_WORKFLOW_SHIP)

    def __init__(self, source=(), *, name: str | None = None) -> None:
        super().__init__()
        self.source = source
        self.name = name

    @classmethod
    def of(cls, value) -> "CheckSuite":
        if isinstance(value, CheckSuite):
            return value
        if not isinstance(value, Iterable):
            raise TypeError("CheckSuite source must be a suite or iterable")
        return cls(value)

    def run(
        self, *, into: CheckRun | None = None,
        on_result: Callable[[CheckResult], object] | None = None,
    ) -> CheckRun:
        run = into if into is not None else CheckRun()
        if not isinstance(run, CheckRun):
            raise TypeError("into must be a CheckRun")
        if on_result is not None and not callable(on_result):
            raise TypeError("on_result must be callable")

        def consume(suite: CheckSuite) -> None:
            items = suite.source(run) if callable(suite.source) else suite.source
            for item in items:
                if isinstance(item, CheckSuite):
                    consume(item)
                    continue
                if isinstance(item, CheckResult):
                    result = item
                elif isinstance(item, Check):
                    try:
                        result = item.run()
                    except Exception as exc:
                        result = CheckResult(item, status="failed", reason=f"{type(exc).__name__}: {exc}")
                else:
                    raise TypeError("CheckSuite items must be Checks, suites or CheckResults")
                run.add(result)
                if on_result is not None:
                    on_result(result)

        consume(self)
        return run


def render_check_run(report: Mapping[str, object]) -> str:
    """Render a bounded, grouped CheckRun report without dumping every result."""
    summary = report["summary"]
    lines = [f"{summary['checks']} checks, {summary['incomplete']} incomplete, "
             f"{summary['pois']} POIs"]
    if summary["pois"]:
        # One instruction for the whole report, ahead of the POIs it concerns.
        from tarav.l1.poi.reporting import context_instruction

        lines += ["", *context_instruction(report.get("context_example")), ""]
    for row in report["items"]:
        lines.append(f"  {row['key']}: {row['pois']} POIs from {row['checks']} checks "
                     f"({row['open']} open, {row['blessed']} blessed)"
                     + (f" — {row['example']}" if row["example"] else ""))
    lines.append("Checks by type: " + ", ".join(
        f"{name} {data['runs']} ({data['by_status']})"
        for name, data in summary["by_check"].items()) if summary["by_check"] else
        "Checks by type: none")
    lines.append("POIs by type: " + ", ".join(
        f"{name} {count}" for name, count in summary["by_type"].items())
        if summary["by_type"] else "POIs by type: none")
    if report["next_offset"] is not None:
        lines.append(f"Next offset: {report['next_offset']}")
    return "\n".join(lines)


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
    "CheckRun",
    "CheckSuite",
    "Situation",
    "SituationCheck",
    "check_report",
    "run_checks",
    "render_check_run",
]
