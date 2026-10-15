"""Explicit scaffolding and uv provisioning for a Project's local harness."""

from __future__ import annotations

import json
import keyword
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Sequence
from uuid import uuid4

from tarav.l0._core.persistence import atomic_write_json
from tarav.l0.project import initialize_project_layout, load_project_marker
from tarav.l0.kernel import (
    TaravClass,
    TaravObject,
    TypeShip,
    locate_record_type,
)
from tarav.l0.kernel.types import RecordTypeReference
from tarav.l1.project import TaravProject
from tarav.l1.project.workflow import PROJECT_WORKFLOW_SHIP
from tarav.l2.project.runner import ProjectLaunchConfiguration, ProjectRunnerError


class ProjectHarnessError(ProjectRunnerError):
    """Explicit Project harness setup or launch cannot proceed."""


def _identifier(value: object, description: str) -> str:
    if (
        not isinstance(value, str)
        or not value.isidentifier()
        or keyword.iskeyword(value)
    ):
        raise ProjectHarnessError(f"{description} must be a Python identifier")
    return value


class ProjectHarness(TaravObject):
    """A Project's harness on disk: the environment its project.json names, the
    manifest beside it, and the setup operations. Discovery imports nothing."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("4a54acdc-8834-4339-a18c-41ec72af2ca6"),
            name="Tarav.Project.Harness",
            workflow=PROJECT_WORKFLOW_SHIP,
        )

    class RecordInterface(TaravObject.RecordInterface):
        root: str

    def __init__(self, root: Path | str, *,
                 launch: ProjectLaunchConfiguration | None = None) -> None:
        super().__init__()
        self.root = Path(root).expanduser().resolve()
        self.directory = self.root / ".tarav"
        self.marker = self.directory / "project.json"
        self._launch = launch

    @classmethod
    def from_path(cls, *, path: Path | str = ".") -> ProjectHarness:
        launch = ProjectLaunchConfiguration.from_path(path)
        return cls(launch.root, launch=launch)

    @classmethod
    def _from_record(cls, record_data: ProjectHarness.RecordInterface) -> ProjectHarness:
        return cls(record_data.root)

    def _to_record(self) -> dict[str, object]:
        return {**super()._to_record(), "root": str(self.root)}

    @property
    def launch(self) -> ProjectLaunchConfiguration:
        if self._launch is None:
            self._launch = ProjectLaunchConfiguration.from_path(self.root)
        return self._launch

    @property
    def manifest(self) -> Path:
        return self.launch.manifest

    @property
    def env(self) -> Path:
        return self.launch.environment

    @property
    def interpreter(self) -> Path:
        return self.launch.interpreter

    def command(
        self,
        *,
        code: str | None = None,
        file: Path | str | None = None,
        arguments: Sequence[str] = (),
    ) -> list[str]:
        """Interpreter arguments that start this Project with the Type its harness names."""
        if code is not None and file is not None:
            raise ProjectHarnessError("Choose code or file, not both")
        command = ["-I", "-m", "tarav.l3.project.launch", "--project", str(self.root)]
        if code is not None:
            command.append("--code=" + code)
        elif file is not None:
            command.extend(["--file", str(Path(file).expanduser().resolve())])
        command.extend(["--", *arguments])
        return command

    def inspect(self) -> dict[str, object]:
        marker = load_project_marker(self.marker)
        return {
            "root": str(self.root),
            "project_id": marker["project_id"],
            "marker": str(self.marker),
            "type": self.launch.project_type,
            "environment": str(self.env),
            "manifest": str(self.manifest),
            "interpreter": str(self.interpreter),
            "environment_present": self.env.exists(),
        }

    @classmethod
    def scaffold(
        cls,
        *,
        path: Path | str,
        package: str,
        tarav_source: Path | str,
        class_name: str = "MyProject",
        adopt: bool = False,
    ) -> ProjectHarness:
        """Create a harness in `.tarav/`: a package defining the Project's Type, the
        manifest and the `harness` of project.json. Edited files are preserved.

        tarav_source explicitly selects a local Tarav checkout or wheel. An
        existing untyped or base-typed marker requires adopt; a marker that
        already has a harness or a specialized Type is never reassigned.
        """
        _identifier(package, "Package")
        _identifier(class_name, "Class name")
        if class_name in {"TaravClass", "TypeShip", "PROJECT_WORKFLOW_SHIP"}:
            raise ProjectHarnessError("Class name conflicts with generated imports")
        if package == "tarav":
            raise ProjectHarnessError("The harness package must not shadow tarav")
        source = Path(tarav_source).expanduser().resolve()
        if source.is_dir():
            try:
                distribution = tomllib.loads((source / "pyproject.toml").read_text())[
                    "project"
                ]["name"]
            except (OSError, ValueError, KeyError, TypeError) as exc:
                raise ProjectHarnessError(
                    f"Tarav source requires a package pyproject.toml: {source}"
                ) from exc
            if distribution != "tarav":
                raise ProjectHarnessError(f"Source is not the Tarav distribution: {source}")
        elif not source.is_file() or source.suffix != ".whl":
            raise ProjectHarnessError(f"Tarav source must be a local checkout or wheel: {source}")
        harness = cls(path)
        if not harness.root.is_dir():
            raise ProjectHarnessError(f"Project root must be an existing directory: {harness.root}")
        project_type = f"{package}.project:{class_name}"
        type_name = f"Project.{package}.{class_name}"
        type_ship = str(uuid4())
        if harness.marker.exists():
            marker = load_project_marker(harness.marker)
            location = locate_record_type(marker)
            reference = RecordTypeReference.parse(location.value) if location else None
            declared = marker.get("harness")
            if declared is not None:
                if not isinstance(declared, dict) or declared.get("type") != project_type:
                    raise ProjectHarnessError(
                        "The Project already has a harness; edit its project.json explicitly")
                if reference is not None and reference.ship is not None:
                    type_ship = str(reference.ship.uuid)
            else:
                from tarav.l2.project import Project

                if reference is not None and not any(
                        base.matches(reference) for base in (TaravProject, Project)):
                    raise ProjectHarnessError(
                        "An already specialized Project Type cannot be overwritten")
                if not adopt:
                    raise ProjectHarnessError(
                        "Existing Project marker requires explicit adopt=True (--adopt)")
        else:
            marker = initialize_project_layout(harness.root, ensure=True)["marker"]
        manifest = harness.directory / "pyproject.toml"
        if manifest.exists():
            selected = (tomllib.loads(manifest.read_text()).get("tool", {}).get("uv", {})
                        .get("sources", {}).get("tarav", {}).get("path"))
            if selected is None or (harness.directory / selected).resolve() != source:
                raise ProjectHarnessError(
                    "Existing harness dependency source differs; edit its manifest explicitly")
        else:
            manifest.write_text(_manifest(package, source), encoding="utf-8")
        package_root = harness.directory / "src" / package
        package_root.mkdir(parents=True, exist_ok=True)
        files = {
            "__init__.py": f'"""Executable Project harness."""\n\nfrom .project import {class_name}\n\n__all__ = [{class_name!r}]\n',
            "project.py": _project_source(class_name, type_ship, type_name),
        }
        for name, text in files.items():
            target = package_root / name
            if not target.exists():
                target.write_text(text, encoding="utf-8")
        location = locate_record_type(marker)
        target = marker
        path_parts = location.path if location else ("type",)
        for part in path_parts[:-1]:
            target = target[part]
        target[path_parts[-1]] = {"uuid": type_ship, "label": type_name}
        marker["harness"] = {"environment": ".tarav/env", "type": project_type}
        if load_project_marker(harness.marker) != marker:
            atomic_write_json(harness.marker, marker)
        ignore = harness.directory / ".gitignore"
        current = ignore.read_text(encoding="utf-8") if ignore.exists() else ""
        if "/env/" not in current.splitlines():
            with ignore.open("a", encoding="utf-8") as stream:
                stream.write(("\n" if current and not current.endswith("\n") else "") + "/env/\n")
        return cls.from_path(path=harness.root)

    def require_environment(self) -> None:
        try:
            self.launch.require_environment()
        except ProjectRunnerError as exc:
            raise ProjectHarnessError(str(exc)) from exc

    def sync(self, *, python: Path | str | None = None) -> None:
        """Lock and install the environment the harness names, from the manifest beside it."""
        if not self.manifest.is_file():
            raise ProjectHarnessError(f"Project harness manifest is absent: {self.manifest}")
        uv = shutil.which("uv")
        if uv is None:
            raise ProjectHarnessError("uv is required to sync the Project harness")
        if self.env.exists():
            self.require_environment()
            if python is not None:
                raise ProjectHarnessError(
                    "Existing environment cannot be replaced by selecting another Python")
            selected_python = self.interpreter
        else:
            selected_python = python if python is not None else sys.executable
        environment = {**os.environ, "UV_PROJECT_ENVIRONMENT": str(self.env)}
        environment.pop("VIRTUAL_ENV", None)
        try:
            subprocess.run(
                [uv, "sync", "--project", str(self.manifest.parent), "--no-dev",
                 "--no-python-downloads", "--python", str(selected_python)],
                cwd=self.root, env=environment, check=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise ProjectHarnessError(
                f"Project harness sync failed; existing files are preserved: {self.root}: {exc}"
            ) from exc
        self.require_environment()


def _manifest(package: str, source: Path) -> str:
    # JSON strings are also TOML basic strings, including escaped local paths.
    def quote(value: str) -> str:
        return json.dumps(value, ensure_ascii=False)

    return f"""[build-system]
requires = ["hatchling>=1.24.0"]
build-backend = "hatchling.build"

[project]
name = {quote(package.replace("_", "-") + "-tarav-harness")}
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["tarav"]

[tool.hatch.build.targets.wheel]
packages = [{quote("src/" + package)}]

[tool.uv.sources]
tarav = {{ path = {quote(str(source))}, editable = {str(source.is_dir()).lower()} }}

[tool.uv.workspace]
members = []
"""


# tarav.breadcrumb d6ba8cb735d3af7f6f1877c97fa39b76945f91ef13cab93971e91dbcfe147568
def _project_source(class_name: str, type_ship: str, type_name: str) -> str:
    return f'''"""This Project's code-owned specialization; extend it with Project operations."""

from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l1.project import TaravProject
from tarav.l1.project.workflow import PROJECT_WORKFLOW_SHIP


class {class_name}(TaravProject):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip({type_ship!r}),
            name={type_name!r},
            workflow=PROJECT_WORKFLOW_SHIP,
        )
'''
