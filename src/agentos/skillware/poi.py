# $kw: ^skillware-poi-adapter --from POI.System --from POI.Linter --note [DF] Skillware kinds map to valid class addresses while preserving producer hashes ^c20260729-49u
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from agentos.poi import POIDiagnostic, POIInstance, POILocation
from agentos.skw import NetworkFinding
from agentos.wayfinder import poi_class_reference


SKILLWARE_POI_CLASSES = {
    "parse-error": "Skillware.Linter/Parse.Error",
    "unresolvable": "Skillware.Linter/Unresolvable",
    "never-built": "Skillware.Linter/Never.Built",
    "stale-build": "Skillware.Linter/Stale.Build",
    "hand-edited": "Skillware.Linter/Hand.Edited",
    "copy-drift": "Skillware.Linter/Copy.Drift",
    "derived-stale": "Skillware.Linter/Derived.Stale",
    "undeclared-dependency": "Skillware.Linter/Dependency.Undeclared",
    "unhonored-dependency": "Skillware.Linter/Dependency.Unhonored",
    "dangling-dependency": "Skillware.Linter/Dependency.Dangling",
    "uncited-dependency": "Skillware.Linter/Dependency.Uncited",
    "context-assembly-bypass": "Skillware.Linter/Context.Assembly.Bypass",
    "malformed-note": "Skillware.Linter/Note.Malformed",
    "address-mismatch": "Skillware.Linter/Address.Mismatch",
    "legacy-callout": "Skillware.Linter/Callout.Legacy",
    "non-skw-annotation": "Skillware.Linter/Annotation.NonSkw",
    "illegal-attachment": "Skillware.Linter/Attachment.Illegal",
    "missing-header": "Skillware.Linter/Header.Missing",
    "missing-edition-history": "Skillware.Linter/Edition.History.Missing",
    "invalid-edition-history-record": (
        "Skillware.Linter/Edition.History.Record.Invalid"
    ),
    "duplicate-edition-session": "Skillware.Linter/Edition.Session.Duplicate",
    "unresolvable-edition-support": ("Skillware.Linter/Edition.Support.Unresolvable"),
    "unsupported-git-edition": "Skillware.Linter/Git.Edition.Unsupported",
}
_LINE_DETAIL_RE = re.compile(r"^line (\d+):")


@dataclass(frozen=True)
class SkillwarePOIInstance(POIInstance):
    @property
    def kind(self) -> str:
        return str(self.evidence["kind"])

    @property
    def key(self) -> str | None:
        value = self.evidence.get("key")
        return str(value) if value is not None else None

    @property
    def poi_hash(self) -> str:
        return self.instance_id

    @property
    def target_path(self) -> Path:
        return Path(self.target.path)

    @property
    def detail(self) -> str:
        return self.situation


def skillware_poi(
    kind: str,
    target: Path,
    key: str | None,
    payload: str,
    detail: str,
    severity: str = "advisory",
    evidence: dict[str, object] | None = None,
) -> SkillwarePOIInstance:
    identity = f"{target}|{kind}|{key}|{payload}"
    instance_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:10]
    return SkillwarePOIInstance.create(
        class_reference=poi_class_reference("agentos-pkg", SKILLWARE_POI_CLASSES[kind]),
        target=POILocation(path=str(target)),
        severity=severity,  # type: ignore[arg-type]
        situation=detail,
        evidence={
            "kind": kind,
            "key": key,
            "identity_payload": payload,
            **(evidence or {}),
        },
        instance_id=instance_id,
    )


def network_finding_to_poi(
    finding: NetworkFinding,
) -> SkillwarePOIInstance:
    return skillware_poi(
        finding.kind,
        finding.target,
        finding.key,
        finding.identity_payload,
        finding.detail,
        finding.severity,
    )


def edition_history_findings_to_pois(findings) -> tuple[SkillwarePOIInstance, ...]:
    return tuple(
        skillware_poi(
            finding.code,
            Path(finding.target),
            None,
            json.dumps(finding.as_dict(), sort_keys=True),
            finding.message,
            evidence={"edition_history": finding.as_dict()},
        )
        for finding in findings
    )


def suppress_blessed(
    lock: dict,
    pois: list[SkillwarePOIInstance],
) -> list[SkillwarePOIInstance]:
    blessed = {
        str(record.get("hash"))
        for record in lock.get("blessings", [])
        if record.get("hash")
    }
    if not blessed:
        return pois
    return [poi for poi in pois if poi.instance_id not in blessed]


def parser_diagnostics(
    pois: tuple[SkillwarePOIInstance, ...],
) -> tuple[POIDiagnostic, ...]:
    diagnostics = []
    for poi in pois:
        if poi.kind != "parse-error":
            continue
        match = _LINE_DETAIL_RE.match(poi.situation)
        line = int(match.group(1)) if match is not None else None
        diagnostics.append(
            POIDiagnostic(
                code="parse-error",
                target=POILocation(path=poi.target.path, line=line),
                message=poi.situation,
                evidence={
                    "origin": "Closure.Parser",
                    "compatibility_poi": poi.instance_id,
                },
            )
        )
    return tuple(diagnostics)


__all__ = [
    "SKILLWARE_POI_CLASSES",
    "SkillwarePOIInstance",
    "edition_history_findings_to_pois",
    "network_finding_to_poi",
    "parser_diagnostics",
    "skillware_poi",
    "suppress_blessed",
]
