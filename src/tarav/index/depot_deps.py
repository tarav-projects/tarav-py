# $kw: --from Index.Depot.Dependency
"""`Index.Depot.Dependency`: direct dependency declaration and resolution.

A depot resolves cross-depot mentions only against depots it *declares* as
dependencies (directed, non-transitive — `tarav-pkg` `Index.Depot.Dependency`).
Declaration is two-tier:

- **local** — the depot's `000-INDEX.md` router names its dependency depots
  **by name**, as a directive line (mirrors the existing ``> `Appendix.Discovery`:``
  router directive). This is the authoritative local declaration for this cut
  (see Impl.Req 701 Impl.Log: router-as-config).
- **global** — the Wayfinder registry resolves each package identity to its last
  verified filesystem location, so local declarations carry no absolute paths.

Resolution is non-transitive: a depot sees its own concepts plus those of its
*directly* declared dependencies only.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from tarav._core.project import global_config_path
from tarav.wayfinder import CorruptWayfinderRegistry, WayfinderRegistry

_DEPENDS_DIRECTIVE_RE = re.compile(
    r"^\s*>\s*`Index\.Depot\.Dependency`\s*:\s*(?P<names>.+?)\s*$", re.MULTILINE
)


def load_depot_registry(home: Path | None = None) -> dict[str, Path]:
    """Return registered Index roots keyed by their stable root identity."""
    try:
        entries = WayfinderRegistry(home=home).entries()
    except CorruptWayfinderRegistry:
        return {}
    return {
        entry.root.id: entry.path
        for entry in entries
        if entry.root.type in {"package.skill", "index.depot"}
    }


def _load_index_config(home: Path | None) -> dict:
    """The global config's ``index`` block, or ``{}`` — never a hard failure."""
    try:
        payload = json.loads(global_config_path(home).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    index = payload.get("index") if isinstance(payload, dict) else None
    return index if isinstance(index, dict) else {}


def load_default_depends(home: Path | None = None) -> list[str]:
    """Depot names every *registered* depot depends on by default (the prelude).

    Declared once in the global config's ``index.default_depends`` — e.g.
    ``["tarav-pkg"]`` so every tarav depot resolves against the shared
    ontology without repeating the declaration in each router.
    """
    names = _load_index_config(home).get("default_depends")
    return [str(n) for n in names] if isinstance(names, list) else []


def declared_dependency_names(depot_root: Path) -> list[str]:
    """The dependency depot names a depot's `000-INDEX.md` router declares.

    Order-preserving and deduped. No router or no directive -> empty list.
    """
    router = Path(depot_root) / "000-INDEX.md"
    try:
        text = router.read_text(encoding="utf-8")
    except OSError:
        return []
    names: list[str] = []
    for match in _DEPENDS_DIRECTIVE_RE.finditer(text):
        for raw in match.group("names").split(","):
            name = raw.strip().strip("`")
            if name and name not in names:
                names.append(name)
    return names


def resolve_dependency_depots(
    depot_root: Path, home: Path | None = None
) -> tuple[list[Path], list[str]]:
    """Resolve a depot's *direct* dependency depots to paths (non-transitive).

    Returns ``(resolved_paths, unresolved_names)``: declared names that the
    registry does not resolve are returned separately so the linter can flag an
    unresolved dependency. Resolution never recurses into a dependency's own
    dependencies.

    A *registered* depot (one that is itself in the registry) additionally
    inherits ``index.default_depends`` — the tarav-pkg prelude. The depot is
    never made to depend on itself.
    """
    registry = load_depot_registry(home)
    self_resolved = Path(depot_root).resolve()
    is_registered = any(p.resolve() == self_resolved for p in registry.values())

    default_names = load_default_depends(home) if is_registered else []
    names = list(dict.fromkeys([*default_names, *declared_dependency_names(depot_root)]))
    if not names:
        return [], []

    resolved: list[Path] = []
    unresolved: list[str] = []
    for name in names:
        target = registry.get(name)
        if target is None:
            unresolved.append(name)
        elif target.resolve() != self_resolved:
            resolved.append(target)
    return resolved, unresolved
