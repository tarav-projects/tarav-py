"""A Project's checks have one entry point: TaravProject.check()."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l1.checks import Check, CheckPOI, CheckResult, check_report
from tarav.l1.project import TaravProject
from tarav.l1.project.workflow import PROJECT_WORKFLOW_SHIP
from tarav.l3.check import report_project_checks
from tarav.l3.cli.cli import main


class _Flags(Check):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("3f0d2c4e-8a51-4b7f-9c2e-6d1a0b7e5f93"),
                          name="Test.Checks.Flags", workflow=PROJECT_WORKFLOW_SHIP)

    def __init__(self, flagged: bool) -> None:
        super().__init__()
        self.flagged = flagged

    def _run(self) -> CheckResult:
        if not self.flagged:
            return CheckResult(self, status="completed")
        poi = CheckPOI(self, "flagged", "something is off", situation={"case": "flagged"})
        return CheckResult(self, status="completed", pois=[poi])


class _Project:
    """Stands in for a Project subtype that implements check()."""

    def __init__(self, *checks: Check) -> None:
        self.checks = checks

    def check(self) -> tuple[CheckResult, ...]:
        return tuple(check.run() for check in self.checks)


def test_the_base_project_has_no_checks_to_run() -> None:
    project = TaravProject.__new__(TaravProject)
    with pytest.raises(NotImplementedError, match="does not implement check"):
        project.check()


def test_the_report_carries_every_result_and_its_pois() -> None:
    report = check_report(_Project(_Flags(False), _Flags(True)).check())
    assert (report["checks"], report["incomplete"], report["pois"]) == (2, 0, 1)
    assert [row["check"] for row in report["results"]] == ["Test.Checks.Flags"] * 2
    assert report["results"][1]["pois"][0]["code"] == "flagged"
    json.dumps(report)


def test_clean_checks_exit_zero_and_pois_exit_one(capsys) -> None:
    assert report_project_checks(_Project(_Flags(False))) == 0
    assert "1 checks, 0 incomplete, 0 POIs" in capsys.readouterr().out
    assert report_project_checks(_Project(_Flags(True)), json_output=True) == 1
    assert json.loads(capsys.readouterr().out)["pois"] == 1


def test_a_project_without_checks_is_reported_not_raised(capsys) -> None:
    assert report_project_checks(TaravProject.__new__(TaravProject)) == 2
    assert "does not implement check()" in capsys.readouterr().err


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
