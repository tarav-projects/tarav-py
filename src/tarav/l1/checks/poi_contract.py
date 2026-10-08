"""Checks that keep every POI explainable: declared guidance and a working context path."""

from __future__ import annotations

import shlex
import tempfile
from pathlib import Path

from tarav.l0.kernel import TaravClass, TypeShip, entity
from tarav.l1.context.query import ContextQueryService, IdentityContextQuery
from tarav.l1.poi import IdentifiedPOI
from tarav.l1.poi.reporting import (
    REPORTED_POI_VIEW, ReportedPOIContext, ReportedPOIResolver, ReportedPOIStore, guidance_of,
)

from . import CHECKS_WORKFLOW_SHIP, Check, CheckPOI, CheckResult, CheckRun, render_check_run

_READ = ("tarav-md/notes/wiki/poi-system.md, section 'Reported POIs and their context'.",
         "tarav.l1.poi.reporting: guidance_of() and context_instruction().")


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


class POIGuidanceMissingPOI(CheckPOI):
    """A POI Type that tells its reader neither what to read nor what may be done."""

    read_first = _READ
    may_do = ("Set `read_first` and `may_do` on the named POI class.",
              "Leaving it is acceptable: this is a reminder, not a defect in a run.")

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("2b6d8f40-7a13-4c95-b8e2-5f0a9c3d1e67"),
                          name="Tarav.Checks.POIGuidanceMissing", workflow=CHECKS_WORKFLOW_SHIP)


# tarav.breadcrumb ab1ededded3d322d81192b4aa9c3984d58a6ee91b9eae863171795b5b8e2a5c3
class POIGuidanceCheck(Check):
    """Every loaded POI Type defined under a folder declares guidance for its readers."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("9c1e4a72-0d58-4b36-a7f9-3e6b2d8c5a10"),
                          name="Tarav.Checks.POIGuidance", workflow=CHECKS_WORKFLOW_SHIP)

    def __init__(self, root: Path) -> None:
        super().__init__()
        self.root = Path(root)

    def _run(self) -> CheckResult:
        pois = []
        for poi_type in _leaf_poi_types():
            if not defined_under(poi_type, self.root):
                continue
            guidance = guidance_of(poi_type)
            if guidance["read_first"] or guidance["may_do"]:
                continue
            name = entity(poi_type).name
            pois.append(POIGuidanceMissingPOI(
                self, "undeclared", f"{name} declares nothing to read or do",
                situation={"poi_type": name},
                details={"poi_type": name, **{key: poi_type.help().get(key)
                                               for key in ("class", "source_path", "source_line")}}))
        return CheckResult(self, status="completed", pois=pois)


class POIContextRoundTripPOI(CheckPOI):
    """The context command a check report advertises does not lead to a POI's context."""

    read_first = _READ
    may_do = ("Repair the report header, the reported-POI resolver or its view in tarav-py.",
              "Raise it to the User: agents are being sent to a command that does not answer.")

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("e5a07c39-8b24-4f61-9d03-1c7f6a2b4d98"),
                          name="Tarav.Checks.POIContextRoundTripPOI",
                          workflow=CHECKS_WORKFLOW_SHIP)


class POIContextRoundTripCheck(Check):
    """Render a report, take the command its header advertises, and follow it."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("7d3f9b61-2e48-4a05-8c17-6a0e5d1f3b29"),
                          name="Tarav.Checks.POIContextRoundTrip", workflow=CHECKS_WORKFLOW_SHIP)

    def _finding(self, code: str, message: str, **details) -> CheckResult:
        return CheckResult(self, status="completed", pois=[POIContextRoundTripPOI(
            self, code, message, situation={"code": code}, details=details)])

    def _run(self) -> CheckResult:
        sample = CheckPOI(self, "sample", "Round-trip sample",
                          situation={"sample": "poi-context-round-trip"})
        run = CheckRun()
        run.add(CheckResult(self, status="completed", pois=[sample]))
        rendered = render_check_run(run.report(by="identity"))
        example = next((line.strip()[len("e.g. "):] for line in rendered.splitlines()
                        if line.strip().startswith("e.g. tarav context ")), None)
        if example is None:
            return self._finding("no-instruction",
                                 "The check report advertises no context command",
                                 rendered=rendered)
        words = shlex.split(example)
        options = dict(zip(words[2::2], words[3::2]))
        if "--id" not in options:
            return self._finding("unparsable", "The advertised command has no --id",
                                 example=example)
        with tempfile.TemporaryDirectory(prefix="tarav-poi-round-trip-") as folder:
            store = ReportedPOIStore(Path(folder))
            store.retain(run.pois(), project={"id": "round-trip", "name": "round-trip"})
            service = ContextQueryService()
            service.register_resolver("reported-poi", ReportedPOIResolver(store))
            service.register_view(REPORTED_POI_VIEW, ReportedPOIContext)
            try:
                answer = service.open(IdentityContextQuery(options["--id"],
                                                           view=options.get("--view")))
                opened = [entry.open() for entry in answer.target.ls()] \
                    if answer.subject is not None else []
            except Exception as exc:
                return self._finding("unresolved", "The advertised command failed",
                                     example=example, error=f"{type(exc).__name__}: {exc}")
        if answer.subject is None or answer.subject.identity != sample.identity:
            return self._finding("unresolved",
                                 "The advertised command does not resolve the reported POI",
                                 example=example)
        if not opened:
            return self._finding("empty-view", "The advertised view has no entries",
                                 example=example)
        return CheckResult(self, status="completed")


__all__ = [
    "POIContextRoundTripCheck",
    "POIContextRoundTripPOI",
    "POIGuidanceCheck",
    "POIGuidanceMissingPOI",
    "defined_under",
]
