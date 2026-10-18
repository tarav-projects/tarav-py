"""General development Project Types and their first checks."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
import uuid

from tarav.l0.testing import DEFAULT_TEST_PROJECT_ID, write_project_marker

from tarav.l2.project.dev import (
    DocsProject,
    PythonPackageProject,
    PyTestCheck,
    PyTestFileSuite,
    PyTestSuite,
    SkillLoadCheck,
    TestFailurePOI,
)
from tarav.l2.breadcrumb_workflows.chatlas_context.checks import UnsubmittedMarkersCheck
from tarav.l2.project import Project
from tarav.l2.project.models import ProjectModels


def _project(root: Path, project_type):
    (root / ".tarav").mkdir(parents=True, exist_ok=True)
    (root / ".tarav/project.json").write_text(json.dumps(
        {"project_id": str(uuid.uuid4()), "created_at": "2026-10-15T00:00:00Z"}))
    return project_type.from_path(root)


# tarav.breadcrumb b5384665de6e
def test_project_capabilities_have_explicit_paths(tmp_path: Path) -> None:
    project = _project(tmp_path, Project)

    assert project.docs.wiki.daily(date(2026, 10, 7)).path.name == "2026-10-07.md"
    assert isinstance(project.models, ProjectModels)
    assert project.models.ls() == ()
    assert not hasattr(project, "wiki")


# tarav.breadcrumb f06862ef7574
def test_a_failing_test_is_a_poi_named_by_its_test(tmp_path: Path) -> None:
    (tmp_path / "test_sample.py").write_text(
        "def test_passes():\n    assert True\n\n"
        "def test_fails():\n    assert 1 == 2, 'one is not two'\n")
    project = _project(tmp_path, PythonPackageProject)
    run = project.checks.run()
    result = next(item for item in run.results if isinstance(item.check, PyTestCheck))
    assert result.status == "completed"
    assert [poi.situation["test"] for poi in result.pois()] == ["test_sample.py::test_fails"]
    assert isinstance(result.pois()[0], TestFailurePOI)
    assert "1 failed, 1 passed" in result.data["summary"]


# tarav.breadcrumb 84c55d0bb2d4
def test_pytest_runs_once_and_each_test_file_is_a_suite_of_its_own(tmp_path: Path) -> None:
    (tmp_path / "test_one.py").write_text(
        "def test_passes():\n    assert True\n\n"
        "def test_fails():\n    assert 1 == 2\n")
    (tmp_path / "test_two.py").write_text("def test_fine():\n    assert True\n")
    write_project_marker(tmp_path)
    suite = PyTestSuite(tmp_path).run()
    assert suite.identity == {"type": "Tarav.Project.Dev.PyTest.Suite", "key": None}
    assert not PyTestSuite.routine
    files = suite.suites()
    assert [type(found) for found in files] == [PyTestFileSuite, PyTestFileSuite]
    assert [found.key for found in files] == ["test_one.py", "test_two.py"]
    assert [len(found.pois()) for found in files] == [1, 0]
    assert suite.complete and "1 failed, 2 passed" in suite.summary_line
    chain, result = next(iter(suite.walk()))
    assert [item["key"] for item in chain] == [None, "test_one.py"]
    assert result.pois()[0].situation == {"project": DEFAULT_TEST_PROJECT_ID,
                                         "test": "test_one.py::test_fails"}

    # a file that is gone is no longer yielded by a run that went to its end
    (tmp_path / "test_one.py").unlink()
    again = PyTestSuite(tmp_path).run()
    assert [found.key for found in again.suites()] == ["test_two.py"] and again.conclusive

    # the check of one file can also run by itself
    alone = PyTestCheck(tmp_path, "test_two.py").run()
    assert (alone.status, alone.pois()) == ("completed", ())


def test_a_test_file_that_cannot_be_collected_is_a_poi(tmp_path: Path) -> None:
    (tmp_path / "test_broken.py").write_text("import no_such_module_anywhere\n")
    (tmp_path / "test_fine.py").write_text("def test_fine():\n    assert True\n")
    write_project_marker(tmp_path)
    suite = PyTestSuite(tmp_path).run()
    assert [found.key for found in suite.suites()] == ["test_broken.py", "test_fine.py"]
    assert [poi.situation["test"] for poi in suite.pois()] == ["test_broken.py"]
    assert "1 passed" in suite.summary_line


def test_a_suite_that_cannot_run_is_a_failed_result(tmp_path: Path) -> None:
    suite = PyTestSuite(tmp_path, arguments=("--no-such-option",)).run()
    assert [result.status for result in suite.results] == ["failed"]
    assert not suite.conclusive and suite.suites() == []


def test_docs_report_unsubmitted_markers_and_skills_that_do_not_load(tmp_path: Path) -> None:
    (tmp_path / "notes/wiki/daily").mkdir(parents=True)
    (tmp_path / "notes/wiki/topic.md").write_text(
        "Text.\n<!-- tarav.breadcrumb " + "a" * 64 + " -->\n")
    (tmp_path / "notes/wiki/daily/today.md").write_text(
        "Text.\n<!-- tarav.context 5a029cbf:0123456789abcdef -->\n")
    (tmp_path / "skills/broken/.skw").mkdir(parents=True)
    (tmp_path / "skills/broken/.skw/main.json").write_text("{}")
    project = _project(tmp_path, DocsProject)
    run = project.checks.run()
    domain_results = [result for result in run.results
                      if isinstance(result.check, (SkillLoadCheck, UnsubmittedMarkersCheck))]
    assert [type(result.check) for result in domain_results] == [SkillLoadCheck,
                                                                 UnsubmittedMarkersCheck]
    assert domain_results[0].status == "incomplete"
    [poi] = domain_results[1].pois()
    assert poi.situation == {"project": str(project.id),
                             "surface": "notes/wiki/daily/today.md"}
    assert poi.details == {"sessions": {"5a029cbf": 1}}
    # the convention is the Breadcrumbs workflow's: a marker quoted in a code block is not one
    (tmp_path / "notes/wiki/quoted.md").write_text(
        "An example:\n\n```\n<!-- tarav.context 5a029cbf:0123456789abcdef -->\n```\n")
    [again] = [result for result in project.checks.run().results
               if isinstance(result.check, UnsubmittedMarkersCheck)]
    assert [found.situation["surface"] for found in again.pois()] == [
        "notes/wiki/daily/today.md"]
