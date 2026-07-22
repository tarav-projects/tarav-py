"""`Index.Depot.Dependency`: the two-tier dependency declaration (Impl.Req 701).

A depot resolves cross-depot mentions only against depots it *declares* as
dependencies (directed, non-transitive — `agentos-pkg` `Index.Depot.Dependency`).
Declaration is two-tier:

- **local** — the depot's `000-INDEX.md` router names its dependency depots
  **by name**, as a directive line (mirrors the existing ``> `Appendix.Discovery`:``
  router directive). This is the authoritative local declaration for this cut
  (see Impl.Req 701 Impl.Log: router-as-config).
- **global** — the ``~/.agentos`` registry resolves each name -> a filesystem
  location, so local declarations carry no absolute paths. The registry reuses
  the `skills.routing.sources` name->location shape as a sibling `index.depots`
  key.

Resolution is non-transitive: a depot sees its own concepts plus those of its
*directly* declared dependencies only.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from agentos._core.project import agentos_home_dir, global_config_path

_DEPENDS_DIRECTIVE_RE = re.compile(
    r"^\s*>\s*`Index\.Depot\.Dependency`\s*:\s*(?P<names>.+?)\s*$", re.MULTILINE
)


def load_depot_registry(home: Path | None = None) -> dict[str, Path]:
    """The global depot registry: depot name -> depot root `Path`.

    Read from ``<home>/config.json`` (``AGENTOS_HOME`` honored via
    `agentos_home_dir`). Missing config, malformed JSON, or a missing
    ``index.depots`` key all yield an empty map — the registry is optional
    plumbing, never a hard failure. Each entry accepts a ``path`` or
    ``project`` location, matching the `skills.routing.sources` forms.
    """
    config_path = global_config_path(home)
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    depots = (((payload.get("index") or {}).get("depots")) or {}) if isinstance(
        payload.get("index"), dict
    ) else {}
    registry: dict[str, Path] = {}
    for name, entry in depots.items():
        if not isinstance(entry, dict):
            continue
        location = entry.get("path") or entry.get("project")
        if isinstance(location, str) and location:
            registry[str(name)] = Path(location)
    return registry


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
    """
    names = declared_dependency_names(depot_root)
    if not names:
        return [], []
    registry = load_depot_registry(home)
    resolved: list[Path] = []
    unresolved: list[str] = []
    for name in names:
        target = registry.get(name)
        if target is None:
            unresolved.append(name)
        else:
            resolved.append(target)
    return resolved, unresolved
