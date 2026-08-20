# $kw: ^wayfinder-poi-adapter --from POI.System --from POI.Linter --note [DF] registry findings map once while resolution failures retain bootstrap-safe inline POIs ^c20260729-49u
from __future__ import annotations

from tarav.poi import (
    POIInstance,
    POILinterReport,
    POILocation,
    build_poi_report,
    tarav_poi_class_reference,
)
from tarav.wayfinder.resolver import Wayfinder
from tarav.wayfinder.registry import WayfinderRegistryCheck, WayfinderRegistryFinding



def _registry_poi(
    finding: WayfinderRegistryFinding,
    class_name: str,
) -> POIInstance:
    evidence = {}
    if finding.root is not None:
        evidence["root"] = finding.root
    return POIInstance.create(
        class_reference=tarav_poi_class_reference(class_name),
        target=POILocation(path=finding.path or "Wayfinder.Registry"),
        severity="error",
        situation=finding.message,
        evidence=evidence,
    )


# $kw: Wayfinder.Registry.Linter/Registry.Invalid
# --note [DF] the Wayfinder registry cannot be read under its existing schema
# --note [CT] the instance preserves the registry path and existing parser message
# --note [RJ] class-level repair guidance is not yet established
def _invalid_registry(finding: WayfinderRegistryFinding) -> POIInstance:
    return _registry_poi(finding, "Wayfinder.Registry.Linter/Registry.Invalid")


# $kw: Wayfinder.Registry.Linter/Location.Stale
# --note [DF] a remembered Wayfinder root location no longer verifies as its registered resource
# --note [CT] the instance preserves the root identity, remembered path, and existing verification message
# --note [RJ] the registry location is operational evidence rather than resource identity or authority
def _stale_location(finding: WayfinderRegistryFinding) -> POIInstance:
    return _registry_poi(finding, "Wayfinder.Registry.Linter/Location.Stale")


CHECK_REGISTRY = {
    "invalid-registry": _invalid_registry,
    "stale-location": _stale_location,
}
WAYFINDER_REGISTRY_POI_CODES = tuple(CHECK_REGISTRY)


def registry_finding_to_poi(finding: WayfinderRegistryFinding) -> POIInstance:
    return CHECK_REGISTRY[finding.code](finding)


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
    "CHECK_REGISTRY",
    "build_wayfinder_registry_linter_report",
    "registry_finding_to_poi",
]
