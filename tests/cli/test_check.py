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


# tarav.breadcrumb 1c3211e4813cc9462c4d94f77ac404645ccf0c232bc8b4e184bccb4426600fa9
def test_the_base_project_is_a_check_provider_with_no_checks() -> None:
    project = TaravProject.__new__(TaravProject)
    assert isinstance(project, CheckProvider)
    with pytest.raises(NotImplementedError, match="declares no checks"):
        project.checks.suite()


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
    assert "1 checks, 0 incomplete, 0 POIs" in capsys.readouterr().out
    assert report_project_checks(_Project(_Flags(True)), json_output=True) == 1
    assert json.loads(capsys.readouterr().out)["summary"]["pois"] == 1


def test_a_project_without_checks_is_reported_not_raised(capsys) -> None:
    assert report_project_checks(TaravProject.__new__(TaravProject)) == 2
    assert "declares no checks" in capsys.readouterr().err


def test_the_cli_runs_check_in_the_project_harness(tmp_path: Path, monkeypatch) -> None:
    from tarav.l3.project import harness

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
    assert lines[0] == "2 checks, 1 incomplete, 0 POIs"
    assert "'failed': 1" in lines[1]
    assert not any("RuntimeError: boom" in line for line in lines)


def test_many_project_pois_render_as_one_type_group(capsys) -> None:
    class ManyProject:
        @property
        def checks(self):
            return CheckSuite(_Flags(True) for _ in range(25))

    assert report_project_checks(ManyProject()) == 1
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "25 checks, 0 incomplete, 25 POIs"
    assert len([line for line in lines if "POIs from" in line]) == 1
    assert "25 POIs from 25 checks" in lines[1]

    assert report_project_checks(ManyProject(), by="identity", limit=1, json_output=True) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["shown"] == 1
    assert report["matching"] == 1  # all 25 checks found the same situation
