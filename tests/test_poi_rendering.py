"""Named POI presentations preserve a path from a line to its context."""

import json

import pytest

from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l1.checks import Check, CheckPOI, CheckResult, CheckRun
from tarav.l1.poi import POICollector
from tarav.l1.poi.rendering import (
    DEFAULT_POI_RENDERER, JSON_LINES_POI_RENDERER, POIRenderError,
    POISelection, renderer, renderers,
)


class SampleCheck(Check):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("eb7fa1fa-6a5a-4842-b804-b311d7fc31d1"),
                          name="Tarav.Test.POIRenderCheck")

    def _run(self):
        return CheckResult(self, status="completed", pois=[
            SamplePOI(self, "Readable problem", situation={"path": "example.py"})])


class SamplePOI(CheckPOI):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("20fa2d46-5c77-4575-a285-8d7f68685861"),
                          name="Tarav.Test.POIRenderPOI")


# tarav.breadcrumb 7f3e537008bba2d8b00cca281777ea6643149f0b16f3dbf4c11e2e27c384cf13
def test_every_named_renderer_keeps_a_resolvable_poi_and_context_route():
    run = CheckRun()
    run.add(SampleCheck().run())
    poi = run.pois()[0]
    selection = POISelection.from_check_report(run.report(by="identity", detail=True))
    assert {item.name for item in renderers()} >= {
        DEFAULT_POI_RENDERER, JSON_LINES_POI_RENDERER}
    for named in renderers():
        for level in named.levels:
            content = named.render(selection, level=level)
            assert poi.identity[:12] in content
            assert "tarav context --id" in content
    lines = renderer(JSON_LINES_POI_RENDERER).render(selection, level="record").splitlines()
    assert [json.loads(line)["kind"] for line in lines] == ["poi-selection", "poi"]


def test_collector_selection_is_rendered_without_reselecting():
    poi = SampleCheck().run().pois()[0]
    collector = POICollector()
    collector.emit(poi)
    selected = POISelection.from_collector_report(collector.report(limit=1), title="sample")
    assert "Readable problem" in renderer().render(selected)
    assert poi.identity[:12] in renderer().render(selected)
    with pytest.raises(POIRenderError, match="Unknown"):
        renderer("missing")
