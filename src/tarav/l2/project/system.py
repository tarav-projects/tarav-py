"""The Tarav System Project: one per machine, at `~/Documents/tarav/system/`.

It is an ordinary Project, a place, from which work over all Projects is done:
its record names the active Projects, by hand, and its checks run over them.
Projects never know about it. `tarav init --system` creates it.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess

from tarav.l0._core.data_root import default_tarav_data_root
from tarav.l0._core.errors import CliError
from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l0.project import require_agentos_project
from tarav.l1.checks import Check, CheckPOI, CheckResult, CheckSuite
from tarav.l1.project.workflow import PROJECT_WORKFLOW_SHIP

from . import Project
from .harness import ProjectHarness


def system_root() -> Path:
    """Where this machine's System Project lives."""
    return default_tarav_data_root() / "system"


# tarav.breadcrumb 54db358d862b223c5add4db4e4eb2d78c2d2d33915c1e8fe183b0f2c23fdaf0a
# tarav.breadcrumb 564dd5d64c3d1e2fe24ac2f711643e278b7fa5679254aa675956ded48775c4ee
class TaravSystemProject(Project):
    """A machine's Tarav System Project; its own Type subclasses this one.

    `active` lists the Projects it works on, as paths; it is kept by hand.
    """

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("bbdc72b7-0d45-4489-8223-d36f9b379e7d"),
                          name="Tarav.Project.System", workflow=PROJECT_WORKFLOW_SHIP)

    class RecordInterface(Project.RecordInterface):
        active: list[str] = []

    def active_paths(self) -> tuple[Path, ...]:
        return tuple(Path(path).expanduser().resolve()
                     for path in self.records.to_record().get("active", []))

    class Checks(Project.Checks):
        def suite(self) -> CheckSuite:
            """Its own checks, and one check per active Project."""
            return CheckSuite(
                [super().suite(),
                 CheckSuite([ActiveProjectCheck(self.obj, path)
                             for path in self.obj.active_paths()],
                            name=f"{self.obj.name} active Projects")],
                name=self.obj.name, repositories=self.obj.repositories())


class ActivePOI(CheckPOI):
    """Family, never raised: an active Project of the System Project needs attention."""

    context_notes = ("The System Project's project.json lists its active Projects "
                     "(`active`); each one is loaded through its own harness.",)

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("1b82c932-f7dc-441e-9970-c45cc515eb6b"),
                          name="Tarav.Project.System.ActivePOI", workflow=PROJECT_WORKFLOW_SHIP)


class ActiveProjectMissing(ActivePOI):
    """No Project marker at an active path."""

    context_notes = (*ActivePOI.context_notes, "It is no longer raised once the path holds a "
                     "Project again, or it leaves the active list.")

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("90e1c418-42a5-438e-9185-80f5e7905588"),
                          name="Tarav.Project.System.ActiveMissing", workflow=PROJECT_WORKFLOW_SHIP)


class ActiveProjectDoesNotLoad(ActivePOI):
    """An active Project does not load through its harness in its own environment."""

    context_notes = (*ActivePOI.context_notes, "It is no longer raised once the Project's "
                     "harness names an environment that exists and a Type that imports there; "
                     "the details hold the error.")

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("3cee60ad-246f-48ad-84e2-a63f760e2914"),
                          name="Tarav.Project.System.ActiveDoesNotLoad",
                          workflow=PROJECT_WORKFLOW_SHIP)


# tarav.breadcrumb 002f3f48f20e7e18848a42e3045367942c0b82be9b72a79fb36190d4f18baade
class ActiveProjectCheck(Check):
    """Loads one active Project from outside, in its own environment, and nothing more."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("5e74c9f0-b625-438a-b187-fcf1f4879932"),
                          name="Tarav.Project.System.ActiveCheck", workflow=PROJECT_WORKFLOW_SHIP)

    def __init__(self, system: TaravSystemProject, path: Path) -> None:
        super().__init__()
        self.system = system
        self.path = path

    def _poi(self, poi_type: type[ActivePOI], message: str, **details) -> ActivePOI:
        return poi_type(self, message, situation={"project": str(self.path)}, details=details)

    def _run(self) -> CheckResult:
        try:
            if require_agentos_project(self.path).root.resolve() != self.path:
                raise CliError("no marker")
        except CliError:
            return CheckResult(self, status="completed", pois=[self._poi(
                ActiveProjectMissing, f"No Project at the active path {self.path}")])
        try:
            harness = ProjectHarness.from_path(path=self.path)
            harness.require_environment()
            environment = {**os.environ}
            environment.pop("VIRTUAL_ENV", None)
            done = subprocess.run([str(harness.interpreter), *harness.command(code="pass")],
                                  cwd=self.path, env=environment, capture_output=True, text=True,
                                  check=False)
            error = None if done.returncode == 0 else (done.stderr or done.stdout).strip()
        except (CliError, OSError) as exc:
            error = f"{type(exc).__name__}: {exc}"
        pois = [] if error is None else [self._poi(
            ActiveProjectDoesNotLoad, f"{self.path.name} does not load through its harness",
            error="\n".join(error.splitlines()[-5:]))]
        return CheckResult(self, status="completed", pois=pois)


SYSTEM_RECORD_TYPES = (ActivePOI, ActiveProjectMissing, ActiveProjectDoesNotLoad)

__all__ = ["ActivePOI", "ActiveProjectCheck", "ActiveProjectDoesNotLoad", "ActiveProjectMissing",
           "SYSTEM_RECORD_TYPES", "TaravSystemProject", "system_root"]
