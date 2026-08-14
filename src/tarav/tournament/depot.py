# $kw: ^tournament-depot --from Tournament.Depot --note [DC] the depot resolves to a canonical global location by default and accepts an explicit root --supp ^c20260806-26u ^<anchor-on-landing>
"""Where a tournament keeps its frozen definitions and its accumulated records.

One rooted directory. ``definitions/<tournament-id>/`` holds the snapshot a
tournament executes, ``records/<tournament-id>/`` is the Bloberia namespace
holding that tournament's record and every verdict, and ``tickets/`` is the
mutable submission staging. The split is the depot's; Bloberia owns only what is
under ``records/``.

``components/`` is the fourth and the only one that is not per-tournament: it is
the depot-wide `Match.Component.Registry` holding each distinct part every run
was rendered from, once. Dedup across tournaments is free, so it is allowed.
"""

from __future__ import annotations

import os
from pathlib import Path

DEPOT_ENV_VAR = "TARAV_TOURNAMENT_DEPOT"
DEFAULT_DEPOT_RELATIVE = Path(".tarav") / "tournament"

DEFINITIONS_DIRNAME = "definitions"


def resolve_depot_root(root: Path | str | None) -> Path:
    """Resolve the depot root: explicit argument, then environment, then default.

    Matches the ``~/.tarav/wayfinder`` and ``~/.tarav/activity`` precedent,
    so a caller that has no opinion still gets one durable place.
    """
    if root is not None:
        return Path(root).expanduser().resolve()
    override = os.environ.get(DEPOT_ENV_VAR)
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / DEFAULT_DEPOT_RELATIVE
