# $kw: --from POI.Linter --note [DC] one shared runtime owns the check-selection-execution-report algebra while domains retain their Floor.Model, checks, and POI.Class blocks
"""Workflow-neutral runtime for deterministic POI linters."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from time import perf_counter
from typing import Any, ClassVar, Generic, TypeVar

from tarav._core.errors import CliError

from .model import reference_sugar, tarav_poi_class_reference


JsonObject = dict[str, object]
ContextT = TypeVar("ContextT")


class Status(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"


class Evaluator(StrEnum):
    CODE = "code"
    AGENT = "agent"
    USER = "user"


class Tier(StrEnum):
    STRUCTURAL = "structural"
    REPORTABLE = "reportable"


@dataclass(frozen=True, slots=True)
class Finding:
    """One addressable computation result, without semantic interpretation."""

    poi_class: str
    subject: JsonObject
    operands: JsonObject = field(default_factory=dict)
    status: Status = Status.FAILED
    evaluator: Evaluator = Evaluator.CODE
    surface: JsonObject | None = None
    tier: Tier = Tier.REPORTABLE
    source: str | None = None

    @property
    def identity(self) -> str:
        payload = _canonical_json(
            [self.poi_class, self.subject, self.surface or {}]
        )
        return f"poi-{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]}"

    @property
    def blocked(self) -> bool:
        return self.status is Status.BLOCKED


class Check(Generic[ContextT]):
    """One instantiated evaluation over a domain-owned linter context."""

    name: ClassVar[str]
    tier: ClassVar[Tier] = Tier.REPORTABLE
    default_on: ClassVar[bool] = True
    resolutions: ClassVar[tuple[str, ...]] = ()
    requires: ClassVar[tuple[str, ...]] = ()
    dev: ClassVar[bool] = False
    replaces: ClassVar[str | None] = None

    def __init__(self, context: ContextT) -> None:
        self.context = context

    def run(self) -> list[Finding]:
        raise NotImplementedError

    @classmethod
    def record_scoped(cls) -> bool:
        return _reaches_selected_records(cls.run)

    @classmethod
    def poi_classes(cls) -> frozenset[str]:
        return _referenced_poi_classes(cls.run)

    @classmethod
    def source(cls) -> str:
        code = cls.run.__code__
        return f"{Path(code.co_filename).name}:{code.co_firstlineno}"

    @classmethod
    def why(cls) -> str:
        return (cls.run.__doc__ or "").strip()


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    status: Status
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class LintReport:
    findings: tuple[Finding, ...]
    blocked: tuple[Finding, ...]
    blessed: tuple[Finding, ...]
    results: tuple[CheckResult, ...]
    execution: JsonObject = field(default_factory=dict)
    elapsed_ms: float = 0.0
    dev: tuple[str, ...] = ()
    short_circuited: bool = False

    @property
    def clean(self) -> bool:
        return not self.findings

    @property
    def verified(self) -> bool:
        return (
            not self.findings
            and not self.blocked
            and not self.blocked_checks
            and not self.short_circuited
        )

    @property
    def blocked_checks(self) -> tuple[CheckResult, ...]:
        return tuple(result for result in self.results if result.status is Status.BLOCKED)


def select_checks(
    registry: Iterable[type[Check[Any]]],
    check: Iterable[str] | None = None,
    skip: Iterable[str] | None = None,
    *,
    dev: bool = False,
    targeted: bool = False,
) -> list[type[Check[Any]]]:
    """Resolve one registry selection without weakening structural or dev lanes."""

    entries = tuple(registry)
    included = tuple(check or ())
    excluded = tuple(skip or ())
    names = {entry.name for entry in entries}
    if len(names) != len(entries):
        duplicates = sorted(
            name for name in names if sum(entry.name == name for entry in entries) > 1
        )
        raise ValueError("duplicate linter check name(s): " + ", ".join(duplicates))
    unknown = (set(included) | set(excluded)) - names
    if unknown:
        raise CliError("unknown linter check(s): " + ", ".join(sorted(unknown)))

    replacements = _active_replacements(entries, dev=dev)
    displaced = frozenset(replacements)
    selected_names: set[str] = set()
    for entry in entries:
        if entry.dev and not dev:
            continue
        if entry.name in displaced:
            continue
        if targeted and not entry.record_scoped() and entry.tier is not Tier.STRUCTURAL:
            continue
        if entry.tier is Tier.STRUCTURAL:
            selected_names.add(entry.name)
            continue
        enabled = entry.name in included if included else entry.default_on
        if entry.name in excluded:
            enabled = False
        if enabled:
            selected_names.add(entry.name)

    by_name = {entry.name: entry for entry in entries}
    positions = {entry.name: index for index, entry in enumerate(entries)}
    for entry in entries:
        unknown_requires = set(entry.requires) - names
        if unknown_requires:
            raise ValueError(
                f"check {entry.name!r} requires unknown check(s): "
                + ", ".join(sorted(unknown_requires))
            )
        for dependency in _effective_dependencies(entry, replacements):
            if dependency == entry.name:
                raise ValueError(f"check {entry.name!r} depends on itself")
            if positions[dependency] >= positions[entry.name]:
                raise ValueError(
                    f"check {entry.name!r} requires {dependency!r} before it"
                )

    pending = list(selected_names)
    while pending:
        name = pending.pop()
        entry = by_name[name]
        for declared, dependency in zip(
            entry.requires,
            _effective_dependencies(entry, replacements),
            strict=True,
        ):
            dependency_type = by_name[dependency]
            if (
                declared in excluded or dependency in excluded
            ) and dependency_type.tier is not Tier.STRUCTURAL:
                raise CliError(
                    f"cannot skip check {dependency!r}; selected check {name!r} requires it"
                )
            if dependency_type.dev and not dev:
                raise CliError(
                    f"check {name!r} requires dev check {dependency!r} outside the dev lane"
                )
            if dependency not in selected_names:
                selected_names.add(dependency)
                pending.append(dependency)

    return [entry for entry in entries if entry.name in selected_names]


def run_checks(
    context: object,
    registry: Iterable[type[Check[Any]]],
    *,
    check: Iterable[str] | None = None,
    skip: Iterable[str] | None = None,
    dev: bool = False,
    targeted: bool = False,
    silenced: Iterable[str] = (),
    blessable: Callable[[Finding], bool] | None = None,
    execution: Callable[[Any], JsonObject] | None = None,
) -> LintReport:
    """Execute selected checks in registry order and return one three-valued run."""

    started_at = perf_counter()
    entries = tuple(registry)
    selected = select_checks(
        entries,
        check,
        skip,
        dev=dev,
        targeted=targeted,
    )
    replacements = _active_replacements(entries, dev=dev)
    silenced_ids = frozenset(silenced)
    may_bless = blessable or (lambda _finding: True)
    findings: list[Finding] = []
    blocked: list[Finding] = []
    blessed: list[Finding] = []
    results: list[CheckResult] = []
    short_circuited = False
    results_by_name: dict[str, CheckResult] = {}

    for check_type in selected:
        blocked_by = tuple(
            dependency
            for dependency in _effective_dependencies(check_type, replacements)
            if results_by_name[dependency].status is Status.BLOCKED
        )
        if blocked_by:
            result = CheckResult(
                check_type.name,
                Status.BLOCKED,
                "blocked by check(s): " + ", ".join(blocked_by),
            )
            results.append(result)
            results_by_name[result.name] = result
            continue

        check_instance = check_type(context)
        produced = [
            replace(item, source=check_type.source(), tier=check_type.tier)
            for item in check_instance.run()
        ]
        failed_here: list[Finding] = []
        blocked_here: list[Finding] = []
        for item in produced:
            if item.blocked:
                blocked.append(item)
                blocked_here.append(item)
                continue
            produced_ids = getattr(context, "produced", None)
            if isinstance(produced_ids, set):
                produced_ids.add(item.identity)
            if item.identity in silenced_ids and may_bless(item):
                blessed.append(item)
            else:
                findings.append(item)
                failed_here.append(item)

        status = (
            Status.FAILED
            if failed_here
            else Status.BLOCKED
            if blocked_here
            else Status.PASSED
        )
        result = CheckResult(check_type.name, status)
        results.append(result)
        results_by_name[result.name] = result
        if check_type.tier is Tier.STRUCTURAL and produced:
            short_circuited = True
            break

    execution_payload = execution(context) if execution is not None else {}
    return LintReport(
        findings=tuple(findings),
        blocked=tuple(blocked),
        blessed=tuple(blessed),
        results=tuple(results),
        execution=_normalize_json_object(execution_payload),
        elapsed_ms=round((perf_counter() - started_at) * 1000, 3),
        dev=tuple(entry.name for entry in selected if entry.dev),
        short_circuited=short_circuited,
    )


def _active_replacements(
    entries: tuple[type[Check[Any]], ...],
    *,
    dev: bool,
) -> dict[str, str]:
    if not dev:
        return {}

    names = {entry.name for entry in entries}
    replacements: dict[str, str] = {}
    for entry in entries:
        target = entry.replaces if entry.dev else None
        if target is None:
            continue
        if target not in names:
            raise ValueError(
                f"dev check {entry.name!r} replaces unknown check {target!r}"
            )
        previous = replacements.get(target)
        if previous is not None:
            raise ValueError(
                f"check {target!r} has several active replacements: "
                f"{previous!r}, {entry.name!r}"
            )
        replacements[target] = entry.name

    chained = sorted(name for name in replacements.values() if name in replacements)
    if chained:
        raise ValueError(
            "dev replacement chains are not supported: " + ", ".join(chained)
        )
    return replacements


def _effective_dependencies(
    entry: type[Check[Any]],
    replacements: Mapping[str, str],
) -> tuple[str, ...]:
    return tuple(replacements.get(name, name) for name in entry.requires)


class LinterReportSelectionError(ValueError):
    """An explicit instance projection selected no occurrence."""


def build_linter_document(
    report: LintReport,
    *,
    run_class: str,
    limit: int,
    poi_classes: Iterable[str] = (),
    poi_ids: Iterable[str] = (),
    statuses: Iterable[str] = (),
) -> JsonObject:
    """Build the one JSON object consumed by every POI linter renderer."""

    if limit < 0:
        raise ValueError("linter instance limit must be non-negative")
    selected_classes = tuple(sorted(set(poi_classes)))
    selected_ids = tuple(sorted(set(poi_ids)))
    selected_statuses = tuple(sorted(set(statuses)))
    known_statuses = {"failed", "blocked", "blessed"}
    unknown = set(selected_statuses) - known_statuses
    if unknown:
        raise ValueError("unknown POI status: " + ", ".join(sorted(unknown)))

    instances = tuple(sorted(_reported_instances(report), key=_instance_sort_key))
    matching = tuple(
        item
        for item in instances
        if (not selected_classes or item["class_address"] in selected_classes)
        and (not selected_ids or item["instance_id"] in selected_ids)
        and (not selected_statuses or item["status"] in selected_statuses)
    )
    if (selected_classes or selected_ids or selected_statuses) and not matching:
        raise LinterReportSelectionError(
            "explicit POI selectors matched no occurrence in this linter run"
        )
    shown = matching[:limit]
    check_counts = {
        "run": len(report.results),
        "passed": sum(result.status is Status.PASSED for result in report.results),
        "failed": sum(result.status is Status.FAILED for result in report.results),
        "blocked": sum(result.status is Status.BLOCKED for result in report.results),
    }
    return {
        "class": run_class,
        "schema_version": 1,
        "status": _run_status(report),
        "clean": report.clean,
        "verified": report.verified,
        "short_circuited": report.short_circuited,
        "execution": {**report.execution, "elapsed_ms": report.elapsed_ms},
        "selection": {
            "poi_classes": list(selected_classes),
            "poi_ids": list(selected_ids),
            "statuses": list(selected_statuses),
        },
        "checks": {
            "summary": check_counts,
            "items": [
                {
                    "name": result.name,
                    "status": str(result.status),
                    "reason": result.reason,
                }
                for result in report.results
            ],
        },
        "poi_classes": _class_summaries(instances),
        "poi_instances": {
            "total": len(instances),
            "matching": len(matching),
            "shown": len(shown),
            "limit": limit,
            "truncated": len(shown) < len(matching),
            "items": list(shown),
        },
        "dev": list(report.dev),
    }


def render_linter_text(document: Mapping[str, object]) -> str:
    execution = _mapping(document["execution"])
    checks = _mapping(document["checks"])
    summary = _mapping(checks["summary"])
    lane = " DEV" if document["dev"] else ""
    lines = [
        f"{document['class']}{lane} — {str(document['status']).upper()} — "
        f"{execution['elapsed_ms']} ms",
        "",
        "Execution",
    ]
    for key, value in execution.items():
        if key != "elapsed_ms":
            lines.append(f"  {key} {value}")
    lines.append(
        f"  checks {summary['run']} run: {summary['passed']} passed, "
        f"{summary['failed']} failed, {summary['blocked']} blocked"
    )
    for raw in _list(checks["items"]):
        item = _mapping(raw)
        if item["status"] == "passed":
            continue
        reason = f" — {item['reason']}" if item["reason"] else ""
        lines.append(f"    {item['status']}  {item['name']}{reason}")

    classes = [_mapping(item) for item in _list(document["poi_classes"])]
    lines.extend(["", f"POI classes ({len(classes)})"])
    if not classes:
        lines.append("  none")
    for item in classes:
        counts = _mapping(item["counts"])
        lines.append(
            f"  {item['class_address']}  {counts['total']} total "
            f"({counts['failed']} failed, {counts['blocked']} blocked, "
            f"{counts['blessed']} blessed)"
        )
        lines.append(f"    {item['class_reference_sugar']}")

    window = _mapping(document["poi_instances"])
    lines.extend(
        [
            "",
            f"POI instances — showing {window['shown']} of {window['matching']} "
            f"matching POI instances ({window['total']} total)",
        ]
    )
    for raw in _list(window["items"]):
        item = _mapping(raw)
        lines.append(
            f"  {item['status']:<7} {item['instance_id']}  "
            f"{item['class_address']}  {_canonical_json(item['subject'])}"
        )
    return "\n".join(lines)


def _reaches_selected_records(
    fn: Callable[..., object],
    seen: frozenset[str] = frozenset(),
) -> bool:
    code = getattr(fn, "__code__", None)
    if code is None:
        return False
    if "selected_records" in code.co_names or "is_selected" in code.co_names:
        return True
    namespace = getattr(fn, "__globals__", {})
    for name in code.co_names:
        if name in seen:
            continue
        candidate = namespace.get(name)
        if callable(candidate) and getattr(candidate, "__module__", None) == fn.__module__:
            if _reaches_selected_records(candidate, seen | {name}):
                return True
    return False


def _referenced_poi_classes(
    fn: Callable[..., object],
    seen: frozenset[str] = frozenset(),
) -> frozenset[str]:
    code = getattr(fn, "__code__", None)
    if code is None:
        return frozenset()
    found = {
        value
        for value in code.co_consts
        if isinstance(value, str) and ".Linter/" in value
    }
    namespace = getattr(fn, "__globals__", {})
    for name in code.co_names:
        if name in seen:
            continue
        candidate = namespace.get(name)
        if isinstance(candidate, str) and ".Linter/" in candidate:
            found.add(candidate)
        if callable(candidate) and getattr(candidate, "__module__", None) == fn.__module__:
            found.update(_referenced_poi_classes(candidate, seen | {name}))
    return frozenset(found)


def _reported_instances(report: LintReport) -> Iterable[JsonObject]:
    grouped: dict[str, tuple[str, list[Finding]]] = {}
    for status, findings in (
        ("failed", report.findings),
        ("blocked", report.blocked),
        ("blessed", report.blessed),
    ):
        for finding in findings:
            current = grouped.get(finding.identity)
            if current is None:
                grouped[finding.identity] = (status, [finding])
            elif current[0] != status:
                raise ValueError(
                    f"POI instance {finding.identity} appears in several status lanes"
                )
            else:
                current[1].append(finding)

    for identity, (status, findings) in grouped.items():
        first = findings[0]
        reference = tarav_poi_class_reference(first.poi_class)
        evidence: JsonObject = {"operands": first.operands}
        if len(findings) > 1:
            observations: list[JsonObject] = []
            for finding in findings:
                observation: JsonObject = {"operands": finding.operands}
                if finding.source != first.source and finding.source is not None:
                    observation["source"] = finding.source
                if finding.surface != first.surface and finding.surface is not None:
                    observation["surface"] = finding.surface
                if observation not in observations:
                    observations.append(observation)
            evidence["observation_count"] = len(findings)
            evidence["observations"] = observations
        yield {
            "class": "POI.Instance",
            "instance_id": identity,
            "status": status,
            "class_address": first.poi_class,
            "class_reference": reference.as_dict(),
            "class_reference_sugar": reference_sugar(reference),
            "subject": first.subject,
            "operands": first.operands,
            "surface": first.surface,
            "source": first.source,
            "tier": str(first.tier),
            "evaluator": str(first.evaluator),
            "evidence": evidence,
        }


def _instance_sort_key(item: JsonObject) -> tuple[int, str, str, str]:
    order = {"failed": 0, "blocked": 1, "blessed": 2}
    return (
        order[str(item["status"])],
        str(item["class_address"]),
        _canonical_json(item["subject"]),
        str(item["instance_id"]),
    )


def _class_summaries(instances: tuple[JsonObject, ...]) -> list[JsonObject]:
    grouped: dict[str, list[JsonObject]] = {}
    for item in instances:
        grouped.setdefault(str(item["class_address"]), []).append(item)
    rows: list[JsonObject] = []
    for address, members in sorted(grouped.items()):
        first = members[0]
        rows.append(
            {
                "class_address": address,
                "class_reference": first["class_reference"],
                "class_reference_sugar": first["class_reference_sugar"],
                "sources": sorted(
                    {str(item["source"]) for item in members if item["source"]}
                ),
                "counts": {
                    "total": len(members),
                    "failed": sum(item["status"] == "failed" for item in members),
                    "blocked": sum(item["status"] == "blocked" for item in members),
                    "blessed": sum(item["status"] == "blessed" for item in members),
                },
            }
        )
    return rows


def _run_status(report: LintReport) -> str:
    if report.findings:
        return "failed"
    if report.blocked or report.blocked_checks or report.short_circuited:
        return "blocked"
    return "verified"


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _normalize_json_object(value: JsonObject) -> JsonObject:
    try:
        normalized = json.loads(_canonical_json(value))
    except (TypeError, ValueError) as exc:
        raise ValueError("POI linter data must be JSON-serializable") from exc
    if not isinstance(normalized, dict):
        raise ValueError("POI linter data must be a JSON object")
    return normalized


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError("invalid POI linter document mapping")
    return value


def _list(value: object) -> list[object]:
    if not isinstance(value, list):
        raise TypeError("invalid POI linter document list")
    return value


__all__ = [
    "Check",
    "CheckResult",
    "Evaluator",
    "Finding",
    "LintReport",
    "LinterReportSelectionError",
    "Status",
    "Tier",
    "build_linter_document",
    "render_linter_text",
    "run_checks",
    "select_checks",
]
