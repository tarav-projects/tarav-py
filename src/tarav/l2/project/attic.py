"""Project-local discovery and composition of the independent Attic workflow."""

from pathlib import PurePosixPath

from pydantic import BaseModel, ConfigDict, field_validator

from tarav.l0._core.errors import CliError
from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l1.attic import Attic, AtticWorkflow
from tarav.l1.checks import Check, CheckResult, CheckSuite
from tarav.l1.project.config import ProjectConfig
from tarav.l1.project.workflow import PROJECT_WORKFLOW_SHIP


# tarav.breadcrumb fe1b20023be7
class ProjectAtticConfig(BaseModel):
    """The Attic section of `.tarav/config.json`; paths are Project-relative."""

    model_config = ConfigDict(strict=True, extra="forbid")

    path: str = "_ATTIC"

    @field_validator("path")
    @classmethod
    def local_folder(cls, value):
        path = PurePosixPath(value)
        if (not value.strip() or not path.parts or path.is_absolute()
                or ".." in path.parts or "\\" in value or "\0" in value):
            raise ValueError("Attic path must name a folder below the Project")
        return value


def project_attic(project) -> Attic:
    """Select a local Attic without creating its directory or reading payloads."""
    config = ProjectConfig(project.root).section("attic", ProjectAtticConfig)
    path = (project.root / (config or ProjectAtticConfig()).path).resolve()
    if path == project.root or not path.is_relative_to(project.root):
        raise CliError("Attic path must resolve below the Project")
    return AtticWorkflow.open(path)


class AtticLoadCheck(Check):
    """A Project's Attic location could not be selected; its scan is incomplete."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("b2bdb172-dc1f-4d23-b3fd-165f90086d87"),
                          name="Tarav.Project.Attic.Load", workflow=PROJECT_WORKFLOW_SHIP)

    def __init__(self, reason):
        super().__init__()
        self.reason = reason

    def _run(self):
        return CheckResult(self, status="incomplete", reason=self.reason)


def project_attic_checks(project) -> CheckSuite:
    """Resolve lazily so a malformed config does not stop unrelated checks."""
    def produce(_suite):
        try:
            attic = project.attic()
        except (CliError, OSError, ValueError, RuntimeError) as exc:
            yield AtticLoadCheck(f"{type(exc).__name__}: {exc}")
        else:
            yield attic.checks.suite()

    return CheckSuite(produce, name="Project Attic")
