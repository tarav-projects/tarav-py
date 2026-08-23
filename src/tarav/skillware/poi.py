# $kw: ^skillware-poi-adapter --from POI.System --from POI.Linter --note [DF] Skillware kinds map to valid class addresses while preserving producer hashes ^c20260729-49u
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from tarav.poi import (
    POIDiagnostic,
    POIInstance,
    POILocation,
    tarav_poi_class_reference,
)
from tarav.skw.network import NetworkFinding


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


def _skillware_poi(
    class_name: str,
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
        class_reference=tarav_poi_class_reference(class_name),
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


def _bound_poi(class_name: str):
    def emit(
        kind: str,
        target: Path,
        key: str | None,
        payload: str,
        detail: str,
        severity: str = "advisory",
        evidence: dict[str, object] | None = None,
    ) -> SkillwarePOIInstance:
        return _skillware_poi(
            class_name,
            kind,
            target,
            key,
            payload,
            detail,
            severity,
            evidence,
        )

    return emit


# $kw: Skillware.Linter/Parse.Error
# --note [DF] the source is below the parse floor because machinery is malformed or a construct is unclosed
# --note [CT] this compatibility POI is accompanied by a distinct `Closure.Parser` diagnostic
# --note [PR] fix the source; parse errors gate that file's other checks and are not blessable
def _parse_error(*args, **kwargs) -> SkillwarePOIInstance:
    return _bound_poi("Skillware.Linter/Parse.Error")(*args, **kwargs)


# $kw: Skillware.Linter/Unresolvable
# --note [DF] a `--from` target does not resolve at its declared address
# --note [PR] fix the address or restore the target; this class is not blessable
def _unresolvable(*args, **kwargs) -> SkillwarePOIInstance:
    return _bound_poi("Skillware.Linter/Unresolvable")(*args, **kwargs)


# $kw: Skillware.Linter/Never.Built --note [DF] a source exists without a corresponding lock entry
# --note [PR] run `tarav skw build` to create the missing lock entry ^c20260821-62u
def _never_built(*args, **kwargs) -> SkillwarePOIInstance:
    return _bound_poi("Skillware.Linter/Never.Built")(*args, **kwargs)


# $kw: Skillware.Linter/Stale.Build --note [DF] the on-disk target matches the lock while a fresh compilation differs
# --note [PR] run `tarav skw build` to refresh the stale target ^c20260821-63u
def _stale_build(*args, **kwargs) -> SkillwarePOIInstance:
    return _bound_poi("Skillware.Linter/Stale.Build")(*args, **kwargs)


# $kw: Skillware.Linter/Hand.Edited --note [DF] a compiled target was edited outside its source
# --note [PR] move the intended content into the source or rebuild over the target
def _hand_edited(*args, **kwargs) -> SkillwarePOIInstance:
    return _bound_poi("Skillware.Linter/Hand.Edited")(*args, **kwargs)


# $kw: Skillware.Linter/Copy.Drift --note [DF] a copy body no longer equals the expansion of its target
# --note [PR] run `tarav skw build` to restore the generated copy body ^c20260821-64u
def _copy_drift(*args, **kwargs) -> SkillwarePOIInstance:
    return _bound_poi("Skillware.Linter/Copy.Drift")(*args, **kwargs)


# $kw: Skillware.Linter/Derived.Stale --note [DF] a dependency changed since the derived body was written
# --note [PR] re-derive the source body or explicitly bless the current instance
def _derived_stale(*args, **kwargs) -> SkillwarePOIInstance:
    return _bound_poi("Skillware.Linter/Derived.Stale")(*args, **kwargs)


# $kw: Skillware.Linter/Dependency.Undeclared
# --note [DF] compiled text mentions a resolving dotted name without declaring its dependency
# --note [PR] declare the dependency with `--from` or explicitly bless the current instance
def _dependency_undeclared(*args, **kwargs) -> SkillwarePOIInstance:
    return _bound_poi("Skillware.Linter/Dependency.Undeclared")(*args, **kwargs)


# $kw: Skillware.Linter/Dependency.Unhonored
# --note [DF] a declared dependency is not mentioned in compiled text
# --note [PR] mention the dependency, remove the declaration, or explicitly bless the instance
def _dependency_unhonored(*args, **kwargs) -> SkillwarePOIInstance:
    return _bound_poi("Skillware.Linter/Dependency.Unhonored")(*args, **kwargs)


# $kw: Skillware.Linter/Dependency.Dangling
# --note [DF] a declared `--from` target no longer resolves in the Index records
# --note [PR] restore or repoint the target, or explicitly bless the instance
def _dependency_dangling(*args, **kwargs) -> SkillwarePOIInstance:
    return _bound_poi("Skillware.Linter/Dependency.Dangling")(*args, **kwargs)


# $kw: Skillware.Linter/Dependency.Uncited
# --note [DF] a `--cite` target is not explicit in the compiled surface
# --note [PR] cite the target visibly, change its role, or explicitly bless the instance
def _dependency_uncited(*args, **kwargs) -> SkillwarePOIInstance:
    return _bound_poi("Skillware.Linter/Dependency.Uncited")(*args, **kwargs)


# $kw: Skillware.Linter/Context.Assembly.Bypass
# --note [DF] a surface depends on assembly-covered source without loading its context assembly
# --note [PR] add the required `--dev-from` or explicitly bless the intentional bypass
def _context_assembly_bypass(*args, **kwargs) -> SkillwarePOIInstance:
    return _bound_poi("Skillware.Linter/Context.Assembly.Bypass")(*args, **kwargs)


# $kw: Skillware.Linter/Note.Malformed
# --note [DF] a `--note` or `--supp` lacks its act code or trailing anchor
# --note [PR] add the missing type and support anchor in the source
def _note_malformed(*args, **kwargs) -> SkillwarePOIInstance:
    return _bound_poi("Skillware.Linter/Note.Malformed")(*args, **kwargs)


# $kw: Skillware.Linter/Address.Mismatch
# --note [DF] a fenced element name differs from its declared address
# --note [PR] align the element name and address
def _address_mismatch(*args, **kwargs) -> SkillwarePOIInstance:
    return _bound_poi("Skillware.Linter/Address.Mismatch")(*args, **kwargs)


# $kw: Skillware.Linter/Callout.Inert
# --note [DF] a `[!skw]` callout line outside a fence is prose the parser does not read as an annotation
# --note [CT] the class names what the parser found, not the grammar version that produced it
# --note [PR] rewrite it using current `$kw` grammar
def _callout_legacy(*args, **kwargs) -> SkillwarePOIInstance:
    return _bound_poi("Skillware.Linter/Callout.Inert")(*args, **kwargs)


# $kw: Skillware.Linter/Annotation.NonSkw
# --note [DF] a comment on a managed code surface is not represented as a `Skw.Annotation`
# --note [PR] encode it as an annotation, remove it, or explicitly bless the instance
def _annotation_non_skw(*args, **kwargs) -> SkillwarePOIInstance:
    return _bound_poi("Skillware.Linter/Annotation.NonSkw")(*args, **kwargs)


# $kw: Skillware.Linter/Attachment.Illegal
# --note [DF] a Skw block attaches outside the surface's sanctioned point set
# --note [PR] move it to a sanctioned point or change the owning attachment policy
def _attachment_illegal(*args, **kwargs) -> SkillwarePOIInstance:
    return _bound_poi("Skillware.Linter/Attachment.Illegal")(*args, **kwargs)


# $kw: Skillware.Linter/Header.Missing
# --note [DF] a managed code file lacks the required line-one annotation
# --note [PR] add the line-one header or change the owning presence policy
def _header_missing(*args, **kwargs) -> SkillwarePOIInstance:
    return _bound_poi("Skillware.Linter/Header.Missing")(*args, **kwargs)


# $kw: Skillware.Linter/Edition.History.Missing
# --note [DF] a configured file has no valid edition and session association
# --note [PR] inspect Git and Chatlas, then record a supported association
def _edition_history_missing(*args, **kwargs) -> SkillwarePOIInstance:
    return _bound_poi("Skillware.Linter/Edition.History.Missing")(*args, **kwargs)


# $kw: Skillware.Linter/Edition.History.Record.Invalid
# --note [DF] an edition-history record violates the existing service schema
# --note [PR] repair or replace the invalid record
def _edition_history_record_invalid(*args, **kwargs) -> SkillwarePOIInstance:
    return _bound_poi("Skillware.Linter/Edition.History.Record.Invalid")(
        *args, **kwargs
    )


# $kw: Skillware.Linter/Edition.Session.Duplicate
# --note [DF] one file edition and session association is recorded more than once
# --note [PR] remove the duplicate record
def _edition_session_duplicate(*args, **kwargs) -> SkillwarePOIInstance:
    return _bound_poi("Skillware.Linter/Edition.Session.Duplicate")(*args, **kwargs)


# $kw: Skillware.Linter/Edition.Support.Unresolvable
# --note [DF] an edition and session support set cannot be resolved through Chatlas
# --note [PR] repair the exact session and event support members
def _edition_support_unresolvable(*args, **kwargs) -> SkillwarePOIInstance:
    return _bound_poi("Skillware.Linter/Edition.Support.Unresolvable")(*args, **kwargs)


# $kw: Skillware.Linter/Git.Edition.Unsupported
# --note [DF] a Git edition has no resolvable edition and session association
# --note [PR] recover candidate chats and record supported associations
def _git_edition_unsupported(*args, **kwargs) -> SkillwarePOIInstance:
    return _bound_poi("Skillware.Linter/Git.Edition.Unsupported")(*args, **kwargs)


CHECK_REGISTRY = {
    "parse-error": _parse_error,
    "unresolvable": _unresolvable,
    "never-built": _never_built,
    "stale-build": _stale_build,
    "hand-edited": _hand_edited,
    "copy-drift": _copy_drift,
    "derived-stale": _derived_stale,
    "undeclared-dependency": _dependency_undeclared,
    "unhonored-dependency": _dependency_unhonored,
    "dangling-dependency": _dependency_dangling,
    "uncited-dependency": _dependency_uncited,
    "context-assembly-bypass": _context_assembly_bypass,
    "malformed-note": _note_malformed,
    "address-mismatch": _address_mismatch,
    "legacy-callout": _callout_legacy,
    "non-skw-annotation": _annotation_non_skw,
    "illegal-attachment": _attachment_illegal,
    "missing-header": _header_missing,
    "missing-edition-history": _edition_history_missing,
    "invalid-edition-history-record": _edition_history_record_invalid,
    "duplicate-edition-session": _edition_session_duplicate,
    "unresolvable-edition-support": _edition_support_unresolvable,
    "unsupported-git-edition": _git_edition_unsupported,
}


def skillware_poi(
    kind: str,
    target: Path,
    key: str | None,
    payload: str,
    detail: str,
    severity: str = "advisory",
    evidence: dict[str, object] | None = None,
) -> SkillwarePOIInstance:
    return CHECK_REGISTRY[kind](
        kind,
        target,
        key,
        payload,
        detail,
        severity,
        evidence,
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
    "CHECK_REGISTRY",
    "SkillwarePOIInstance",
    "edition_history_findings_to_pois",
    "network_finding_to_poi",
    "parser_diagnostics",
    "skillware_poi",
    "suppress_blessed",
]
