# $kw: ^skw-network-findings --from POI.System --from POI.Linter --note [DF] backend-neutral dependency drift algorithms emit domain findings for later POI adaptation ^c20260729-49u
# $kw: ^skw-network --from Dependency.Profile.Split --note [DF] backend-neutral dependency-network mechanics are shared by Index and Skillware without either core importing the other --supp ^c20260811-62u
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


_BACKTICKED_DOTTED_NAME_RE = re.compile(
    r"`([A-Z][A-Za-z0-9]*(?:\.[A-Z][A-Za-z0-9]*)+"
    r"(?:::[A-Z][A-Za-z0-9]*(?:\.[A-Z][A-Za-z0-9]*)+)?)`"
)


def extract_mentions(text: str) -> set[str]:
    return set(_BACKTICKED_DOTTED_NAME_RE.findall(text))


@dataclass(frozen=True)
class NetworkFinding:
    kind: str
    target: Path
    key: str | None
    identity_payload: str
    detail: str
    severity: str = "advisory"

    @property
    def poi_hash(self) -> str:
        identity = f"{self.target}|{self.kind}|{self.key}|{self.identity_payload}"
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:10]


def network_finding(
    kind: str,
    target: Path,
    key: str | None,
    payload: str,
    detail: str,
    severity: str = "advisory",
) -> NetworkFinding:
    return NetworkFinding(
        kind=kind,
        target=target,
        key=key,
        identity_payload=payload,
        detail=detail,
        severity=severity,
    )


@runtime_checkable
class SurfaceProvider(Protocol):
    def declared_edges(self) -> tuple[set[str], set[str]]: ...

    def mentions(self) -> set[str]: ...

    def resolve(self, names: set[str]) -> dict[str, str]: ...


def run_dependency_sync(
    target_rel: Path,
    provider: SurfaceProvider,
) -> list[NetworkFinding]:
    declared, declared_from_depends = provider.declared_edges()
    mention_resolutions = {
        name: resolution
        for name, resolution in provider.resolve(provider.mentions()).items()
        if not resolution.startswith("unresolved:")
    }
    return dependency_sync_findings(
        target_rel,
        declared,
        declared_from_depends,
        mention_resolutions,
        provider.resolve(declared),
    )


def dangling_mention_findings(
    target_rel: Path,
    mention_resolutions: dict[str, str],
) -> list[NetworkFinding]:
    return [
        network_finding(
            "dangling-mention",
            target_rel,
            name,
            resolution,
            f"mention `{name}` no longer resolves to a concept",
        )
        for name, resolution in sorted(mention_resolutions.items())
        if resolution.startswith("unresolved:")
    ]


def dependency_sync_findings(
    target_rel: Path,
    declared: set[str],
    declared_from_depends: set[str],
    mention_resolutions: dict[str, str],
    declared_resolutions: dict[str, str],
) -> list[NetworkFinding]:
    dangling = {
        name
        for name, resolution in declared_resolutions.items()
        if resolution.startswith("unresolved:")
    }
    findings: list[NetworkFinding] = []
    for name in sorted(dangling):
        findings.append(
            network_finding(
                "dangling-dependency",
                target_rel,
                name,
                declared_resolutions[name],
                f"declared dependency `{name}` no longer resolves in the configured depots",
            )
        )
    for name, resolution in sorted(mention_resolutions.items()):
        if name in declared:
            continue
        findings.append(
            network_finding(
                "undeclared-dependency",
                target_rel,
                name,
                resolution,
                f"mention `{name}` resolves but has no declared dependency",
            )
        )
    for name in sorted(declared_from_depends):
        if name in mention_resolutions or name in dangling:
            continue
        findings.append(
            network_finding(
                "unhonored-dependency",
                target_rel,
                name,
                declared_resolutions.get(name, "unresolved"),
                f"declared dependency `{name}` is not mentioned in compiled text",
            )
        )
    return findings
