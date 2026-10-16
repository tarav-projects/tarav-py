"""Checks of the chatlas-context annotation workflow over files, without the store.

The marker convention is this workflow's: what a provisional marker looks
like in each language and when one is active. Whoever has surfaces to
watch, a Wiki for its notes among them, includes a check from here.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l1.breadcrumbs import BreadcrumbError
from tarav.l1.breadcrumbs.identity import BREADCRUMBS_WORKFLOW_SHIP
from tarav.l1.breadcrumbs.surfaces import infer_surface_language
from tarav.l1.checks import Check, CheckPOI, CheckResult

from .workflow import provisional_markers


class SurfaceWithUnsubmittedMarkers(CheckPOI):
    """A surface carries active `tarav.context` markers that were never submitted as Breadcrumbs.

    `sessions` in its details counts the markers by the session alias they
    name; each alias is declared in the surface's `tarav.sessions` block.
    """

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("568afde8-7cdd-4549-b4e0-5edf7baa3c6c"),
                          name="Tarav.Breadcrumbs.ChatlasContext.SurfaceWithUnsubmittedMarkers",
                          workflow=BREADCRUMBS_WORKFLOW_SHIP)


class UnsubmittedMarkersCheck(Check):
    """Find the surfaces under a folder that carry active, unsubmitted `tarav.context` markers.

    It reads the files with this workflow's own parser, so a marker quoted in
    a code block is not one. It consults neither the Breadcrumb store nor
    Chatlas: whether a marker can be submitted is for the audit to say.
    """

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("041ef42f-f251-421e-a016-f842b1b61e8a"),
                          name="Tarav.Breadcrumbs.ChatlasContext.UnsubmittedMarkers",
                          workflow=BREADCRUMBS_WORKFLOW_SHIP)

    def __init__(self, folder: Path, *, project: str, root: Path,
                 pattern: str = "*.md") -> None:
        """`project` is the id of the Project the folder belongs to, and `root` its root:
        a surface is named by its path from there.
        """
        super().__init__()
        self.folder = Path(folder)
        self.project = project
        self.root = Path(root)
        self.pattern = pattern

    def _run(self) -> CheckResult:
        pois = []
        for surface in sorted(self.folder.rglob(self.pattern)):
            text = surface.read_text(encoding="utf-8", errors="replace")
            if "tarav.context" not in text:
                continue  # nothing to parse
            try:
                markers = provisional_markers(text, infer_surface_language(surface))
            except BreadcrumbError:
                continue  # a file of a language this workflow has no convention for
            if markers:
                relative = surface.relative_to(self.root).as_posix()
                pois.append(SurfaceWithUnsubmittedMarkers(
                    self, f"{relative}: {len(markers)} unsubmitted markers",
                    # a path from the Project's root, with the Project: one place, one situation
                    situation={"project": self.project, "surface": relative},
                    details={"sessions": dict(sorted(Counter(
                        marker.alias for marker in markers).items()))}))
        return CheckResult(self, status="completed", pois=pois)


__all__ = ["SurfaceWithUnsubmittedMarkers", "UnsubmittedMarkersCheck"]
