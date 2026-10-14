"""General Project Types for places where a library and its documents are developed.

A development folder can be a root Project over these children. Their checks
are deliberately few; a library's own subtype adds what is specific to it.
"""

from __future__ import annotations

from pathlib import Path
import re
import subprocess
import sys
import tempfile
from xml.etree import ElementTree

from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l1.checks import Check, CheckPOI, CheckResult, CheckSuite
from tarav.l1.project.workflow import PROJECT_WORKFLOW_SHIP

from . import Project

_FAILURE = re.compile(r"^(FAILED|ERROR) (\S+)(?: - (.*))?$")


class TestFailurePOI(CheckPOI):
    """Family, never raised: a test of the Project's suite did not pass."""

    __test__ = False

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("e79b1433-b8ee-4be9-a46b-1d6437214f63"),
                          name="Tarav.Project.Dev.TestFailure", workflow=PROJECT_WORKFLOW_SHIP)


class TestFailed(TestFailurePOI):
    """A test of the Project's suite failed an assertion."""

    __test__ = False

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("a8ca5b56-7ed2-40ea-aa79-3a4cf850358b"),
                          name="Tarav.Project.Dev.TestFailure.Failed", workflow=PROJECT_WORKFLOW_SHIP)


class TestErrored(TestFailurePOI):
    """A test of the Project's suite raised an error."""

    __test__ = False

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("c5fc0e77-32f1-46fe-8ca7-a3ffc167ff41"),
                          name="Tarav.Project.Dev.TestFailure.Errored", workflow=PROJECT_WORKFLOW_SHIP)


def _pytest(root: Path, arguments: tuple[str, ...] = ()) -> dict:
    """Run pytest once under `root`; say whether it ran, which files ran, and what failed."""
    with tempfile.TemporaryDirectory(prefix="tarav-pytest-") as folder:
        report = Path(folder) / "junit.xml"
        completed = subprocess.run(
            # A test file that cannot be collected is reported, not a reason to
            # skip the rest of the suite.
            [sys.executable, "-m", "pytest", "-q", "-rfE", "-p", "no:cacheprovider",
             "--continue-on-collection-errors", f"--junit-xml={report}",
             "-o", "junit_family=xunit1", *arguments],
            cwd=root, capture_output=True, text=True, check=False,
        )
        lines = completed.stdout.splitlines()
        if completed.returncode not in (0, 1, 5):
            return {"ran": False,
                    "reason": "\n".join((lines or completed.stderr.splitlines())[-5:])}
        files = set()
        if report.is_file():
            files = {case.get("file") for case in ElementTree.parse(report).iter("testcase")
                     if case.get("file")}
    failures: dict[str, list[tuple[str, str, str]]] = {}
    for line in lines:
        match = _FAILURE.match(line)
        if match:
            outcome, test, message = match.groups()
            failures.setdefault(test.split("::")[0], []).append((outcome, test, message))
    return {"ran": True, "files": sorted(files | set(failures)), "failures": failures,
            "summary": lines[-1] if lines else ""}


# tarav.breadcrumb 10a6704ec38a59d5b0c7192e4d0759df90e57d0356f0f31db97b4f29d286c53e
class PyTestCheck(Check):
    """The tests of one file as pytest ran them: one POI per test that did not pass.

    Without a file it stands for pytest itself, for a run that could not start.
    """

    __test__ = False

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("3b0f6a2c-91d4-4e7b-a6c5-8f2d1e9b7a40"),
                          name="Tarav.Project.Dev.PyTest", workflow=PROJECT_WORKFLOW_SHIP)

    def __init__(self, root: Path, file: str | None = None, *,
                 arguments: tuple[str, ...] = ()) -> None:
        super().__init__()
        self.root = Path(root)
        self.file = file
        self.arguments = tuple(arguments)

    def result(self, outcome: dict) -> CheckResult:
        """This file's result, read from one pytest run."""
        if not outcome["ran"]:
            return CheckResult(self, status="failed", reason=outcome["reason"])
        pois = [
            (TestFailed if kind == "FAILED" else TestErrored)(
                self, f"{test}: {message or kind.lower()}",
                situation={"project": self.root.name, "test": test})
            for file, found in outcome["failures"].items()
            if self.file is None or file == self.file
            for kind, test, message in found
        ]
        return CheckResult(self, status="completed", pois=pois,
                           data={"file": self.file, "summary": outcome["summary"]})

    def _run(self) -> CheckResult:
        return self.result(_pytest(
            self.root, (*self.arguments, *((self.file,) if self.file else ()))))


class PyTestFileSuite(CheckSuite):
    """The tests of one file. Its key is the file, so its actions know where they belong."""

    __test__ = False

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("6d8e2f41-0c37-4a95-b1e8-4f7a9c3d5b62"),
                          name="Tarav.Project.Dev.PyTest.File", workflow=PROJECT_WORKFLOW_SHIP)


