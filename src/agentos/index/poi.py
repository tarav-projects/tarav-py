from __future__ import annotations

from agentos.poi import POICatalog, POICatalogError, POIInstance, POILocation
from agentos.wayfinder import poi_class_reference

from ._linter_models import LinterFinding


def finding_to_poi(
    finding: LinterFinding,
    catalog: POICatalog,
    *,
    package_id: str = "agentos-pkg",
) -> POIInstance:
    expected_reference = poi_class_reference(package_id, finding.code)
    registered_reference = catalog.get(finding.code)
    if registered_reference is not None and registered_reference != expected_reference:
        raise POICatalogError(
            f"POI class {finding.code} is owned by "
            f"{registered_reference.root.id}, not {package_id}"
        )
    return POIInstance.create(
        class_reference=registered_reference or expected_reference,
        target=POILocation(path=finding.path, line=finding.line),
        severity=finding.severity,
        situation=finding.message,
        evidence=finding.details,
    )


__all__ = ["finding_to_poi"]
