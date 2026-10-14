"""POI actions, tried on the actions test workflow."""

from __future__ import annotations

import pytest

from tarav.l1.actions import CLOSED, RUNNING
from tarav.l1.actions.pois import GONE, POIActionClosed, action_id
from tarav.l1.actions.blessing import BLESSED, BlessingInput
from tarav.l2.tests.actions import TestMarkerPOI, update_workspace, workspace_pois
from tarav.l3.runtime import create_runtime

from test_actions_workflow import Stores


@pytest.fixture
def stores(tmp_path):
    return Stores(tmp_path / "records", create_runtime().records)


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "a.txt").write_text("first line\nTODO write the rest\n", encoding="utf-8")
    (root / "b.txt").write_text("TODO one\nTODO two\n", encoding="utf-8")
    (root / "c.txt").write_text("nothing to see\n", encoding="utf-8")
    return root


def test_the_workspace_raises_one_poi_per_marked_file(workspace):
    # tarav.breadcrumb 88c6596bc475015b69873c1dd8c9115b2e9dfb77fcdc4cd4f2daccaaa2a13b40
    assert [type(poi) for poi in workspace_pois(workspace)] == [TestMarkerPOI, TestMarkerPOI]


def test_fixing_a_file_closes_its_action_and_blessing_closes_the_other(stores, workspace):
    # tarav.breadcrumb c7523381ecd002e3baef2446d9bef9e6b668aa5f6c2df15a39cce253908c361f
    a, b = workspace_pois(workspace)
    first = update_workspace(workspace, stores.runs)
    assert (first["opened"], first["actions"]) == (2, 2)
    assert stores.pois.of(a).data["project"] == {
        "id": "test-workspace", "name": "test-workspace", "root": str(workspace)}

    (workspace / "a.txt").write_text("first line\nthe rest\n", encoding="utf-8")
    fixed = update_workspace(workspace, stores.runs)
    assert fixed["gone"] == 1 and [type(item) for item in fixed["signals"]] == [POIActionClosed]
    assert (stores.pois.of(a).state, stores.pois.of(a).exit) == (CLOSED, GONE)
    assert stores.pois.of(b).state == RUNNING

    reason = stores.contexts.put(BlessingInput.new(reason="Both are tracked in the plan."))
    stores.runner.close(str(action_id(b)), reason, exit=BLESSED)
    after = update_workspace(workspace, stores.runs)
    assert (after["opened"], after["reopened"], after["gone"]) == (0, 0, 0)
    assert {run.exit for run in stores.runs.list(state=CLOSED)} == {GONE, BLESSED}
    assert stores.runs.list(state=RUNNING) == []
