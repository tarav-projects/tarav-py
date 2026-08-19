# $kw: ^anchory-poi-adapter --from POI.System --from POI.Linter --note [DF] Anchory findings map once into package-owned POI instances ^c20260729-49u
from __future__ import annotations

from pathlib import Path

from tarav.wayfinder.index_blocks import create_index_wayfinder
from tarav.poi import (
    POIInstance,
    POILinterReport,
    POILocation,
    build_poi_report,
)
from tarav.wayfinder import poi_class_reference

from .core import AnchoryCheckFinding, AnchoryCheckResult


ANCHORY_POI_CLASSES = {
    "invalid-meta": "Anchory.Linter/Meta.Invalid",
    "invalid-shard-name": "Anchory.Linter/Shard.Name.Invalid",
    "invalid-json": "Anchory.Linter/Json.Invalid",
    "invalid-shard": "Anchory.Linter/Shard.Invalid",
    "invalid-record": "Anchory.Linter/Record.Invalid",
    "invalid-anchor": "Anchory.Linter/Anchor.Invalid",
    "misplaced-anchor": "Anchory.Linter/Anchor.Misplaced",
    "duplicate-anchor": "Anchory.Linter/Anchor.Duplicate",
    "tagless-anchor": "Anchory.Linter/Anchor.Tagless",
}
ANCHORY_POI_CODES = tuple(ANCHORY_POI_CLASSES)


def anchory_finding_to_poi(finding: AnchoryCheckFinding) -> POIInstance:
    evidence = {}
    if finding.anchor is not None:
        evidence["anchor"] = finding.anchor
    return POIInstance.create(
        class_reference=poi_class_reference(
            "tarav-pkg", ANCHORY_POI_CLASSES[finding.code]
        ),
        target=POILocation(path=finding.path),
        severity=finding.severity,  # type: ignore[arg-type]
        situation=finding.message,
        evidence=evidence,
    )


def build_anchory_linter_report(
    result: AnchoryCheckResult,
    *,
    depot: Path,
) -> POILinterReport:
    return POILinterReport(
        poi_report=build_poi_report(
            (anchory_finding_to_poi(finding) for finding in result.findings),
            wayfinder=create_index_wayfinder(),
        ),
        summary={
            "poi_count": len(result.findings),
            "error_count": sum(
                finding.severity == "error" for finding in result.findings
            ),
            "warning_count": sum(
                finding.severity == "warning" for finding in result.findings
            ),
        },
        domain={
            "depot": str(depot),
            "status": "ok" if result.ok else "error",
        },
    )


__all__ = [
    "ANCHORY_POI_CODES",
    "ANCHORY_POI_CLASSES",
    "anchory_finding_to_poi",
    "build_anchory_linter_report",
]
