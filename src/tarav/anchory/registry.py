# $kw: --from Anchory.System
"""Anchory depot registry and discovery.

The registry records every depot an anchory command touches, keyed by root
path, with the namespaces (and declared prefixes) seen there. It powers
`Pwd.Upward.Search`: resolving an anchor without a depot searches registered
depots closest to the working directory first, then the global depot.

Registry writes are best-effort: they must never raise into depot operations.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from tarav._core.persistence import atomic_write_json

if TYPE_CHECKING:
    from .core import AnchoryDepot, AnchoryResolution


REGISTRY_TOUCH_INTERVAL = timedelta(minutes=5)


def registry_path() -> Path:
    override = os.environ.get("TARAV_ANCHORY_REGISTRY")
    if override:
        return Path(override).expanduser()
    return Path("~/.tarav/anchory/registry.json").expanduser()


def global_depot_root() -> Path:
    override = os.environ.get("TARAV_ANCHORY_GLOBAL_DEPOT")
    if override:
        return Path(override).expanduser()
    return Path("~/.tarav/anchory/depot").expanduser()


def read_registry() -> dict[str, object]:
    path = registry_path()
    if not path.is_file():
        return {"depots": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"depots": []}
    if not isinstance(payload, dict) or not isinstance(payload.get("depots"), list):
        return {"depots": []}
    return payload


def record_depot_touch(depot: "AnchoryDepot") -> bool:
    """Best-effort idempotent registration; return whether the file changed."""
    try:
        namespaces: dict[str, object] = {}
        for namespace in depot.namespaces():
            try:
                meta = depot.namespace_meta(namespace)
            except Exception:
                meta = None
            entry: dict[str, object] = {}
            if isinstance(meta, dict) and isinstance(meta.get("prefix"), str):
                entry["prefix"] = meta["prefix"]
            namespaces[namespace] = entry
        registry = read_registry()
        original_depots = registry["depots"]
        live_depots = [
            entry for entry in original_depots if _entry_has_live_root(entry)
        ]
        depot_root = str(depot.root)
        existing = next(
            (
                entry
                for entry in live_depots
                if isinstance(entry, dict) and entry.get("root") == depot_root
            ),
            None,
        )
        pruned = len(live_depots) != len(original_depots)
        if (
            depot.root.is_dir()
            and isinstance(existing, dict)
            and existing.get("namespaces") == namespaces
            and _entry_was_touched_recently(existing)
            and not pruned
        ):
            return False

        depots = [
            entry
            for entry in live_depots
            if isinstance(entry, dict) and entry.get("root") != depot_root
        ]
        if depot.root.is_dir():
            depots.append(
                {
                    "root": depot_root,
                    "namespaces": namespaces,
                    "last_touched": datetime.now(timezone.utc).isoformat(),
                }
            )
        depots.sort(key=lambda entry: str(entry.get("root", "")))
        _write_registry_atomic({"depots": depots})
        return True
    except Exception:
        return False


def prune_dead_registry_entries() -> int:
    """Best-effort removal of registrations whose depot roots disappeared."""
    try:
        registry = read_registry()
        original = registry["depots"]
        live = [entry for entry in original if _entry_has_live_root(entry)]
        removed = len(original) - len(live)
        if removed:
            _write_registry_atomic({"depots": live})
        return removed
    except Exception:
        return 0


def discover_resolve(
    anchor: str, *, cwd: Path | str | None = None
) -> tuple["AnchoryResolution", Path] | None:
    """Resolve an anchor with no prior depot knowledge (`Pwd.Upward.Search`).

    Searches registered depots ordered by proximity to `cwd` (deepest shared
    path first), filtered by namespace prefix when the anchor carries one,
    then the global depot.
    """
    from .core import AnchoryDepot

    working = Path(cwd).expanduser() if cwd is not None else Path.cwd()
    working = working.resolve()
    ns_letter = anchor[0] if anchor and anchor[0].isalpha() else None

    prune_dead_registry_entries()
    candidates: list[tuple[int, Path]] = []
    for entry in read_registry()["depots"]:
        if not isinstance(entry, dict):
            continue
        root_text = entry.get("root")
        if not isinstance(root_text, str):
            continue
        root = Path(root_text)
        if not root.is_dir():
            continue
        namespaces = entry.get("namespaces")
        if ns_letter is not None and isinstance(namespaces, dict) and namespaces:
            prefixes = {
                meta.get("prefix")
                for meta in namespaces.values()
                if isinstance(meta, dict)
            }
            has_unprefixed = any(
                not isinstance(meta, dict) or "prefix" not in meta
                for meta in namespaces.values()
            )
            if ns_letter not in prefixes and not has_unprefixed:
                continue
        try:
            common = Path(os.path.commonpath([working, root]))
        except ValueError:
            continue
        candidates.append((len(common.parts), root))

    candidates.sort(key=lambda item: (-item[0], str(item[1])))
    seen: set[Path] = set()
    for _score, root in candidates:
        if root in seen:
            continue
        seen.add(root)
        resolution = AnchoryDepot(root).resolve(anchor)
        if resolution is not None:
            return resolution, root

    global_root = global_depot_root()
    if global_root not in seen and global_root.is_dir():
        resolution = AnchoryDepot(global_root).resolve(anchor)
        if resolution is not None:
            return resolution, global_root
    return None


def _entry_has_live_root(entry: object) -> bool:
    if not isinstance(entry, dict):
        return False
    root = entry.get("root")
    return isinstance(root, str) and Path(root).is_dir()


def _entry_was_touched_recently(entry: dict[str, object]) -> bool:
    touched = entry.get("last_touched")
    if not isinstance(touched, str):
        return False
    try:
        timestamp = datetime.fromisoformat(touched)
    except ValueError:
        return False
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - timestamp < REGISTRY_TOUCH_INTERVAL


def _write_registry_atomic(payload: dict[str, object]) -> None:
    atomic_write_json(registry_path(), payload)


__all__ = [
    "discover_resolve",
    "global_depot_root",
    "prune_dead_registry_entries",
    "read_registry",
    "record_depot_touch",
    "registry_path",
]
