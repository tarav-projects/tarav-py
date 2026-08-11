# $kw: ^wayfinder-poi-adapter --from POI.System --from POI.Linter --note [DF] registry findings map once while resolution failures retain bootstrap-safe inline POIs ^c20260729-49u
from __future__ import annotations

from agentos.poi import (
    POIInstance,
    POILinterReport,
    POILocation,
    build_poi_report,
)
from agentos.wayfinder.model import poi_class_reference
from agentos.wayfinder.resolver import Wayfinder
from agentos.wayfinder.registry import WayfinderRegistryCheck, WayfinderRegistryFinding



WAYFINDER_REGISTRY_POI_CLASSES = {
    "invalid-registry": "Wayfinder.Registry.Linter/Registry.Invalid",
    "stale-location": "Wayfinder.Registry.Linter/Location.Stale",
}
WAYFINDER_REGISTRY_POI_CODES = tuple(WAYFINDER_REGISTRY_POI_CLASSES)


def registry_finding_to_poi(finding: WayfinderRegistryFinding) -> POIInstance:
    evidence = {}
    if finding.root is not None:
        evidence["root"] = finding.root
    return POIInstance.create(
        class_reference=poi_class_reference(
            "agentos-pkg", WAYFINDER_REGISTRY_POI_CLASSES[finding.code]
        ),
        target=POILocation(path=finding.path or "Wayfinder.Registry"),
        severity="error",
        situation=finding.message,
        evidence=evidence,
    )


def build_wayfinder_registry_linter_report(
    result: WayfinderRegistryCheck,
    *,
    registry_path: str,
    wayfinder: Wayfinder,
) -> POILinterReport:
    return POILinterReport(
        poi_report=build_poi_report(
            (registry_finding_to_poi(finding) for finding in result.findings),
            wayfinder=wayfinder,
        ),
        summary={
            "poi_count": len(result.findings),
            "error_count": len(result.findings),
            "warning_count": 0,
        },
        domain={
            "registry": registry_path,
            "status": "ok" if result.ok else "poi",
        },
    )


__all__ = [
    "WAYFINDER_REGISTRY_POI_CODES",
    "WAYFINDER_REGISTRY_POI_CLASSES",
    "build_wayfinder_registry_linter_report",
    "registry_finding_to_poi",
]
