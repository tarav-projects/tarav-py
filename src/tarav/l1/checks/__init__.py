"""Independently runnable, bound checks and their execution snapshots."""

from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from copy import deepcopy
from pathlib import Path
from typing import ClassVar, Literal

from tarav.l0._core.git_repository import repository_states
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
from tarav.l1.context.groups import Link, Member
from tarav.l1.poi import SituationPOI, POI, POIDetails, POIProvider, fingerprint, plain, poi_member
from tarav.l1.poi.actionable import ActionablePOI

CHECKS_WORKFLOW_SHIP = WorkflowShip("44fc55a7-771e-4b63-8b38-6641a5069fc7")


class ChecksWorkflow(TaravWorkflow):
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

        def run(self, *, select=None, on_result=None) -> "CheckSuite":
            """Run this provider's suite, whole or filtered, and return it with its results."""
            return self.suite().run(select=select, on_result=on_result)

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

    @property
    def identity(self) -> str | None:
        """Which check this is across runs; None when it cannot say."""
        return None

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
class CheckPOI(SituationPOI, ActionablePOI):
    """A POI explained by the bound Check object that produced it; it spins an action by default.

    It adds three fields to its situation: the `check` that raised it,
    `details`, free data the check observed that is not part of the
    identity, and `failure`, whether it counts as a finding.
    """

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("20ad2c76-009f-4aae-a564-70b7925664ef"),
                          name="Tarav.Checks.POI", workflow=CHECKS_WORKFLOW_SHIP)

    def __init__(self, check: Check, message: str, *,
                 situation,
                 details: dict | None = None, failure: bool = True) -> None:
        if not isinstance(check, Check):
            raise TypeError("CheckPOI requires a bound Check object")
        self.check = check
        self.raised_by = entity(type(check)).name
        self.details = deepcopy(details or {})
        if not isinstance(failure, bool):
            raise TypeError("CheckPOI failure must be a boolean")
        self.failure = failure
        super().__init__(message, situation=situation)

    class RecordInterface(SituationPOI.RecordInterface):
        check: str
        details: dict
        failure: bool

    def _to_record(self) -> dict[str, object]:
        return {**super()._to_record(), "check": self.raised_by,
                "details": plain(self.details), "failure": self.failure}

    @classmethod
    def _from_record(cls, record_data):
        """A loaded check POI has no bound check: `raised_by` still names its Type."""
        result = super()._from_record(record_data)
        result.check, result.raised_by = None, record_data.check
        result.details, result.failure = deepcopy(record_data.details), record_data.failure
        return result

    class Records(SituationPOI.Records):
        def record_example(self) -> dict[str, object]:
            return {**super().record_example(), "check": "Tarav.Checks.Check", "details": {},
                    "failure": True}

    # tarav.breadcrumb 98efb14446fdafc5cbb4a98e2d0d162e31638150e69ea0198d0c4c6c3e0f7cd9
    def obj_context(self, builder) -> None:
        super().obj_context(builder)
        builder.add("check", opener=lambda: self.check)
        builder.add("details", opener=lambda: POIDetails.records.from_record(
            {"type": entity(POIDetails).name, "value": deepcopy(self.details)}))


