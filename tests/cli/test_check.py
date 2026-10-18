"""A Project is a CheckProvider; tarav check --project runs its checks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l1.checks import Check, CheckPOI, CheckProvider, CheckResult, CheckSuite, check_report
from tarav.l1.project import TaravProject
from tarav.l1.project.workflow import PROJECT_WORKFLOW_SHIP
from tarav.l3.check import report_project_checks
from tarav.l3.cli.cli import main


class _Flags(Check):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("3f0d2c4e-8a51-4b7f-9c2e-6d1a0b7e5f93"),
                          name="Test.Checks.Flags", workflow=PROJECT_WORKFLOW_SHIP)

    def __init__(self, flagged: bool, *, crash: bool = False) -> None:
        super().__init__()
        self.flagged = flagged
        self.crash = crash

    def _run(self) -> CheckResult:
        if self.crash:
            raise RuntimeError("boom")
        if not self.flagged:
            return CheckResult(self, status="completed")
        poi = CheckPOI(self, "something is off", situation={"case": "flagged"})
        return CheckResult(self, status="completed", pois=[poi])


class _Project:
    """Stands in for a Project subtype that lists its checks."""

    def __init__(self, *checks: Check) -> None:
        self._checks = checks

    @property
    def checks(self):
        return CheckSuite(self._checks)


class _SpecialPOI(CheckPOI):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("477c579d-6d72-4b3c-b0c1-58ee7df8a223"),
                          name="Test.Checks.SpecialPOI", workflow=PROJECT_WORKFLOW_SHIP)


class _Mixed(Check):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("29a1c817-445b-4e4c-94ce-586d9470f30b"),
                          name="Test.Checks.Mixed", workflow=PROJECT_WORKFLOW_SHIP)

    def _run(self) -> CheckResult:
        return CheckResult(self, status="completed", pois=[
            CheckPOI(self, "base case", situation={"case": "base"}),
            _SpecialPOI(self, "special case", situation={"case": "special"}),
        ])


# tarav.breadcrumb 1c3211e4813c
def test_a_project_is_a_check_provider_and_a_bare_provider_has_no_checks() -> None:
    # the base Project has its shared bootstrap checks; only a bare provider has none
    assert issubclass(TaravProject, CheckProvider)
    assert "suite" in TaravProject.Checks.__dict__
    with pytest.raises(NotImplementedError, match="Tarav.Checks.Provider declares no checks"):
        CheckProvider().checks.suite()


def test_the_report_carries_every_result_and_its_pois() -> None:
    report = check_report(
        check.run() for check in _Project(_Flags(False), _Flags(True)).checks.source
    )
    assert (report["checks"], report["incomplete"], report["pois"]) == (2, 0, 1)
    assert [row["check"] for row in report["results"]] == ["Test.Checks.Flags"] * 2
    assert report["results"][1]["pois"][0]["message"] == "something is off"
    json.dumps(report)


def test_clean_checks_exit_zero_and_pois_exit_one(capsys) -> None:
    assert report_project_checks(_Project(_Flags(False))) == 0
    assert "1 checks ran, all completed. 0 POIs." in capsys.readouterr().out
    assert report_project_checks(_Project(_Flags(True)), json_output=True) == 1
    assert json.loads(capsys.readouterr().out)["summary"]["pois"] == 1


def test_a_provider_without_checks_is_reported_not_raised(capsys) -> None:
    assert report_project_checks(CheckProvider()) == 2
    assert "declares no checks" in capsys.readouterr().err


def test_the_cli_runs_check_in_the_project_harness(tmp_path: Path, monkeypatch) -> None:
    from tarav.l3 import check as check_module
    from tarav.l3.project import harness

    # the command also tells the machine's Project index; keep the test out of it
    (tmp_path / ".tarav").mkdir()
    (tmp_path / ".tarav/project.json").write_text(json.dumps({
        "project_id": "5d0c8a3e-2b17-4f69-8e4a-9c1d7b6f3a20",
        "created_at": "2026-10-15T00:00:00Z"}))
    monkeypatch.setattr(check_module, "observe_project", lambda root: None, raising=False)
    launched = []

    def run(*, path, code):
        launched.append((path, code))
        namespace = {"project": _Project(_Flags(True))}
        try:
            exec(code, namespace)
        except SystemExit as exc:
            return exc.code
        return 0

    monkeypatch.setattr(harness, "run", run)
    assert main(["check", "--project", str(tmp_path)]) == 1
    assert launched[0][0] == tmp_path


def test_the_cli_needs_a_project() -> None:
    assert main(["check"]) != 0


def test_report_is_grouped_and_a_crash_becomes_a_failed_result(capsys) -> None:
    assert report_project_checks(_Project(_Flags(False, crash=True), _Flags(False))) == 1
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "2 checks ran, 1 did not complete. 0 POIs."
    assert lines[1] == "  did not complete: Test.Checks.Flags (1 failed)"
    assert not any("RuntimeError: boom" in line for line in lines)


def test_many_project_pois_render_as_one_type_group(capsys) -> None:
    class ManyProject:
        @property
        def checks(self):
            return CheckSuite(_Flags(True) for _ in range(25))

    assert report_project_checks(ManyProject()) == 1
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "25 checks ran, all completed. 25 POIs."
    groups = [line for line in lines if "POIs from" in line]
    assert len(groups) == 1 and "25 POIs from 25 checks" in groups[0]

    assert report_project_checks(ManyProject(), by="identity", limit=1, json_output=True) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["shown"] == 1
    assert report["matching"] == 1  # all 25 checks found the same situation


# tarav.breadcrumb ff8a74613bbe
def test_type_filter_includes_subtypes_and_preserves_full_run_status(capsys) -> None:
    project = _Project(_Mixed())
    assert report_project_checks(project, poi_type="Tarav.Checks.POI", json_output=True) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["summary"]["pois"] == 2
    assert report["matching_pois"] == 2
    assert report["filters"] == {"type": "Tarav.Checks.POI"}
    assert report["matching"] == 2

    assert report_project_checks(project, poi_type="Test.Checks.SpecialPOI",
                                 json_output=True) == 1
    exact = json.loads(capsys.readouterr().out)
    assert exact["matching_pois"] == 1

    assert report_project_checks(project, poi_type="Test.Checks.SpecialPOI") == 1
    output = capsys.readouterr().out
    assert "1 checks ran, all completed. 2 POIs." in output
    assert "Showing 1 of 2 POIs matching type=Test.Checks.SpecialPOI" in output
    assert "POIs by type:" not in output

    assert report_project_checks(project, poi_type="Tarav.POI", json_output=True) == 1
    assert json.loads(capsys.readouterr().out)["matching_pois"] == 2
