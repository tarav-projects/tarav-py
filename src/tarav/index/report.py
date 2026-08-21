# $kw: --from POI.Renderer --from Index.Linter
# --note [DC] `Index.Linter` produces one canonical JSON-serializable run document before any output mode renders it. ^c20260820-9u
# --note [CT] Check execution, POI class aggregates, and POI instances are separate named sections so their identities and counts cannot be confused. ^c20260820-10u
# --note [CT] The POI class summary is complete for the selected linter execution even when occurrence presentation is bounded. ^c20260820-11u
# --note [DC] `--limit` bounds only the deterministically ordered POI instance window, and every rendering states how many matching and total instances exist. ^c20260820-12u
# --note [CT] Failed, blocked, and blessed occurrences share one POI instance collection and carry explicit status. ^c20260820-13u
# --note [RJ] The default report does not emit the semantic `Concentration` heuristic. ^c20260820-14u
# --note [CT] Text and JSON renderings consume the same run document and obey the same filters and instance limit. ^c20260820-16u
"""Canonical agent-facing report document for an Index linter run."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Literal, TypeAlias

from tarav.poi import POIInstance, POILocation, reference_sugar, tarav_poi_class_reference

from .config import TaravIndexError
from .linter import Finding, LintReport


InstanceStatus: TypeAlias = Literal["failed", "blocked", "blessed"]
_STATUS_ORDER: dict[InstanceStatus, int] = {
    "failed": 0,
    "blocked": 1,
    "blessed": 2,
}


class LinterReportSelectionError(TaravIndexError):
    """Raised when an explicit POI projection selects no occurrence."""


@dataclass(frozen=True, slots=True)
class _ReportedInstance:
    status: InstanceStatus
    findings: tuple[Finding, ...]
    instance: POIInstance

    @property
    def finding(self) -> Finding:
        return self.findings[0]

    @property
    def class_address(self) -> str:
        return str(self.instance.class_reference.address)

    def sort_key(self) -> tuple[int, str, str, str]:
        return (
            _STATUS_ORDER[self.status],
            self.class_address,
            self.finding.subject,
            self.instance.instance_id,
        )

    def as_dict(self) -> dict[str, object]:
        instance = self.instance.as_dict()
        class_reference = instance.pop("class")
        class_reference_sugar = instance.pop("class_sugar")
        return {
            "class": "POI.Instance",
            "status": self.status,
            "class_address": self.class_address,
            "class_reference": class_reference,
            "class_reference_sugar": class_reference_sugar,
            "subject": self.finding.subject,
            "source": self.finding.source,
            "surface": self.finding.surface,
            "tier": str(self.finding.tier),
            **instance,
        }


def build_linter_document(
    report: LintReport,
    *,
    limit: int,
    poi_classes: Iterable[str] = (),
    poi_ids: Iterable[str] = (),
    statuses: Iterable[str] = (),
) -> dict[str, object]:
    """Build the one JSON object consumed by every Index linter renderer."""

    if limit < 0:
        raise ValueError("linter instance limit must be non-negative")

    selected_classes = tuple(sorted(set(poi_classes)))
    selected_ids = tuple(sorted(set(poi_ids)))
    selected_statuses = tuple(sorted(set(statuses)))
    unknown_statuses = set(selected_statuses) - set(_STATUS_ORDER)
    if unknown_statuses:
        raise ValueError(
            "unknown POI status: " + ", ".join(sorted(unknown_statuses))
        )

    instances = tuple(sorted(_reported_instances(report), key=lambda item: item.sort_key()))
    matching = tuple(
        item
        for item in instances
        if (not selected_classes or item.class_address in selected_classes)
        and (not selected_ids or item.instance.instance_id in selected_ids)
        and (not selected_statuses or item.status in selected_statuses)
    )
    if (selected_classes or selected_ids or selected_statuses) and not matching:
        raise LinterReportSelectionError(
            "explicit POI selectors matched no occurrence in this linter run"
        )

    shown = matching[:limit]
    check_counts = {
        "run": len(report.results),
        "passed": sum(result.status == "passed" for result in report.results),
        "failed": sum(result.status == "failed" for result in report.results),
        "blocked": sum(result.status == "blocked" for result in report.results),
    }

    return {
        "class": "Index.Linter.Run",
        "schema_version": 1,
        "status": _run_status(report),
        "execution": {
            "project_id": report.project_id,
            "project_root": report.project_root,
            "elapsed_ms": report.elapsed_ms,
            "records_loaded": report.records_loaded,
            "records_checked": report.records_checked,
            "surface_files_loaded": report.surface_files_loaded,
            "surface_lines_loaded": report.surface_lines_checked,
        },
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
            "items": [item.as_dict() for item in shown],
        },
        "dev": list(report.dev),
    }


def render_linter_text(document: Mapping[str, object]) -> str:
    """Render only facts already selected and aggregated in the run document."""

    status = str(document["status"]).upper()
    execution = _mapping(document["execution"])
    checks = _mapping(document["checks"])
    check_summary = _mapping(checks["summary"])
    lane = " DEV" if document["dev"] else ""
    lines = [
        f"INDEX LINTER{lane} — {status} — {execution['elapsed_ms']} ms",
        "",
        "Execution",
        f"  project {execution['project_id']}  {execution['project_root']}",
        (
            f"  loaded {execution['surface_files_loaded']} surface file(s), "
            f"{execution['surface_lines_loaded']} surface line(s), "
            f"{execution['records_loaded']} record(s)"
        ),
        f"  examined {execution['records_checked']} record(s)",
        (
            f"  checks {check_summary['run']} run: {check_summary['passed']} passed, "
            f"{check_summary['failed']} failed, {check_summary['blocked']} blocked"
        ),
    ]

    nonpassing = [
        _mapping(item)
        for item in _list(checks["items"])
        if _mapping(item)["status"] != "passed"
    ]
    for item in nonpassing:
        reason = f" — {item['reason']}" if item["reason"] else ""
        lines.append(f"    {item['status']}  {item['name']}{reason}")

    classes = [_mapping(row) for row in _list(document["poi_classes"])]
    lines.extend(["", f"POI classes ({len(classes)})"])
    if not classes:
        lines.append("  none")
    for row in classes:
        counts = _mapping(row["counts"])
        sources = ", ".join(str(value) for value in _list(row["sources"]))
        lines.append(
            f"  {row['class_address']}  {counts['total']} total "
            f"({counts['failed']} failed, {counts['blocked']} blocked, "
            f"{counts['blessed']} blessed)"
        )
        lines.append(f"    {row['class_reference_sugar']}  {sources}")

    window = _mapping(document["poi_instances"])
    lines.extend(
        [
            "",
            (
                f"POI instances — showing {window['shown']} of {window['matching']} "
                f"matching POI instances ({window['total']} total)"
            ),
        ]
    )
    for raw_item in _list(window["items"]):
        item = _mapping(raw_item)
        lines.append(
            f"  {item['status']:<7} {item['instance_id']}  "
            f"{item['class_address']}  {item['subject']}"
        )

    return "\n".join(lines)


def _reported_instances(report: LintReport) -> Iterable[_ReportedInstance]:
    grouped: dict[str, tuple[InstanceStatus, list[Finding]]] = {}
    for status, findings in (
        ("failed", report.findings),
        ("blocked", report.blocked),
        ("blessed", report.blessed),
    ):
        for finding in findings:
            typed_status: InstanceStatus = status
            previous = grouped.get(finding.identity)
            if previous is None:
                grouped[finding.identity] = (typed_status, [finding])
            elif previous[0] != typed_status:
                raise ValueError(
                    f"POI instance {finding.identity} appears in several status lanes"
                )
            else:
                previous[1].append(finding)

    for status, mutable_findings in grouped.values():
        findings = tuple(mutable_findings)
        finding = findings[0]
        evidence: dict[str, object] = {"operands": finding.operands}
        if finding.source is not None:
            evidence["source"] = finding.source
        if finding.surface is not None:
            evidence["surface"] = finding.surface
        if len(findings) > 1:
            observations: list[dict[str, object]] = []
            for observed in findings:
                observation: dict[str, object] = {"operands": observed.operands}
                if observed.source != finding.source and observed.source is not None:
                    observation["source"] = observed.source
                if observed.surface != finding.surface and observed.surface is not None:
                    observation["surface"] = observed.surface
                if observation not in observations:
                    observations.append(observation)
            evidence["observation_count"] = len(findings)
            evidence["observations"] = observations
        instance = POIInstance.create(
            class_reference=tarav_poi_class_reference(finding.poi_class),
            target=POILocation(path=finding.surface or finding.subject),
            severity="error",
            situation=finding.subject,
            evidence=evidence,
            instance_id=finding.identity,
        )
        yield _ReportedInstance(status, findings, instance)


def _class_summaries(
    instances: tuple[_ReportedInstance, ...],
) -> list[dict[str, object]]:
    grouped: dict[str, list[_ReportedInstance]] = {}
    for item in instances:
        grouped.setdefault(item.class_address, []).append(item)

    rows: list[dict[str, object]] = []
    for address, members in sorted(grouped.items()):
        reference = members[0].instance.class_reference
        rows.append(
            {
                "class_address": address,
                "class_reference": reference.as_dict(),
                "class_reference_sugar": reference_sugar(reference),
                "sources": sorted(
                    {
                        finding.source
                        for item in members
                        for finding in item.findings
                        if finding.source
                    }
                ),
                "counts": {
                    "total": len(members),
                    "failed": sum(item.status == "failed" for item in members),
                    "blocked": sum(item.status == "blocked" for item in members),
                    "blessed": sum(item.status == "blessed" for item in members),
                },
            }
        )
    return rows


def _run_status(report: LintReport) -> str:
    if report.findings:
        return "failed"
    if report.blocked or report.blocked_checks:
        return "blocked"
    return "verified"


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError("invalid Index linter run document mapping")
    return value


def _list(value: object) -> list[object]:
    if not isinstance(value, list):
        raise TypeError("invalid Index linter run document list")
    return value


__all__ = [
    "LinterReportSelectionError",
    "build_linter_document",
    "render_linter_text",
]
