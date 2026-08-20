# $kw: ^bloberia-poi-adapter --from POI.System --from POI.Linter --note [DF] Bloberia findings map once into package-owned POI instances ^c20260729-49u
from __future__ import annotations

from pathlib import Path

from tarav.bloberia.core import BloberiaCheckFinding, BloberiaCheckResult
from tarav.poi import (
    POIInstance,
    POILinterReport,
    POILocation,
    build_poi_report,
)
from tarav.wayfinder import poi_class_reference
from tarav.wayfinder import Wayfinder



#: One class, because the depot owns one invariant. `Record.Filename.Invalid`,
#: `Record.Invalid` and `Identity.Mismatch` retired with the envelope they inspected:
#: a store that stores cargo verbatim has no shape of its own left to violate.
BLOBERIA_POI_CLASSES = {
    "invalid-json": "Bloberia.Linter/Json.Invalid",
}
BLOBERIA_POI_CODES = tuple(BLOBERIA_POI_CLASSES)


def bloberia_finding_to_poi(finding: BloberiaCheckFinding) -> POIInstance:
    return POIInstance.create(
        class_reference=poi_class_reference(
            "tarav-pkg", BLOBERIA_POI_CLASSES[finding.code]
        ),
        target=POILocation(path=finding.path),
        severity="error",
        situation=finding.message,
        evidence={},
    )


def build_bloberia_linter_report(
    result: BloberiaCheckResult,
    *,
    depot: Path,
    wayfinder: Wayfinder,
) -> POILinterReport:
    return POILinterReport(
        poi_report=build_poi_report(
            (bloberia_finding_to_poi(finding) for finding in result.findings),
            wayfinder=wayfinder,
        ),
        summary={
            "poi_count": len(result.findings),
            "error_count": len(result.findings),
            "warning_count": 0,
        },
        domain={
            "depot": str(depot),
            "status": "ok" if result.ok else "error",
        },
    )


__all__ = [
    "BLOBERIA_POI_CODES",
    "BLOBERIA_POI_CLASSES",
    "bloberia_finding_to_poi",
    "build_bloberia_linter_report",
]
