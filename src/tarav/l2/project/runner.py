"""Project-owned configuration for the shared Python runner."""

from __future__ import annotations

import os
from pathlib import Path

from tarav.l0._core.errors import CliError
from tarav.l0.project import ProjectHarnessConfig, require_agentos_project
from pydantic import ValidationError

from tarav.l0.kernel import TaravClass, TaravObject, TypeShip
from tarav.l1.project.workflow import PROJECT_WORKFLOW_SHIP
from tarav.l1.python_env.runner import RunnerConfiguration, RunnerConfigurator


class ProjectRunnerError(CliError):
    """Project launch configuration is invalid or incomplete."""


# tarav.breadcrumb ad5d8401295e
class ProjectLaunchConfiguration(TaravObject):
    """What starts a Project, read from the `harness` of its project.json before
    its Type is known: the environment, and the Project Type to import there.

    The environment is a uv environment; its manifest (`pyproject.toml`) sits
    beside it, in the folder holding the environment, where uv expects it.
    """

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip("8b11c276-5d55-4fc2-8f10-4b99f4f5719f"),
            name="Tarav.Project.LaunchConfiguration",
            workflow=PROJECT_WORKFLOW_SHIP,
        )

    class RecordInterface(TaravObject.RecordInterface):
        root: str
        environment: str
        project_type: str

    def __init__(self, *, root: Path | str, environment: Path | str, project_type: str) -> None:
        super().__init__()
        self.root = Path(root).expanduser().resolve()
        self.environment = Path(environment).expanduser().resolve()
        self.manifest = self.environment.parent / "pyproject.toml"
        self.project_type = project_type

    @classmethod
    def from_path(cls, path: Path | str = ".") -> ProjectLaunchConfiguration:
        """Read the harness of the Project at `path` without loading its Type."""
        # tarav.breadcrumb 107c07cf7367

        handler = require_agentos_project(path)
        raw = handler.project_json.get("harness")
        if raw is None:
            raise ProjectRunnerError(f"{handler.marker_path} declares no harness: "
                                     "harness.environment and harness.type")
        try:
            harness = ProjectHarnessConfig.model_validate(raw)
        except ValidationError as exc:
            raise ProjectRunnerError(f"{handler.marker_path}: invalid harness: {exc}") from exc
        root = handler.root.resolve()
        return cls(root=root, environment=root / harness.environment,
                   project_type=harness.type)

    @property
    def interpreter(self) -> Path:
        return self.environment / (
            "Scripts/python.exe" if os.name == "nt" else "bin/python"
        )

    def require_environment(self) -> None:
        if (
            not (self.environment / "pyvenv.cfg").is_file()
            or not self.interpreter.is_file()
        ):
            raise ProjectRunnerError(
                "Project environment is absent or incomplete; explicitly sync it: "
                f"{self.environment}"
            )

    @classmethod
    def _from_record(cls, record_data):
        return cls(root=record_data.root, environment=record_data.environment,
                   project_type=record_data.project_type)

    def _to_record(self):
        return {**super()._to_record(), "root": str(self.root),
                "environment": str(self.environment), "project_type": self.project_type}

    class Records(TaravObject.Records):
        def record_example(self):
            root = Path.cwd().resolve()
            return self._owner(root=root, environment=root / ".tarav/env",
                               project_type="tarav.l2.project:Project").records.to_record()


class ProjectRunnerConfigurator(RunnerConfigurator):
    """Resolve Python execution from a bootstrap-safe Project projection."""

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip("1ba53de2-460d-4ae6-af20-2856f2ff2d08"),
            name="Tarav.Project.RunnerConfigurator",
            workflow=PROJECT_WORKFLOW_SHIP,
        )

    def __init__(self, launch: ProjectLaunchConfiguration) -> None:
        if not isinstance(launch, ProjectLaunchConfiguration):
            raise TypeError("launch must be a ProjectLaunchConfiguration")
        super().__init__()
        self.launch = launch

    @classmethod
    def from_path(cls, path: Path | str = ".") -> ProjectRunnerConfigurator:
        return cls(ProjectLaunchConfiguration.from_path(path))

    def configure(self) -> RunnerConfiguration:
        self.launch.require_environment()
        return RunnerConfiguration(
            interpreter=self.launch.interpreter,
            cwd=self.launch.root,
        )


PROJECT_RUNNER_RECORD_TYPES = (
    ProjectLaunchConfiguration,
)


__all__ = [
    "PROJECT_RUNNER_RECORD_TYPES",
    "ProjectLaunchConfiguration",
    "ProjectRunnerConfigurator",
    "ProjectRunnerError",
]
