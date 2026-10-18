"""A check that keeps every POI explainable: each Type renders a meaningful line."""

from __future__ import annotations

import inspect
from pathlib import Path

from tarav.l0.kernel import TaravClass, TypeShip, entity
from tarav.l1.poi import SituationPOI, POI
from tarav.l1.poi.rendering import POISelection, renderer

from . import CHECKS_WORKFLOW_SHIP, Check, CheckPOI, CheckResult

def defined_under(cls: type, root: Path) -> bool:
    """Whether a class's source file lies under a folder, outside its tests."""
    source = cls.help().get("source_path") if hasattr(cls, "help") else None
    if not source:
        return False
    path = Path(source).resolve()
    return path.is_relative_to(Path(root).resolve()) and "tests" not in path.parts


def _leaf_poi_types(base: type = SituationPOI) -> list[type]:
    found, pending = [], [base]
    while pending:
        current = pending.pop()
        children = current.__subclasses__()
        pending.extend(children)
        if not children and current is not base:
            found.append(current)
    return sorted(set(found), key=lambda cls: entity(cls).name)


class POIRenderSummaryMissing(CheckPOI):
    """A loaded POI Type has no meaningful line summary in the default renderer."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("765c69a1-8405-4e6d-bf75-fb02985677b9"),
                          name="Tarav.Checks.POIRenderSummaryMissing",
                          workflow=CHECKS_WORKFLOW_SHIP)


# tarav.breadcrumb 048bb8a3c990
class POIRenderCoverageCheck(Check):
    """Every loaded local POI Type can contribute a meaningful rendered line."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("834bad80-907c-46e6-89af-32f75e3e435b"),
                          name="Tarav.Checks.POIRenderCoverage",
                          workflow=CHECKS_WORKFLOW_SHIP)

    def __init__(self, root: Path) -> None:
        super().__init__()
        self.root = Path(root)

    def _run(self) -> CheckResult:
        pois = []
        for poi_type in _leaf_poi_types(POI):
            if not defined_under(poi_type, self.root):
                continue
            name = entity(poi_type).name
            description = inspect.cleandoc(poi_type.__dict__.get("__doc__") or "")
            selection = POISelection(
                "collector", ({"type": name, "id": name, "summary": description},),
                1, 1,
            )
            rendered = renderer().render(selection)
            if description and description in rendered:
                continue
            pois.append(POIRenderSummaryMissing(
                self, f"{name} has no meaningful rendered line summary",
                situation={"poi_type": name},
                details={"poi_type": name, "source_path": poi_type.help().get("source_path")}))
        return CheckResult(self, status="completed", pois=pois)


__all__ = [
    "POIRenderCoverageCheck",
    "POIRenderSummaryMissing",
    "defined_under",
]
