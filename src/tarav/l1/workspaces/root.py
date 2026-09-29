# $kw: ^workspaces-root --from Run.Workspace --note [DC] workspaces live at ~/.tarav/workspaces/<date>-<slug>/, one directory per run --supp ^c20260809-87u ^<anchor-on-landing>
"""Where one-run workspaces live.

One rooted directory outside every project, holding one directory per run. The
path carries no lifetime claim: a workspace's life is decided by its `status`
and `extracted` manifest fields and the sweep that reads them, not by where it
sits.
"""

from __future__ import annotations

import os
from pathlib import Path

WORKSPACES_ENV_VAR = "TARAV_WORKSPACES_ROOT"
DEFAULT_WORKSPACES_RELATIVE = Path(".tarav") / "workspaces"

AGENTS_FILENAME = "AGENTS.md"


def resolve_workspaces_root(root: Path | str | None) -> Path:
    """Explicit argument, then environment, then the canonical global default."""
    if root is not None:
        return Path(root).expanduser().resolve()
    override = os.environ.get(WORKSPACES_ENV_VAR)
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / DEFAULT_WORKSPACES_RELATIVE
