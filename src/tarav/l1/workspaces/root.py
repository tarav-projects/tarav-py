"""Locate the independent Workspace depot under the Tarav data root."""

from __future__ import annotations

import os
from pathlib import Path

# tarav.breadcrumb 551c11edc0622147571a79851111de7c07e57fdfb759ea2f754e536299a45aad
WORKSPACES_ENV_VAR = "TARAV_WORKSPACES_ROOT"
DEFAULT_WORKSPACES_RELATIVE = Path("Documents") / "tarav" / "workspaces"

def resolve_workspaces_root(root: Path | str | None) -> Path:
    """Explicit argument, then environment, then the canonical global default."""
    if root is not None:
        return Path(root).expanduser().resolve()
    override = os.environ.get(WORKSPACES_ENV_VAR)
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / DEFAULT_WORKSPACES_RELATIVE
