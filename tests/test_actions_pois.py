"""POI actions, tried on the actions test workflow."""

from __future__ import annotations

import pytest

from tarav.l1.actions import CLOSED, RUNNING
from tarav.l1.actions.pois import GONE, POIActionClosed, action_id
from tarav.l1.actions.blessing import BLESSED, BlessingInput
from tarav.l2.tests.actions import TestMarkerPOI, update_workspace, workspace_pois
from tarav.l3.runtime import create_runtime

from test_actions_workflow import Stores, registry  # noqa: F401  (a fixture)
from test_project_dev import _project


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


# tarav.breadcrumb 17424fc546c8fbd42d1b63e81b7ec777bcb8c45e6dbac5d23e723543fed44498
@pytest.mark.usefixtures("registry")
def test_a_projects_test_fixtures_open_real_actions_on_the_live_path(tmp_path):
    import shutil

    from tarav.l2.project.dev import DocsProject
    from tarav.l2.tests.actions import FIXTURES, TestFixturesSuite

    root = tmp_path / "docs"
    root.mkdir()
    project = _project(root, DocsProject)

    def fixture_suites(status):
        return [suite for suite in status.checks.suites() if isinstance(suite, TestFixturesSuite)]

    def test_actions(state):
        return [run for run in project.actions.list(state=state)
                if run.data["event"]["poi"]["type"] == "Tarav.Test.Actions.MarkerPOI"]

    # without the folder there is no fixtures suite, and no test action
    assert fixture_suites(project.status()) == [] and test_actions(RUNNING) == []

    folder = root / FIXTURES
    folder.mkdir()
    (folder / ".gitignore").write_text("*\n")
    (folder / "hall.txt").write_text("TODO switch the hall lamp off\n")
    (folder / "notes.txt").write_text("nothing to do\n")
    status = project.status()
    assert len(fixture_suites(status)) == 1 and status.actions["opened"] == 1
    [run] = test_actions(RUNNING)
    assert run.data["event"]["poi"]["type"] == "Tarav.Test.Actions.MarkerPOI"
    assert run.data["event"]["poi"]["situation"] == {
        "file": "hall.txt", "lines": ["TODO switch the hall lamp off"]}
    assert run.data["event"]["suites"] == [{"type": "Tarav.Test.Actions.Fixtures",
                                            "key": FIXTURES}]
    assert run.data["project"]["root"] == str(project.root)

    # the folder goes: the suite is no longer yielded, and the action closes as gone
    shutil.rmtree(folder)
    assert project.status().actions["gone"] == 1
    [closed] = test_actions(CLOSED)
    assert (closed.id, closed.exit) == (run.id, GONE)


@pytest.mark.usefixtures("registry")
def test_an_action_and_its_poi_open_the_same_object_group(tmp_path):
    from tarav.l1.context.groups import ObjectGroup
    from tarav.l1.context.query import IdentityContextQuery
    from tarav.l2.project.dev import DocsProject
    from tarav.l2.tests.actions import FIXTURES
    from tarav.l3.cli.cli import context_queries

    root = tmp_path / "docs"
    (root / FIXTURES).mkdir(parents=True)
    project = _project(root, DocsProject)
    hall = root / FIXTURES / "hall.txt"
    hall.write_text("TODO switch the hall lamp off\n")
    project.status()
    hall.write_text("done\n")
    project.status()  # closes as gone
    hall.write_text("TODO switch the hall lamp off\n")
    project.status()  # the same situation again: it reopens
    [run] = [run for run in project.actions.list(state=RUNNING)
             if run.data["event"]["poi"]["type"] == "Tarav.Test.Actions.MarkerPOI"]
    [poi] = [poi for poi in workspace_pois(root / FIXTURES) if isinstance(poi, TestMarkerPOI)]

    def rows(view):
        return [(entry.name, entry.open().records.to_record()) for entry in view.ls()]

    member = "Tarav.Context.Group.Member"
    expected = [
        ("situation", {"type": member, "role": "situation",
                       "value": {"file": "hall.txt", "lines": ["TODO switch the hall lamp off"]}}),
        ("suite", {"type": member, "role": "suite", "member_type": "Tarav.Test.Actions.Fixtures",
                   "key": FIXTURES}),
        ("check", {"type": member, "role": "check",
                   "member_type": "Tarav.Test.Actions.MarkerCheck"}),
        ("poi", {"type": member, "role": "poi", "member_type": "Tarav.Test.Actions.MarkerPOI",
                 "id": poi.identity}),
        ("action", {"type": member, "role": "action",
                    "member_type": "Tarav.Actions.POI.Resolution", "id": str(run.id)}),
        ("closing", {"type": member, "role": "closing", "member_type": "Tarav.Actions.POI.Gone",
                     "key": run.data["tape"][-2]["at"]}),
    ]
    assert rows(run.context(views=(ObjectGroup,))) == expected
    # a POI just raised, not loaded from the action, reaches the same group
    assert rows(poi.context(views=(ObjectGroup,))) == expected
    answer = context_queries(create_runtime()).open(
        IdentityContextQuery(str(run.id), views=("object-group",), path=["closing"]))
    assert answer.target.records.to_record() == expected[-1][1]