# tarav.breadcrumb 39431af614faa314ce80d70ea47cb8ee80bdb2bc2c9a11add96468927082a80b
class PyTestSuite(CheckSuite):
    """A folder's pytest tests: pytest runs once, and each test file is a suite of its own.

    It is not part of the routine run: it is as slow as the tests are. A run
    that leaves it out says nothing about the tests, so their actions stay.
    A test file that is gone is known from a complete run that no longer
    yields its suite.
    """

    __test__ = False
    routine = False

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("f1a47c95-3e60-4b28-9d7f-2c5b8e0a6d13"),
                          name="Tarav.Project.Dev.PyTest.Suite", workflow=PROJECT_WORKFLOW_SHIP)

    def __init__(self, root: Path, *, arguments: tuple[str, ...] = (),
                 key: str | None = None) -> None:
        super().__init__(name="pytest", key=key)
        self.root = Path(root)
        self.arguments = tuple(arguments)
        self.summary_line = ""

    def produce(self):
        outcome = _pytest(self.root, self.arguments)
        if not outcome["ran"]:
            yield PyTestCheck(self.root).result(outcome)
            return
        self.summary_line = outcome["summary"]
        for file in outcome["files"]:
            yield PyTestFileSuite([PyTestCheck(self.root, file).result(outcome)],
                                  name=file, key=file)


class SkillLoadCheck(Check):
    """A skill package under the Project could not be loaded to collect its checks."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("bf257488-4865-4608-a6ee-86b7b23033dc"),
                          name="Tarav.Project.Dev.SkillLoad", workflow=PROJECT_WORKFLOW_SHIP)

    def __init__(self, skill: Path, reason: str) -> None:
        super().__init__()
        self.skill = Path(skill)
        self.reason = reason

    def _run(self) -> CheckResult:
        return CheckResult(self, status="incomplete", reason=f"{self.skill.name}: {self.reason}")


# tarav.breadcrumb 50c81a4342d120bd04f087a5730da94f160ab922273343bb113503bc9f580cbb
class PythonPackageProject(Project):
    """A folder that develops a Python package; its first check is its test suite."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("a9433958-371f-473d-bfdb-9a90f5d4c682"),
                          name="Tarav.Project.PythonPackage", workflow=PROJECT_WORKFLOW_SHIP)

    # tarav.breadcrumb 3e2e1259e794f34ab722d40e3c964d52b00420a699c0d5da986870bcc1fbcb43
    # tarav.breadcrumb deb8671fb2a6493d1541d891423fd388109ce31d67e9811515cc80828f5b4660
    class Checks(Project.Checks):
        def suite(self) -> CheckSuite:
            return CheckSuite([super().suite(), PyTestSuite(self.obj.root),
                               *self.obj._poi_contract_checks()], name=self.obj.name,
                              repositories=self.obj.repositories())

# tarav.breadcrumb d72b348467b8de83b8b8de698550a5382b36011821f0192de499492b38bb2e7d
    def _poi_contract_checks(self) -> list[Check]:
        """Where the POI base Type itself is developed, check the POI contract."""
        from tarav.l1.checks.poi_contract import POIRenderCoverageCheck, defined_under
        from tarav.l1.poi import POI

        if not defined_under(POI, self.root):
            return []
        return [POIRenderCoverageCheck(self.root)]


class DocsProject(Project):
    """A folder of skills, wiki and notes: its skills' checks and its Wiki's checks."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("b811ca80-597a-4d11-90f2-7bdb30f9fd19"),
                          name="Tarav.Project.Docs", workflow=PROJECT_WORKFLOW_SHIP)

    def skill_folders(self) -> tuple[Path, ...]:
        return tuple(sorted(path.parent.parent for path in
                            (self.root / "skills").glob("*/.skw/main.json")))

    class Checks(Project.Checks):
        def suite(self) -> CheckSuite:
            return CheckSuite([super().suite(),
                               CheckSuite(lambda suite: self.obj._checks())],
                              name=self.obj.name, repositories=self.obj.repositories())

    def _checks(self):
        from tarav.l0.kernel.current import current_records
        from tarav.l2.skw.skills import load_skill

        for folder in self.skill_folders():
            try:
                yield load_skill(folder, registry=current_records()).checks.suite()
            except (OSError, ValueError, TypeError, RuntimeError) as exc:
                yield SkillLoadCheck(folder, f"{type(exc).__name__}: {exc}")
        # the Wiki says what to check about its notes
        from .wiki import ProjectWiki
        yield from ProjectWiki(self).checks()


__all__ = [
    "DocsProject",
    "PythonPackageProject",
    "SkillLoadCheck",
    "PyTestCheck",
    "PyTestFileSuite",
    "PyTestSuite",
    "TestFailurePOI",
]
