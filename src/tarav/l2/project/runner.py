"""Project-owned configuration for the shared Python runner."""

from __future__ import annotations

from collections.abc import Mapping
import os
from pathlib import Path

from tarav.l0._core.errors import CliError
from tarav.l0.project import require_agentos_project
from tarav.l0.kernel import TaravClass, TaravObject, TypeShip
from tarav.l1.project.workflow import PROJECT_WORKFLOW_SHIP
from tarav.l1.python_env.runner import RunnerConfiguration, RunnerConfigurator


class ProjectRunnerError(CliError):
    """Project launch configuration is invalid or incomplete."""


class ProjectLaunchConfiguration(TaravObject):
    """Common marker projection needed before concrete Project Type dispatch."""

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
        manifest: str
        environment: str
        declared: bool
        harness_root: str | None = None

    def __init__(
        self,
        *,
        root: Path | str,
        manifest: Path | str,
        environment: Path | str,
        declared: bool,
        harness_root: Path | str | None = None,
    ) -> None:
        super().__init__()
        self.root = Path(root).expanduser().resolve()
        # The Project whose folder holds the harness: this one, or an ancestor
        # that lists this Project as a child and shares its environment.
        self.harness_root = (
            Path(harness_root).expanduser().resolve() if harness_root else self.root
        )
        self.manifest = Path(manifest).expanduser().resolve()
        self.environment = Path(environment).expanduser().resolve()
        self.declared = declared
        self._require_contained(self.manifest, "manifest")
        self._require_contained(self.environment, "environment")

    @classmethod
    def from_path(cls, path: Path | str = ".") -> ProjectLaunchConfiguration:
        """Read common marker fields without dispatching its concrete Type."""
        # tarav.breadcrumb 107c07cf7367ba3ad134140f1f42a8363577cd049754ee4d009d37107becb3d5

        handler = require_agentos_project(path)
        root = handler.root.resolve()
        declaration = handler.project_json.get("harness")
        if declaration is None:
            return cls(
                root=root,
                manifest=root / ".tarav/pyproject.toml",
                environment=root / ".tarav/env",
                declared=False,
            )
        if not isinstance(declaration, Mapping):
            raise ProjectRunnerError("Project harness declaration must be an object")
        if "project" in declaration:
            return cls._from_ancestor(root, declaration)
        return cls(
            root=root,
            manifest=cls._relative_path(declaration, "manifest", root),
            environment=cls._relative_path(declaration, "environment", root),
            declared=True,
        )

    # tarav.breadcrumb e3562e3dd3610cd7e7841afc0b4dc571d01ba89255c966ab3eda504b3d22bc20
    @classmethod
    def _from_ancestor(
        cls, root: Path, declaration: Mapping[object, object]
    ) -> ProjectLaunchConfiguration:
        """Use the harness of an ancestor Project that lists this one as a child."""
        if set(declaration) != {"project"}:
            raise ProjectRunnerError(
                "A Project harness declaration names an ancestor Project or "
                "a manifest and environment, not both"
            )
        value = declaration["project"]
        if not isinstance(value, str) or not value or Path(value).is_absolute():
            raise ProjectRunnerError(
                "Project harness project must be a relative path to an ancestor"
            )
        ancestor = (root / value).resolve()
        if ancestor == root or not root.is_relative_to(ancestor):
            raise ProjectRunnerError(
                f"Project harness project must be an ancestor folder: {ancestor}"
            )
        handler = require_agentos_project(ancestor)
        if handler.root.resolve() != ancestor:
            raise ProjectRunnerError(f"No Project marker at the ancestor: {ancestor}")
        children = handler.project_json.get("children")
        child = root.relative_to(ancestor).as_posix()
        if not isinstance(children, list) or child not in children:
            raise ProjectRunnerError(
                f"The ancestor Project does not list this Project as a child: {child}"
            )
        shared = cls.from_path(ancestor)
        if shared.harness_root != ancestor:
            raise ProjectRunnerError(
                "The ancestor Project must keep its own harness, not share another"
            )
        return cls(
            root=root,
            manifest=shared.manifest,
            environment=shared.environment,
            declared=True,
            harness_root=ancestor,
        )

    @staticmethod
    def _relative_path(
        declaration: Mapping[object, object], field: str, root: Path
    ) -> Path:
        value = declaration.get(field)
        if not isinstance(value, str) or not value:
            raise ProjectRunnerError(
                f"Project harness {field} must be a non-empty relative path"
            )
        relative = Path(value)
        if relative.is_absolute():
            raise ProjectRunnerError(
                f"Project harness {field} must be relative to the Project root"
            )
        target = (root / relative).resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise ProjectRunnerError(
                f"Project harness {field} resolves outside the Project root"
            ) from exc
        return target

    def _require_contained(self, path: Path, field: str) -> None:
        try:
            path.relative_to(self.harness_root)
        except ValueError as exc:
            raise ProjectRunnerError(
                f"Project harness {field} resolves outside the Project root"
            ) from exc

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
        return cls(
            root=record_data.root,
            manifest=record_data.manifest,
            environment=record_data.environment,
            declared=record_data.declared,
            harness_root=record_data.harness_root,
        )

    def _to_record(self):
        return {
            **super()._to_record(),
            "root": str(self.root),
            "manifest": str(self.manifest),
            "environment": str(self.environment),
            "declared": self.declared,
            "harness_root": str(self.harness_root),
        }

    class Records(TaravObject.Records):
        def record_example(self):
            cls = self._owner
            root = Path.cwd().resolve()
            return cls(
                root=root,
                manifest=root / ".tarav/pyproject.toml",
                environment=root / ".tarav/env",
                declared=False,
            ).records.to_record()



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
