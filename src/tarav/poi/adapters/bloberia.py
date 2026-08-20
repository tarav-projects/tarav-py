# $kw: ^bloberia-poi-adapter --from POI.System --from POI.Linter --note [DF] Bloberia findings map once into package-owned POI instances ^c20260729-49u
from __future__ import annotations

from pathlib import Path

from tarav.bloberia.core import BloberiaCheckFinding, BloberiaCheckResult
from tarav.poi import (
    POIInstance,
    POILinterReport,
    POILocation,
    build_poi_report,
    tarav_poi_class_reference,
)
from tarav.wayfinder import Wayfinder



def _bloberia_poi(
    finding: BloberiaCheckFinding,
    class_name: str,
) -> POIInstance:
    return POIInstance.create(
        class_reference=tarav_poi_class_reference(class_name),
        target=POILocation(path=finding.path),
        severity="error",
        situation=finding.message,
        evidence={},
    )


# $kw: Bloberia.Linter/Json.Invalid
# --note [DF] a Bloberia record file cannot be read as JSON
# --note [CT] the instance preserves the existing parser error and path
# --note [RJ] class-level repair guidance is not yet established
def _invalid_json(finding: BloberiaCheckFinding) -> POIInstance:
    """Enforce the one invariant owned by a cargo-verbatim depot.

    ``Record.Filename.Invalid``, ``Record.Invalid`` and ``Identity.Mismatch``
    retired with the envelope they inspected: the store has no record shape of
    its own left to violate.
    """
    return _bloberia_poi(finding, "Bloberia.Linter/Json.Invalid")


CHECK_REGISTRY = {"invalid-json": _invalid_json}
BLOBERIA_POI_CODES = tuple(CHECK_REGISTRY)


def bloberia_finding_to_poi(finding: BloberiaCheckFinding) -> POIInstance:
    return CHECK_REGISTRY[finding.code](finding)


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
    "CHECK_REGISTRY",
    "bloberia_finding_to_poi",
    "build_bloberia_linter_report",
]
