"""Surface-agnostic linter core for the skw system.

The general `Poi.Linter` machinery, independent of any one `Skw.Backend`: the
advisory `Poi` finding type, its bless/suppress plumbing, and the `Skw.Network`
dependency-sync engine. Each backend (skw-skills, index, ...) supplies its own
declared edges and resolved mentions and consumes these primitives.

Extracted from `skillware/build.py` (Impl.Req 700, slice 1) with no behavior
change: the skw-skills backend adapts its `SkwSource`/`Expansion` to these
inputs. Lives at `agentos.skwlint` — a neutral home so backends outside the
skillware package (the index linter) can consume it without importing
`skillware/`.
"""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

_BACKTICKED_DOTTED_NAME_RE = re.compile(
    r"`([A-Z][A-Za-z0-9]*(?:\.[A-Z][A-Za-z0-9]*)+(?:::[A-Z][A-Za-z0-9]*(?:\.[A-Z][A-Za-z0-9]*)+)?)`"
)


def extract_mentions(text: str) -> set[str]:
    """Return backticked addressable dotted names visible in compiled text.

    Surface-agnostic: mentions look the same on every backend, so the core owns
    the extractor and each `SurfaceProvider` feeds it its own compiled text.
    """
    return set(_BACKTICKED_DOTTED_NAME_RE.findall(text))

# Severity is a property of the check, not of the linter. Drift is advisory in
# every backend (`Drift.POI`: the CPU never rules on drift); a backend's own
# structural/well-formedness checks may raise ERROR (gated, unblessable).
ADVISORY = "advisory"
ERROR = "error"


@dataclass(frozen=True)
class Poi:
    """A point of interest: a place worth an agent's attention.

    Advisory by default — a POI is never a verdict. `severity` lets a backend
    raise a gated ERROR from its own structural checks; the dependency-sync
    engine only ever produces ADVISORY findings.
    """

    kind: str
    target: Path
    key: str | None
    poi_hash: str
    detail: str
    severity: str = ADVISORY


def poi(
    kind: str,
    target: Path,
    key: str | None,
    payload: str,
    detail: str,
    severity: str = ADVISORY,
) -> Poi:
    digest = hashlib.sha256(f"{target}|{kind}|{key}|{payload}".encode("utf-8")).hexdigest()
    return Poi(
        kind=kind,
        target=target,
        key=key,
        poi_hash=digest[:10],
        detail=detail,
        severity=severity,
    )


@runtime_checkable
class SurfaceProvider(Protocol):
    """A per-surface backend's binding into the dependency-sync engine.

    Each `Skw.Backend` (skw-skills, index, ...) implements this so the core can
    run drift over its surface without knowing anything about markdown vs index
    blocks vs code. Three questions, per the `Surface.Provider.Interface`:
    what does the surface declare, what does it mention, and how does a name
    resolve on this surface (the resolver is where a per-surface address schema
    plugs in).
    """

    def declared_edges(self) -> tuple[set[str], set[str]]:
        """(all declared names, the subset that are `--from`-style dependencies)."""

    def mentions(self) -> set[str]:
        """Addressable names the compiled surface actually references."""

    def resolve(self, names: set[str]) -> dict[str, str]:
        """Map each name to a content hash, or ``"unresolved:<detail>"``."""


def run_dependency_sync(target_rel: Path, provider: SurfaceProvider) -> list[Poi]:
    """Orchestrate dependency-sync for one surface via its provider."""
    declared, declared_from_depends = provider.declared_edges()
    mention_resolutions = {
        name: resolution
        for name, resolution in provider.resolve(provider.mentions()).items()
        if not resolution.startswith("unresolved:")
    }
    declared_resolutions = provider.resolve(declared)
    return dependency_sync_findings(
        target_rel,
        declared,
        declared_from_depends,
        mention_resolutions,
        declared_resolutions,
    )


def dangling_mention_findings(
    target_rel: Path, mention_resolutions: dict[str, str]
) -> list[Poi]:
    """Flag mentions that no longer resolve — the edge-free drift check.

    A surface with no declared edges (the index) still drifts when a name it
    references is renamed or removed: the mention stops resolving. Given every
    mention resolved to a content hash or ``"unresolved:<detail>"``, raise an
    advisory `dangling-mention` for each unresolved one. Correctness rests
    entirely on the resolver: it must recognize every legitimate concept form
    (headings, inline definitions, aliases/canonical short-forms, ``::``-scoped
    names, cross-depot) or benign references are misflagged.
    """
    findings: list[Poi] = []
    for name, resolution in sorted(mention_resolutions.items()):
        if resolution.startswith("unresolved:"):
            findings.append(
                poi(
                    "dangling-mention",
                    target_rel,
                    name,
                    resolution,
                    f"mention `{name}` no longer resolves to a concept",
                )
            )
    return findings


def blessed_hashes(lock: dict) -> set[str]:
    return {
        str(record.get("hash"))
        for record in lock.get("blessings", [])
        if record.get("hash")
    }


def suppress_blessed(lock: dict, pois: list[Poi]) -> list[Poi]:
    blessed = blessed_hashes(lock)
    if not blessed:
        return pois
    return [p for p in pois if p.poi_hash not in blessed]


def dependency_sync_findings(
    target_rel: Path,
    declared: set[str],
    declared_from_depends: set[str],
    mention_resolutions: dict[str, str],
    declared_resolutions: dict[str, str],
) -> list[Poi]:
    """The `Skw.Network` dependency-sync engine, surface-agnostic.

    Given a surface's declared edges and the resolution of its declared names
    and its mentions, raise the three drift POIs: `dangling-dependency` (a
    declared edge no longer resolves), `undeclared-dependency` (a resolving
    mention with no declaration), `unhonored-dependency` (a declared dependency
    never mentioned). Inputs are plain names; how a backend extracts its
    declarations and mentions is the backend's concern.
    """
    dangling = {
        name
        for name, resolution in declared_resolutions.items()
        if resolution.startswith("unresolved:")
    }
    findings: list[Poi] = []
    for name in sorted(dangling):
        findings.append(
            poi(
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
            poi(
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
        resolution = declared_resolutions.get(name, "unresolved")
        findings.append(
            poi(
                "unhonored-dependency",
                target_rel,
                name,
                resolution,
                f"declared dependency `{name}` is not mentioned in compiled text",
            )
        )
    return findings
