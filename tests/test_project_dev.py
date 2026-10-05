"""General development Project Types and their first checks."""

from __future__ import annotations

import json
from pathlib import Path
import uuid

from tarav.l2.project.dev import (
    DocsProject,
    ProvisionalMarkersCheck,
    PythonPackageProject,
    SkillLoadCheck,
    TestFailurePOI,
    TestSuiteCheck,
)


def _project(root: Path, project_type):
    (root / ".tarav").mkdir(parents=True, exist_ok=True)
    (root / ".tarav/project.json").write_text(json.dumps(
        {"class": "agentos.project", "schema_version": 1, "project_id": str(uuid.uuid4())}))
    return project_type.from_path(root)


def test_a_failing_test_is_a_poi_named_by_its_test(tmp_path: Path) -> None:
    (tmp_path / "test_sample.py").write_text(
        "def test_passes():\n    assert True\n\n"
        "def test_fails():\n    assert 1 == 2, 'one is not two'\n")
    project = _project(tmp_path, PythonPackageProject)
    run = project.checks().run()
    [result] = run.results
    assert result.status == "completed"
    assert [poi.situation["test"] for poi in result.pois()] == ["test_sample.py::test_fails"]
    assert isinstance(result.pois()[0], TestFailurePOI)
    assert "1 failed, 1 passed" in result.data["summary"]


def test_a_suite_that_cannot_run_is_a_failed_result(tmp_path: Path) -> None:
    result = TestSuiteCheck(tmp_path, arguments=("--no-such-option",)).run()
    assert result.status == "failed"


def test_docs_report_unsubmitted_markers_and_skills_that_do_not_load(tmp_path: Path) -> None:
    (tmp_path / "notes/wiki/daily").mkdir(parents=True)
    (tmp_path / "notes/wiki/topic.md").write_text(
        "Text.\n<!-- tarav.breadcrumb " + "a" * 64 + " -->\n")
    (tmp_path / "notes/wiki/daily/today.md").write_text(
        "Text.\n<!-- tarav.context 5a029cbf:0123456789abcdef -->\n")
    (tmp_path / "skills/broken/.skw").mkdir(parents=True)
    (tmp_path / "skills/broken/.skw/main.json").write_text("{}")
    project = _project(tmp_path, DocsProject)
    run = project.checks().run()
    assert [type(result.check) for result in run.results] == [SkillLoadCheck,
                                                              ProvisionalMarkersCheck]
    assert run.results[0].status == "incomplete"
    [poi] = run.results[1].pois()
    assert poi.situation == {"note": "daily/today.md"}
