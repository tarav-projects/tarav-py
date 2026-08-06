# $kw: ^tournament-depot --from Tournament.Depot --note [DC] the depot resolves to a canonical global location by default and accepts an explicit root --supp ^c20260806-26u ^<anchor-on-landing>
"""Where a tournament keeps its frozen definitions and its accumulated records.

One rooted directory with two children: ``definitions/<tournament-id>/`` holds
the snapshot a tournament executes, and ``records/<tournament-id>/`` is the
Bloberia namespace holding that tournament's record and every verdict. The split
is the depot's; Bloberia owns only what is under ``records/``.
"""

from __future__ import annotations

import os
from pathlib import Path

DEPOT_ENV_VAR = "AGENTOS_TOURNAMENT_DEPOT"
DEFAULT_DEPOT_RELATIVE = Path(".agentos") / "tournament"

DEFINITIONS_DIRNAME = "definitions"


def resolve_depot_root(root: Path | str | None) -> Path:
    """Resolve the depot root: explicit argument, then environment, then default.

    Matches the ``~/.agentos/wayfinder`` and ``~/.agentos/activity`` precedent,
    so a caller that has no opinion still gets one durable place.
    """
    if root is not None:
        return Path(root).expanduser().resolve()
    override = os.environ.get(DEPOT_ENV_VAR)
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / DEFAULT_DEPOT_RELATIVE
