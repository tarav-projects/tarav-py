"""Which Projects a Project can see: itself and the Projects it lists as children."""

from __future__ import annotations

from pathlib import Path

from tarav.l0._core.errors import CliError
from tarav.l0.project import require_agentos_project


def project_scope(root: str | Path) -> tuple[str, ...]:
    """The root of a Project and of every Project below it that it lists, at any depth.

    A Project sees what its listed children hold; it does not own it. Only
    the marker is read, so this works for a child whose Type does not load
    here. A folder without a marker has only itself in scope.
    """
    origin = Path(root).expanduser().resolve()
    found = list(dict.fromkeys((str(root), str(origin))))  # as given, and as it resolves
    try:
        children = require_agentos_project(origin).project_json.get("children") or ()
    except (CliError, OSError, ValueError):
        return tuple(found)
    for child in children:
        if not isinstance(child, str):
            continue
        path = (origin / child).resolve()
        try:
            listed = require_agentos_project(path).root.resolve() == path
        except (CliError, OSError, ValueError):
            listed = False
        if listed and path != origin and path.is_relative_to(origin):
            found.extend(item for item in project_scope(path) if item not in found)
    return tuple(found)


__all__ = ["project_scope"]