# tarav.breadcrumb fc19d1dda27390665cfc51da98143a0209b87e99bdc414ace2fe55987e55af09
def check_links(poi: CheckPOI):
    """The check reads the situation and raises the POI. A loaded POI has no bound
    check, so only the check's Type is known of it."""
    check = Member("check", member_type=poi.raised_by)
    yield Link(Member("situation", value=poi.situation), check)
    yield Link(check, poi_member(poi))


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

    @property
    def identity(self) -> str:
        return fingerprint([str(entity(type(self)).id), self._situation.to_json_value()])

    def obj_context(self, builder) -> None:
        builder.add(
            "situation",
            opener=lambda: POIDetails.records.from_record({
                "type": entity(POIDetails).name,
                "value": self._situation.to_json_value(),
            }),
        )

    def poi(
        self,
        poi_type: type[CheckPOI],
        *,
        message: str,
        details: dict | None = None,
        failure: bool = True,
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
    """One execution snapshot; inspecting POIs never reruns its Check.

    `git` is the state of the repositories the nearest suite above it
    declares, taken when that suite started: by repository root, its HEAD and
    whether it was clean. None when no suite above declares any.
    """

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
        self.git: dict[str, dict] | None = None
        self._pois = tuple(pois)
        if any(not isinstance(poi, POI) for poi in self._pois):
            raise TypeError("CheckResult POIs must be POIs")
        if any(isinstance(poi, CheckPOI) and poi.check is not check for poi in self._pois):
            raise ValueError("CheckResult contains a POI from another Check")

    def pois(self) -> tuple[POI, ...]:
        return self._pois


# tarav.breadcrumb bd06b988e162e226589d99af66360d1d8cabff4416e3467793331678eff4cc98
# tarav.breadcrumb a99d78902f0b314cddb487a06fe912eb513c6d03a7b5da3a3a8b21534ac68802
# tarav.breadcrumb 187a0de2c6388a20c78433829fe87d2a0dc9c8df4c93515e846b813724854891
# tarav.breadcrumb e8a9613020d9d01c514464079be745e2211a69b633b56f6ea5005e23991749ff
class CheckSuite(TaravObject, POIProvider):
    """A detector: the code that runs checks, and the results of its one run.

    A suite does not contain checks. Which checks exist is only known while
    it runs, because many are made from situations found on the way, and
    situations cannot be listed beforehand. `produce()` is that code: it
    yields checks, nested suites or ready results.

    One instance holds one run. It can run whole or filtered, and it says
    whether what it ran is conclusive; that is what lets someone conclude
    that a situation it did not report is gone. A subclass is a suite with an
    identity of its own, and a `key` binds one instance to a subject.

    `repositories` are folders in the Git repositories its checks read: a
    declaration its maintainers keep. When it runs it records their state
    first, as `git`; a suite that declares none keeps the one above it.
    """

    routine: ClassVar[bool] = True  # part of the run that is repeated often

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("dc589b3c-9a16-4c3d-8338-50ab6304b2f3"),
                          name="Tarav.Checks.Suite", workflow=CHECKS_WORKFLOW_SHIP)

    def __init__(self, source=(), *, name: str | None = None, key: str | None = None,
                 repositories: Iterable[str | Path] = ()) -> None:
        super().__init__()
        self.source = source
        self.name = name
        self.key = key
        self.repositories = tuple(Path(folder) for folder in repositories)
        self.reset()

    @classmethod
    def of(cls, value) -> "CheckSuite":
        if isinstance(value, CheckSuite):
            return value
        if not isinstance(value, Iterable):
            raise TypeError("CheckSuite source must be a suite or iterable")
        return cls(value)

    @classmethod
    def gathered(cls, suites: Iterable["CheckSuite"], *, name: str | None = None) -> "CheckSuite":
        """One suite over suites that already ran, to read them together."""
        whole = cls(name=name)
        whole.items = list(suites)
        whole.ran = True
        return whole

    # tarav.breadcrumb 292068630e668cebc44b4c49570344d5f1a1263cf5b1b7c9fdb057652d47d92d
    @property
    def identity(self) -> dict | None:
        """What this suite is: its Type and its key. A plain grouping has none.

        A grouping without identity counts as part of the suite above it.
        """
        if type(self) is CheckSuite and self.key is None:
            return None
        return {"type": entity(type(self)).name, "key": self.key}

    def reset(self) -> None:
        """Forget the run this suite holds."""
        self.items: list[CheckResult | CheckSuite] = []
        self.ran = False
        self.git: dict[str, dict] | None = None
        self._refused = 0

    def produce(self) -> Iterable:
        """Yield what to run: checks, nested suites or ready results.

        A function given as the source receives this suite, to read what ran
        before it.
        """
        return self.source(self) if callable(self.source) else self.source

    # tarav.breadcrumb 0957344ced509d1d0237945f09a405e985bdc7222b4f01f51043cc531db4262f
    def run(
        self, *, select: Callable[[object], bool] | None = None,
        on_result: Callable[[CheckResult], object] | None = None,
        git: dict[str, dict] | None = None,
    ) -> "CheckSuite":
        """Run what `produce()` yields and keep the results on this suite.

        `select` is asked for each check and nested suite before it runs. One
        it refuses does not run, and this suite then did not run completely.
        `git` is the state the suite above took, for a suite that declares no
        repositories of its own.
        """
        if select is not None and not callable(select):
            raise TypeError("select must be callable")
        if on_result is not None and not callable(on_result):
            raise TypeError("on_result must be callable")
        self.reset()
        self.ran = True
        # tarav.breadcrumb 646320d9df89a53c1ab51fa1adfd01176f4d14b449d1634db183fdcc952f03d1
        # tarav.breadcrumb 62668358e7f205b4b5bf318d0eae1e8b8aac2f13e2ab52122d248739cf04ec1d
        self.git = repository_states(self.repositories) if self.repositories else git
        for item in self.produce():
            if isinstance(item, CheckSuite):
                if select is not None and not select(item):
                    item.reset()  # kept, so that it is known as not run
                else:
                    item.run(select=select, on_result=on_result, git=self.git)
                self.items.append(item)
                continue
            if isinstance(item, CheckResult):
                result = item
            elif isinstance(item, Check):
                if select is not None and not select(item):
                    self._refused += 1
                    continue
                try:
                    result = item.run()
                except Exception as exc:
                    result = CheckResult(item, status="failed", reason=f"{type(exc).__name__}: {exc}")
            else:
                raise TypeError("A suite yields Checks, suites or CheckResults")
            if result.git is None:
                result.git = self.git
            self.items.append(result)
            if on_result is not None:
                on_result(result)
        return self

    def add(self, result: "CheckResult") -> "CheckResult":
        """Keep one ready result, for a suite put together by hand."""
        if not isinstance(result, CheckResult):
            raise TypeError("A suite keeps CheckResults")
        self.items.append(result)
        self.ran = True
        return result

    # tarav.breadcrumb 5815e018a2d0dccc212f073206d962cc8ea7f9f109dc60f9882b330ea67e76c1
    @property
    def complete(self) -> bool:
        """It ran, nothing was refused, and every check and nested suite completed."""
        return (self.ran and not self._refused
                and all(item.complete if isinstance(item, CheckSuite)
                        else item.status == "completed" for item in self.items))

    def own_results(self) -> Iterable["CheckResult"]:
        """The results of this suite itself: its own and those of plain groupings in it."""
        for item in self.items:
            if not isinstance(item, CheckSuite):
                yield item
            elif item.identity is None:
                yield from item.own_results()

    # tarav.breadcrumb b4ea07ac1bcf4e22778f334dd461c4fca0e352d44d3c1864f73b373ec328f46c
    @property
    def exhausted(self) -> bool:
        """This suite's own code ran to its end and nothing in it was refused.

        A nested suite with an identity answers for itself, so one that was
        left out does not count here.
        """
        return (self.ran and not self._refused
                and all(item.exhausted for item in self.items
                        if isinstance(item, CheckSuite) and item.identity is None))

    def conclusive_for(self, check_type: str | None = None) -> bool:
        """Can this suite say that what it did not report is not there?

        It can when it is exhausted and its own checks completed: those of
        one Type when `check_type` names it, otherwise all of them. Then a
        situation they did not report is gone, and so is a nested suite this
        one did not yield.
        """
        return self.exhausted and all(
            result.status == "completed" for result in self.own_results()
            if check_type is None or entity(type(result.check)).name == check_type)

    @property
    def conclusive(self) -> bool:
        return self.conclusive_for()

    @property
    def results(self) -> list["CheckResult"]:
        """Every result of this suite and of the suites it ran, in execution order."""
        return [result for _, result in self.walk()]

    def suites(self) -> list["CheckSuite"]:
        """The nested suites, at any depth, that were run or refused."""
        found: list[CheckSuite] = []
        for item in self.items:
            if isinstance(item, CheckSuite):
                found.append(item)
                found.extend(item.suites())
        return found

    def walk(self, above: tuple[dict, ...] = ()) -> Iterable[tuple[tuple[dict, ...], "CheckResult"]]:
        """Each result with the identified suites above it, outermost first."""
        chain = above if self.identity is None else (*above, self.identity)
        for item in self.items:
            if isinstance(item, CheckSuite):
                yield from item.walk(chain)
            else:
                yield chain, item

    def results_of(self, check_type: type[Check] | str) -> tuple["CheckResult", ...]:
        if isinstance(check_type, str):
            return tuple(result for result in self.results
                         if entity(type(result.check)).name == check_type)
        if not isinstance(check_type, type) or not issubclass(check_type, Check):
            raise TypeError("Expected a Check Type or Type name")
        return tuple(result for result in self.results if isinstance(result.check, check_type))

    def pois(self) -> tuple[POI, ...]:
        return tuple(poi for result in self.results for poi in result.pois())

    def findings(self) -> tuple[POI, ...]:
        """The POIs that stand as findings: every POI but those marked as not a failure."""
        return tuple(poi for poi in self.pois()
                     if not (isinstance(poi, CheckPOI) and not poi.failure))

    def summary(self) -> dict[str, object]:
        statuses: Counter[str] = Counter()
        by_type: Counter[str] = Counter()
        by_check: dict[str, dict[str, object]] = {}
        results = self.results
        for result in results:
            check_name = entity(type(result.check)).name
            statuses[result.status] += 1
            check_row = by_check.setdefault(check_name, {"runs": 0, "by_status": {}, "pois": 0})
            check_row["runs"] += 1
            check_row["pois"] += len(result.pois())
            check_row["by_status"][result.status] = check_row["by_status"].get(result.status, 0) + 1
            for poi in result.pois():
                by_type[entity(type(poi)).name] += 1
        return {
            "checks": len(results),
            "by_status": dict(statuses),
            "incomplete": len(results) - statuses["completed"],
            "not_run": [{**(suite.identity or {"type": None, "key": None}), "name": suite.name}
                        for suite in self.suites() if not suite.ran],
            "pois": sum(by_type.values()),
            "by_check": by_check,
            "by_type": dict(by_type),
        }

    # tarav.breadcrumb d96e22c81cc727200ea256c3e9af4d895e1d1842e4d7ac7861e3279bee041f3b
    def clean(self) -> bool:
        """Every check completed and none left a finding.

        Whether a finding is settled is not known here; who knows it reads
        `findings()` and decides.
        """
        return (all(result.status == "completed" for result in self.results)
                and not self.findings())

    # tarav.breadcrumb cb1a5772a23d17b22aa60b8bb37e1a3015cff629e44c47640e8886c7fe49d6e0
    def report(
        self, *, by: str = "type", sort: str = "run", offset: int = 0, limit: int = 20,
        type: str | None = None, check: str | None = None,
        detail: bool = False,
    ) -> dict[str, object]:
        """A bounded grouped report of the run's POIs. It says nothing about actions."""
        if by not in ("type", "check", "identity"):
            raise ValueError("Unknown report grouping")
        if sort not in ("run", "count"):
            raise ValueError("Unknown report sort order")
        if offset < 0 or limit < 1:
            raise ValueError("Expected nonnegative offset and positive limit")
        groups: dict[str, dict[str, object]] = {}
        emission_index = 0
        matching_pois = 0
        for result_index, result in enumerate(self.results):
            check_name = entity(result.check.__class__).name
            for poi in result.pois():
                type_name = entity(poi.__class__).name
                if (type is not None and not any(
                        entity(base).name == type
                        for base in poi.__class__.__mro__
                        if issubclass(base, POI) and "class_entity" in base.__dict__)
                        or check is not None and check != check_name):
                    continue
                matching_pois += 1
                emission_index += 1
                key = {
                    "type": type_name,
                    "check": check_name,
                    "identity": getattr(poi, "identity", f"emission:{emission_index}"),
                }[by]
                row = groups.setdefault(key, {
                    "key": key, "by": by, "pois": 0, "checks": 0,
                    "example": poi.summary(),
                    "id": getattr(poi, "identity", None),
                    "types": [], "_results": set(),
                })
                row["pois"] += 1
                if result_index not in row["_results"]:
                    row["_results"].add(result_index)
                    row["checks"] += 1
                if type_name not in row["types"]:
                    row["types"].append(type_name)
                if detail and "example_poi" not in row:
                    row["example_poi"] = poi.records.to_record()
        rows = list(groups.values())
        if sort == "count":
            rows.sort(key=lambda row: -row["pois"])
        for row in rows:
            del row["_results"]
        page = rows[offset:offset + limit]
        return {
            "summary": self.summary(),
            "matching_pois": matching_pois,
            "filters": {key: value for key, value in (("type", type), ("check", check))
                        if value is not None},
            "by": by,
            "sort": sort,
            "matching": len(rows),
            "offset": offset,
            "shown": len(page),
            "next_offset": offset + limit if offset + limit < len(rows) else None,
            "items": page,
        }


# tarav.breadcrumb f1a2ea68b964b6f2337f39c07640ed590bab9deea67d99884bc6b8d99b4e1901
def routine(item: object) -> bool:
    """A filter for the run that is repeated often: leave out suites that are not routine."""
    return not (isinstance(item, CheckSuite) and not item.routine)


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
            "pois": [poi.records.to_record() for poi in result.pois()],
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
    "CheckSuite",
    "Situation",
    "SituationCheck",
    "check_links",
    "check_report",
    "routine",
    "run_checks",
]
