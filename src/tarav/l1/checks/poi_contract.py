"""Checks that keep every POI explainable: a rendered line and a working context path."""

from __future__ import annotations

import inspect
import json
import shlex
import tempfile
from pathlib import Path

from tarav.l0.kernel import TaravClass, TypeShip, entity
from tarav.l1.context.query import ContextQueryService, IdentityContextQuery
from tarav.l1.poi import IdentifiedPOI, POI
from tarav.l1.poi.reporting import (
    REPORTED_POI_VIEW, ReportedPOIContext, ReportedPOIResolver, ReportedPOIStore,
)
from tarav.l1.poi.rendering import POISelection, renderers
from tarav.l1.poi.rendering import renderer

from . import CHECKS_WORKFLOW_SHIP, Check, CheckPOI, CheckResult, CheckRun

_READ = ("How reported POIs are opened is described in tarav-md/notes/wiki/poi-system.md, "
         "section 'Reported POIs and their context'.",
         "The command shown with a report is built by "
         "tarav.l1.poi.reporting.context_instruction().")


def defined_under(cls: type, root: Path) -> bool:
    """Whether a class's source file lies under a folder, outside its tests."""
    source = cls.help().get("source_path") if hasattr(cls, "help") else None
    if not source:
        return False
    path = Path(source).resolve()
    return path.is_relative_to(Path(root).resolve()) and "tests" not in path.parts


def _leaf_poi_types(base: type = IdentifiedPOI) -> list[type]:
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


# tarav.breadcrumb 048bb8a3c9906c28ad55f6c9705d200f2c6c9ff7d44078ad35ac0fa96bc7adee
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
                1, 1, example_id=name,
            )
            rendered = renderer().render(selection)
            if description and description in rendered:
                continue
            pois.append(POIRenderSummaryMissing(
                self, f"{name} has no meaningful rendered line summary",
                situation={"poi_type": name},
                details={"poi_type": name, "source_path": poi_type.help().get("source_path")}))
        return CheckResult(self, status="completed", pois=pois)


class POIContextRoundTripPOI(CheckPOI):
    """Family, never raised: a check report's advertised context command does not lead to a POI."""

    context_notes = (*_READ,
                     "It is no longer raised once the report header, the reported-POI "
                     "resolver and its view agree in tarav-py.",
                     "Its producer intends it to reach the User: agents are being sent to "
                     "a command that does not answer.")

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("e5a07c39-8b24-4f61-9d03-1c7f6a2b4d98"),
                          name="Tarav.Checks.POIContextRoundTripPOI",
                          workflow=CHECKS_WORKFLOW_SHIP)


class POIContextInstructionMissing(POIContextRoundTripPOI):
    """A rendered check report advertises no context command."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("ea4588cf-24ed-412d-81f2-40c056d96568"),
                          name="Tarav.Checks.POIContextRoundTrip.InstructionMissing", workflow=CHECKS_WORKFLOW_SHIP)


class POIContextCommandUnparsable(POIContextRoundTripPOI):
    """The context command a check report advertises names no identifier."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("1951a335-d8cf-42e9-9527-133c151e59f2"),
                          name="Tarav.Checks.POIContextRoundTrip.CommandUnparsable", workflow=CHECKS_WORKFLOW_SHIP)


class POIContextCommandUnresolved(POIContextRoundTripPOI):
    """The context command a check report advertises does not open the reported POI."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("ce077b67-644c-4d5c-bf29-2f32a87209b6"),
                          name="Tarav.Checks.POIContextRoundTrip.CommandUnresolved", workflow=CHECKS_WORKFLOW_SHIP)


class POIContextViewEmpty(POIContextRoundTripPOI):
    """The context view a check report advertises has no entries."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("5b96101e-f649-45b5-9b33-34ad483ecfe0"),
                          name="Tarav.Checks.POIContextRoundTrip.ViewEmpty", workflow=CHECKS_WORKFLOW_SHIP)


class POIContextRoundTripCheck(Check):
    """Render a report, take the command its header advertises, and follow it."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("7d3f9b61-2e48-4a05-8c17-6a0e5d1f3b29"),
                          name="Tarav.Checks.POIContextRoundTrip", workflow=CHECKS_WORKFLOW_SHIP)

    def _poi(self, case: type[CheckPOI], message: str, **details) -> CheckResult:
        return CheckResult(self, status="completed", pois=[case(
            self, message, situation={"surface": "check-report",
                                      "renderer": details.get("renderer")}, details=details)])

    def _run(self) -> CheckResult:
        sample = CheckPOI(self, "Round-trip sample",
                          situation={"sample": "poi-context-round-trip"})
        run = CheckRun()
        run.add(CheckResult(self, status="completed", pois=[sample]))
        with tempfile.TemporaryDirectory(prefix="tarav-poi-round-trip-") as folder:
            store = ReportedPOIStore(Path(folder))
            store.retain(run.pois(), project={"id": "round-trip", "name": "round-trip"})
            service = ContextQueryService()
            service.register_resolver("reported-poi", ReportedPOIResolver(store))
            service.register_view(REPORTED_POI_VIEW, ReportedPOIContext)
            selection = POISelection.from_check_report(run.report(by="identity"))
            for selected_renderer in renderers():
                rendered = selected_renderer.render(selection)
                try:
                    lines = (json.loads(rendered.splitlines()[0])["context_instruction"]
                             if selected_renderer.media_type == "application/x-ndjson"
                             else rendered.splitlines())
                except (IndexError, KeyError, TypeError, ValueError) as exc:
                    return self._poi(POIContextCommandUnparsable,
                                     "The POI renderer returned invalid context instructions",
                                     renderer=selected_renderer.name, error=str(exc))
                example = next((line.strip()[len("e.g. "):] for line in lines
                                if line.strip().startswith("e.g. tarav context ")), None)
                if example is None:
                    return self._poi(POIContextInstructionMissing,
                                         "The POI renderer advertises no context command",
                                         renderer=selected_renderer.name, rendered=rendered)
                words = shlex.split(example)
                options = dict(zip(words[2::2], words[3::2]))
                if "--id" not in options:
                    return self._poi(POIContextCommandUnparsable,
                                         "The advertised command has no --id",
                                         renderer=selected_renderer.name, example=example)
                try:
                    answer = service.open(IdentityContextQuery(options["--id"],
                                                               view=options.get("--view")))
                    opened = [entry.open() for entry in answer.target.ls()] \
                        if answer.subject is not None else []
                except Exception as exc:
                    return self._poi(POIContextCommandUnresolved,
                                         "The advertised command failed",
                                         renderer=selected_renderer.name, example=example,
                                         error=f"{type(exc).__name__}: {exc}")
                if answer.subject is None or answer.subject.identity != sample.identity:
                    return self._poi(POIContextCommandUnresolved,
                                         "The advertised command does not resolve the reported POI",
                                         renderer=selected_renderer.name, example=example)
                if not opened:
                    return self._poi(POIContextViewEmpty,
                                         "The advertised view has no entries",
                                         renderer=selected_renderer.name, example=example)
        return CheckResult(self, status="completed")


__all__ = [
    "POIContextCommandUnparsable",
    "POIContextCommandUnresolved",
    "POIContextInstructionMissing",
    "POIContextRoundTripCheck",
    "POIContextRoundTripPOI",
    "POIContextViewEmpty",
    "POIRenderCoverageCheck",
    "POIRenderSummaryMissing",
    "defined_under",
]
