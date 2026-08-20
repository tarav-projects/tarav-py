# $kw: ^anchory-poi-adapter --from POI.System --from POI.Linter --note [DF] Anchory findings map once into package-owned POI instances ^c20260729-49u
from __future__ import annotations

from pathlib import Path

from tarav.skillware._build_core import find_project_root
from tarav.skillware.managed_blocks import create_tarav_wayfinder
from tarav.poi import (
    POIInstance,
    POILinterReport,
    POILocation,
    build_poi_report,
    tarav_poi_class_reference,
)

from .core import AnchoryCheckFinding, AnchoryCheckResult


def _anchory_poi(
    finding: AnchoryCheckFinding,
    class_name: str,
) -> POIInstance:
    evidence = {}
    if finding.anchor is not None:
        evidence["anchor"] = finding.anchor
    return POIInstance.create(
        class_reference=tarav_poi_class_reference(class_name),
        target=POILocation(path=finding.path),
        severity=finding.severity,  # type: ignore[arg-type]
        situation=finding.message,
        evidence=evidence,
    )


# $kw: Anchory.Linter/Meta.Invalid
# --note [DF] an Anchory namespace metadata file is invalid
# --note [CT] the instance preserves the existing validator message and metadata path
# --note [RJ] class-level repair guidance is not yet established
def _invalid_meta(finding: AnchoryCheckFinding) -> POIInstance:
    return _anchory_poi(finding, "Anchory.Linter/Meta.Invalid")


# $kw: Anchory.Linter/Shard.Name.Invalid
# --note [DF] an Anchory shard filename violates the existing shard-name grammar
# --note [CT] the instance preserves the existing validator message and shard path
# --note [RJ] class-level repair guidance is not yet established
def _invalid_shard_name(finding: AnchoryCheckFinding) -> POIInstance:
    return _anchory_poi(finding, "Anchory.Linter/Shard.Name.Invalid")


# $kw: Anchory.Linter/Json.Invalid
# --note [DF] an Anchory shard cannot be read as JSON
# --note [CT] the instance preserves the existing parser error and shard path
# --note [RJ] class-level repair guidance is not yet established
def _invalid_json(finding: AnchoryCheckFinding) -> POIInstance:
    return _anchory_poi(finding, "Anchory.Linter/Json.Invalid")


# $kw: Anchory.Linter/Shard.Invalid
# --note [DF] an Anchory shard payload is not the JSON object required by the depot format
# --note [CT] the instance preserves the existing validator message and shard path
# --note [RJ] class-level repair guidance is not yet established
def _invalid_shard(finding: AnchoryCheckFinding) -> POIInstance:
    return _anchory_poi(finding, "Anchory.Linter/Shard.Invalid")


# $kw: Anchory.Linter/Record.Invalid
# --note [DF] an Anchory entry does not contain the JSON object required for an application-owned record
# --note [CT] the instance preserves the existing anchor and shard evidence
# --note [RJ] class-level repair guidance is not yet established
def _invalid_record(finding: AnchoryCheckFinding) -> POIInstance:
    return _anchory_poi(finding, "Anchory.Linter/Record.Invalid")


# $kw: Anchory.Linter/Anchor.Invalid
# --note [DF] an Anchory record key violates the existing nonempty anchor requirement
# --note [CT] the instance preserves the existing key and shard evidence
# --note [RJ] class-level repair guidance is not yet established
def _invalid_anchor(finding: AnchoryCheckFinding) -> POIInstance:
    return _anchory_poi(finding, "Anchory.Linter/Anchor.Invalid")


# $kw: Anchory.Linter/Anchor.Misplaced
# --note [DF] an Anchory record is stored outside the shard selected by its key
# --note [CT] the instance preserves the anchor and current shard evidence
# --note [RJ] class-level repair guidance is not yet established
def _misplaced_anchor(finding: AnchoryCheckFinding) -> POIInstance:
    return _anchory_poi(finding, "Anchory.Linter/Anchor.Misplaced")


# $kw: Anchory.Linter/Anchor.Duplicate
# --note [DF] the same Anchory key appears in more than one shard
# --note [CT] the instance preserves the duplicate key and observed shard
# --note [RJ] class-level repair guidance is not yet established
def _duplicate_anchor(finding: AnchoryCheckFinding) -> POIInstance:
    return _anchory_poi(finding, "Anchory.Linter/Anchor.Duplicate")


# $kw: Anchory.Linter/Anchor.Tagless
# --note [DF] a key in a prefixed Anchory namespace carries no application tag
# --note [CT] the existing validator reports this condition as a warning
# --note [RJ] class-level evaluation and amendment guidance is not yet established
def _tagless_anchor(finding: AnchoryCheckFinding) -> POIInstance:
    return _anchory_poi(finding, "Anchory.Linter/Anchor.Tagless")


CHECK_REGISTRY = {
    "invalid-meta": _invalid_meta,
    "invalid-shard-name": _invalid_shard_name,
    "invalid-json": _invalid_json,
    "invalid-shard": _invalid_shard,
    "invalid-record": _invalid_record,
    "invalid-anchor": _invalid_anchor,
    "misplaced-anchor": _misplaced_anchor,
    "duplicate-anchor": _duplicate_anchor,
    "tagless-anchor": _tagless_anchor,
}
ANCHORY_POI_CODES = tuple(CHECK_REGISTRY)


def anchory_finding_to_poi(finding: AnchoryCheckFinding) -> POIInstance:
    return CHECK_REGISTRY[finding.code](finding)


def build_anchory_linter_report(
    result: AnchoryCheckResult,
    *,
    depot: Path,
) -> POILinterReport:
    return POILinterReport(
        poi_report=build_poi_report(
            (anchory_finding_to_poi(finding) for finding in result.findings),
            wayfinder=create_tarav_wayfinder(
                project_root=find_project_root(Path(__file__))
            ),
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
    "CHECK_REGISTRY",
    "anchory_finding_to_poi",
    "build_anchory_linter_report",
]
