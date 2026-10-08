"""General Project Types for places where a library and its documents are developed.

A development folder can be a root Project over these children. Their checks
are deliberately few; a library's own subtype adds what is specific to it.
"""

from __future__ import annotations

from pathlib import Path
import re
import subprocess
import sys

from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l1.checks import Check, CheckPOI, CheckResult, CheckSuite
from tarav.l1.project.workflow import PROJECT_WORKFLOW_SHIP

from . import Project

_FAILURE = re.compile(r"^(FAILED|ERROR) (\S+)(?: - (.*))?$")
_PROVISIONAL = re.compile(r"tarav\.context [0-9a-f]{8}:[0-9a-f]{16}")


class TestFailurePOI(CheckPOI):
    """A test of the Project's suite that failed or errored."""

    __test__ = False

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("e79b1433-b8ee-4be9-a46b-1d6437214f63"),
                          name="Tarav.Project.Dev.TestFailure", workflow=PROJECT_WORKFLOW_SHIP)


class TestSuiteCheck(Check):
    """Run the Project's pytest suite with the running interpreter."""

    __test__ = False

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("21f16812-bbbe-4de8-b254-889b9ff4863a"),
                          name="Tarav.Project.Dev.TestSuite", workflow=PROJECT_WORKFLOW_SHIP)

    def __init__(self, root: Path, *, arguments: tuple[str, ...] = ()) -> None:
        super().__init__()
        self.root = Path(root)
        self.arguments = tuple(arguments)

    def _run(self) -> CheckResult:
        completed = subprocess.run(
            # A test file that cannot be collected is reported, not a reason to
            # skip the rest of the suite.
            [sys.executable, "-m", "pytest", "-q", "-rfE", "-p", "no:cacheprovider",
             "--continue-on-collection-errors", *self.arguments],
            cwd=self.root, capture_output=True, text=True, check=False,
        )
        lines = completed.stdout.splitlines()
        if completed.returncode not in (0, 1, 5):
            return CheckResult(self, status="failed",
                               reason="\n".join((lines or completed.stderr.splitlines())[-5:]))
        pois = []
        for line in lines:
            match = _FAILURE.match(line)
            if match:
                outcome, test, message = match.groups()
                pois.append(TestFailurePOI(
                    self, outcome.lower(), f"{test}: {message or outcome.lower()}",
                    situation={"project": self.root.name, "test": test}))
        return CheckResult(self, status="completed", pois=pois,
                           data={"summary": lines[-1] if lines else ""})


class ProvisionalMarkerPOI(CheckPOI):
    """A Note still carries provisional Breadcrumb markers that were never submitted."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("568afde8-7cdd-4549-b4e0-5edf7baa3c6c"),
                          name="Tarav.Project.Dev.ProvisionalMarker", workflow=PROJECT_WORKFLOW_SHIP)


class ProvisionalMarkersCheck(Check):
    """Find Markdown Notes under a folder with unsubmitted `tarav.context` markers."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("041ef42f-f251-421e-a016-f842b1b61e8a"),
                          name="Tarav.Project.Dev.ProvisionalMarkers",
                          workflow=PROJECT_WORKFLOW_SHIP)

    def __init__(self, folder: Path) -> None:
        super().__init__()
        self.folder = Path(folder)

    def _run(self) -> CheckResult:
        pois = []
        for note in sorted(self.folder.rglob("*.md")):
            count = len(_PROVISIONAL.findall(note.read_text(encoding="utf-8", errors="replace")))
            if count:
                relative = note.relative_to(self.folder).as_posix()
                pois.append(ProvisionalMarkerPOI(
                    self, "provisional", f"{relative}: {count} provisional markers",
                    situation={"note": relative}, details={"markers": count}))
        return CheckResult(self, status="completed", pois=pois)


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
            return CheckSuite([super().suite(), TestSuiteCheck(self.obj.root)],
                              name=self.obj.name)


class DocsProject(Project):
    """A folder of skills, wiki and notes: its skills' checks and unsubmitted markers."""

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
                               CheckSuite(lambda run: self.obj._checks())],
                              name=self.obj.name)

    def _checks(self):
        from tarav.l0.kernel.current import current_records
        from tarav.l2.skw.skills import load_skill

        for folder in self.skill_folders():
            try:
                yield load_skill(folder, registry=current_records()).checks.suite()
            except (OSError, ValueError, TypeError, RuntimeError) as exc:
                yield SkillLoadCheck(folder, f"{type(exc).__name__}: {exc}")
        yield ProvisionalMarkersCheck(self.root / "notes" / "wiki")


__all__ = [
    "DocsProject",
    "ProvisionalMarkerPOI",
    "ProvisionalMarkersCheck",
    "PythonPackageProject",
    "SkillLoadCheck",
    "TestFailurePOI",
    "TestSuiteCheck",
]
