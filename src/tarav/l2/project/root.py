"""A root Project over the child Projects its marker lists."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from tarav.l0._core.errors import CliError
from tarav.l0._core.project import require_agentos_project
from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l1.checks import Check, CheckPOI, CheckResult, CheckSuite
from tarav.l1.project import TaravProject
from tarav.l1.project.workflow import PROJECT_WORKFLOW_SHIP

from . import Project
from .harness import ProjectHarness
from .runner import ProjectLaunchConfiguration, ProjectRunnerError


# tarav.breadcrumb 21a58e45c152521ac93f0ff0957d825ba966f6fd39858553439d7b6cc6527828
# tarav.breadcrumb a36e9974ecedf7230bd7a4bf01d17a42fc2eec20a81ae33048e398a1403345a7
class RootProject(Project):
    """A folder whose Projects are listed children; its checks are theirs.

    Only listed folders are children, so a root can hold a link to a place
    that is not its child without collecting it.
    """

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls,
                          id=TypeShip("150b82a2-71c9-428d-862a-24f0d2d14677"),
                          name="Tarav.Project.Root", workflow=PROJECT_WORKFLOW_SHIP)

    def child_paths(self) -> tuple[str, ...]:
        children = self.records.to_record().get("children", [])
        if not isinstance(children, list):
            raise ProjectRunnerError("Root Project children must be a list of paths")
        for child in children:
            if not isinstance(child, str) or not child or Path(child).is_absolute():
                raise ProjectRunnerError(f"Root Project child must be a relative path: {child!r}")
            path = (self.root / child).resolve()
            if path == self.root or not path.is_relative_to(self.root):
                raise ProjectRunnerError(f"Root Project child must lie below the root: {child}")
        return tuple(children)

    def child(self, relative: str) -> TaravProject:
        """Load one listed child; its marker Type must be bound in this runtime."""
        if relative not in self.child_paths():
            raise ProjectRunnerError(f"Not a listed child of this root: {relative}")
        path = (self.root / relative).resolve()
        if require_agentos_project(path).root.resolve() != path:
            raise ProjectRunnerError(f"No Project marker at the child folder: {relative}")
        return TaravProject.load_project(path=path)

    def children(self) -> tuple[TaravProject, ...]:
        return tuple(self.child(relative) for relative in self.child_paths())

    # tarav.breadcrumb fce5f1a0129b44b625e1de501793625ea4f9b2d0778224beb59c68e5a28fd8c9
    # tarav.breadcrumb 2b6fe56e6a9feeb5ea9ac5ce7cd3d4036cda1f0c9e630e4cd823cfc6af0e3a1f
    class Checks(Project.Checks):
        def suite(self) -> CheckSuite:
            return CheckSuite(
                [super().suite(),
                 CheckSuite(lambda run: map(self.obj._child_checks,
                                            self.obj.child_paths()))],
                name=self.obj.name,
            )

    def _child_checks(self, relative: str) -> CheckSuite | Check | CheckResult:
        """A child sharing this environment runs in place; others in their own."""
        check = ChildProjectCheck(self, relative)
        path = (self.root / relative).resolve()
        try:
            if require_agentos_project(path).root.resolve() != path:
                return CheckResult(check, status="incomplete",
                                   reason=f"no Project marker at {relative}")
            launch = ProjectLaunchConfiguration.from_path(path)
            if launch.environment != Path(sys.prefix).resolve():
                return check
            return CheckSuite.of(self.child(relative).checks.suite())
        except NotImplementedError as exc:
            return CheckResult(check, status="incomplete", reason=str(exc))
        except (CliError, TypeError, ValueError, LookupError) as exc:
            return CheckResult(check, status="incomplete",
                               reason=f"{type(exc).__name__}: {exc}")


class ChildProjectPOI(CheckPOI):
    """POIs of one type that a child Project reported from its own environment."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls,
                          id=TypeShip("04a70330-76a0-4393-b51d-741fadbcdbb4"),
                          name="Tarav.Project.Root.ChildPOIs", workflow=PROJECT_WORKFLOW_SHIP)


class ChildProjectCheck(Check):
    """Run a child Project's checks in its own environment and report its counts.

    A child with its own environment cannot load in this process, so its
    result arrives as one row per POI type with the count, not as its POIs.
    """

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls,
                          id=TypeShip("022c4e7e-dc20-4329-9ffb-5dede22db624"),
                          name="Tarav.Project.Root.ChildCheck", workflow=PROJECT_WORKFLOW_SHIP)

    def __init__(self, parent: RootProject, child: str) -> None:
        super().__init__()
        self.parent = parent
        self.child = child

    def _run(self) -> CheckResult:
        path = (self.parent.root / self.child).resolve()
        code = ("import json\nfrom tarav.l1.checks import CheckSuite\n"
                "run = project.checks.run()\n"
                "print(json.dumps(run.report(limit=10**9), default=str))\n")
        try:
            harness = ProjectHarness.from_path(path=path)
            harness.require_environment()
            environment = {**os.environ}
            environment.pop("VIRTUAL_ENV", None)
            completed = subprocess.run(
                [str(harness.interpreter), *harness.command(code=code)],
                cwd=path, env=environment, capture_output=True, text=True, check=False,
            )
            report = json.loads(completed.stdout.strip().splitlines()[-1])
        except (CliError, OSError, ValueError, IndexError) as exc:
            return CheckResult(self, status="failed", reason=f"{type(exc).__name__}: {exc}")
        pois = [
            ChildProjectPOI(self, row["key"],
                            f"{row['pois']} {row['key']} POIs in {self.child}",
                            situation={"child": self.child, "type": row["key"]},
                            details={"pois": row["pois"], "open": row["open"],
                                     "checks": row["checks"]})
            for row in report["items"]
        ]
        incomplete = report["summary"]["incomplete"]
        return CheckResult(
            self, status="completed" if not incomplete else "incomplete", pois=pois,
            data=report["summary"],
            reason=f"{incomplete} incomplete checks in {self.child}" if incomplete else None,
        )


__all__ = ["ChildProjectCheck", "ChildProjectPOI", "RootProject"]
