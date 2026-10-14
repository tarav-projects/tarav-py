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
from uuid import UUID, uuid4

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
    """A filesystem handler; discovery neither imports project code nor installs."""

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

    def __init__(
        self,
        root: Path | str,
        *,
        launch: ProjectLaunchConfiguration | None = None,
    ) -> None:
        super().__init__()
        self.root = Path(root).expanduser().resolve()
        self.directory = self.root / ".tarav"
        self.marker = self.directory / "project.json"
        self.launch = launch or ProjectLaunchConfiguration(
            root=self.root,
            manifest=self.directory / "pyproject.toml",
            environment=self.directory / "env",
            declared=False,
        )
        self.manifest = self.launch.manifest
        # tarav.breadcrumb d06d769f0a631a2b4912f8edbcf3a42aacdc491b6f0c596f513f941b493ebfd2
        self.env = self.launch.environment

    @classmethod
    def from_path(cls, *, path: Path | str = ".") -> ProjectHarness:
        launch = ProjectLaunchConfiguration.from_path(path)
        return cls(launch.root, launch=launch)

    @classmethod
    def _from_record(
        cls, record_data: ProjectHarness.RecordInterface
    ) -> ProjectHarness:
        return cls(record_data.root)

    def _to_record(self) -> dict[str, object]:
        return {**super()._to_record(), "root": str(self.root)}

    @property
    def interpreter(self) -> Path:
        return self.launch.interpreter

    def configuration(self) -> dict[str, str]:
        try:
            document = tomllib.loads(self.manifest.read_text(encoding="utf-8"))
            config = document["tool"]["tarav"]["harness"]
            _identifier(config["package"], "Package")
            _identifier(config["class_name"], "Class name")
            UUID(config["type_ship"])
            if not isinstance(config["type_name"], str) or not config["type_name"]:
                raise ValueError("type_name is required")
            return {
                key: config[key]
                for key in ("package", "class_name", "type_ship", "type_name")
            }
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            raise ProjectHarnessError(
                f"Invalid or absent Project harness configuration: {self.manifest}: {exc}"
            ) from exc

    def _harness_table(self) -> dict[str, object]:
        try:
            document = tomllib.loads(self.manifest.read_text(encoding="utf-8"))
            return document["tool"]["tarav"]["harness"]
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ProjectHarnessError(
                f"Invalid or absent Project harness configuration: {self.manifest}: {exc}"
            ) from exc

    # tarav.breadcrumb 11105a6b96fc632b26133674958a794af4684c7e6f5332e71b18f99c4348e561
    def project_types(self) -> tuple[str, ...]:
        """Trusted `module:Class` paths of the Project Types this environment runs.

        `[tool.tarav.harness] projects` lists several, so one library can
        provide several Project Types; otherwise the scaffolded package and
        class name the only one. Markers never select these import paths.
        """
        config = self._harness_table()
        if "projects" not in config:
            single = self.configuration()
            return (f"{single['package']}:{single['class_name']}",)
        specs = config["projects"]
        if not isinstance(specs, list) or not specs:
            raise ProjectHarnessError("Harness projects must be a non-empty list")
        for spec in specs:
            module, _, name = spec.partition(":") if isinstance(spec, str) else ("", "", "")
            if not module or not all(part.isidentifier() for part in module.split(".")):
                raise ProjectHarnessError(f"Harness project must be module:Class: {spec!r}")
            _identifier(name, "Project class name")
        return tuple(specs)

    def command(
        self,
        *,
        code: str | None = None,
        file: Path | str | None = None,
        arguments: Sequence[str] = (),
    ) -> list[str]:
        """Interpreter arguments that start this Project with its trusted Types."""
        if code is not None and file is not None:
            raise ProjectHarnessError("Choose code or file, not both")
        # A single scaffolded class starts through its package's own entry.
        self.project_types()
        entry = ("tarav.l3.project.launch" if "projects" in self._harness_table()
                 else self.configuration()["package"])
        command = ["-I", "-m", entry, "--project", str(self.root)]
        if code is not None:
            command.append("--code=" + code)
        elif file is not None:
            command.extend(["--file", str(Path(file).expanduser().resolve())])
        command.extend(["--", *arguments])
        return command

    def inspect(self) -> dict[str, object]:
        marker = load_project_marker(self.marker)
        scaffold = None
        if not self.launch.declared and self.manifest.exists():
            scaffold = (
                {"projects": list(self.project_types())}
                if "projects" in self._harness_table()
                else self.configuration()
            )
        owner = self.launch.harness_root
        launch = {
            "harness_root": str(owner),
            "manifest": str(self.manifest.relative_to(owner)),
            "environment": str(self.env.relative_to(owner)),
            "declared": self.launch.declared,
        }
        return {
            "root": str(self.root),
            "project_id": marker["project_id"],
            "marker": str(self.marker),
            "manifest": str(self.manifest),
            "environment": str(self.env),
            "interpreter": str(self.interpreter),
            "environment_present": self.env.exists(),
            "harness": scaffold or launch,
            "launch": launch,
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
        """Create missing harness files; preserve edited source and both identities.

        tarav_source explicitly selects a local Tarav checkout or wheel.
        Existing base/untyped markers require adopt; specialized markers are
        never reassigned. An existing harness may be retried with the same inputs.
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
                raise ProjectHarnessError(
                    f"Source is not the Tarav distribution: {source}"
                )
        elif not source.is_file() or source.suffix != ".whl":
            raise ProjectHarnessError(
                f"Tarav source must be a local checkout or wheel: {source}"
            )
        harness = cls(path)
        if not harness.root.is_dir():
            raise ProjectHarnessError(
                f"Project root must be an existing directory: {harness.root}"
            )
        harness._check_local_paths()
        existing = harness.manifest.exists()
        if existing:
            config = harness.configuration()
            if (config["package"], config["class_name"]) != (package, class_name):
                raise ProjectHarnessError(
                    "Existing harness package/class cannot be reassigned"
                )
            manifest_data = tomllib.loads(harness.manifest.read_text())
            selected_source = (
                manifest_data.get("tool", {})
                .get("uv", {})
                .get("sources", {})
                .get("tarav", {})
                .get("path")
            )
            if (
                selected_source is None
                or (harness.directory / selected_source).resolve() != source
            ):
                raise ProjectHarnessError(
                    "Existing harness dependency source differs; edit its manifest explicitly"
                )
        else:
            if (harness.directory / "src" / package).exists():
                raise ProjectHarnessError(
                    "Existing package source will not be adopted or overwritten"
                )
            config = {
                "package": package,
                "class_name": class_name,
                "type_ship": str(uuid4()),
                "type_name": f"Project.{package}.{class_name}",
            }
        marker = (
            load_project_marker(harness.marker) if harness.marker.exists() else None
        )
        if marker is not None:
            location = locate_record_type(marker)
            reference = RecordTypeReference.parse(location.value) if location else None
            own_type = reference is not None and (
                reference.ship == TypeShip(config["type_ship"])
                if reference.ship is not None
                else reference.label == config["type_name"]
            )
            if not own_type:
                from tarav.l2.project import Project

                if reference is not None and not any(
                    base.matches(reference) for base in (TaravProject, Project)
                ):
                    raise ProjectHarnessError(
                        "An already specialized Project Type cannot be overwritten"
                    )
                if not adopt:
                    raise ProjectHarnessError(
                        "Existing Project marker requires explicit adopt=True (--adopt)"
                    )
        if marker is None:
            marker = initialize_project_layout(harness.root, ensure=True)["marker"]
        # The manifest retains the generated class identity across partial setup.
        if not existing:
            harness.manifest.write_text(_manifest(config, source), encoding="utf-8")
        package_root = harness.directory / "src" / package
        package_root.mkdir(parents=True, exist_ok=True)
        files = {
            "__init__.py": f'"""Executable Project harness."""\n\nfrom .project import {class_name}\n\n__all__ = [{class_name!r}]\n',
            "project.py": _project_source(config),
            "__main__.py": f'from tarav.l3.project.harness import main\nfrom .project import {class_name}\n\nif __name__ == "__main__":\n    raise SystemExit(main(project_type={class_name}))\n',
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
        target[path_parts[-1]] = {
            "uuid": config["type_ship"],
            "label": config["type_name"],
        }
        if load_project_marker(harness.marker) != marker:
            atomic_write_json(harness.marker, marker)
        ignore = harness.directory / ".gitignore"
        current = ignore.read_text(encoding="utf-8") if ignore.exists() else ""
        if "/env/" not in current.splitlines():
            with ignore.open("a", encoding="utf-8") as stream:
                stream.write(
                    ("\n" if current and not current.endswith("\n") else "") + "/env/\n"
                )
        return harness

    def _check_local_paths(self) -> None:
        for name, path in (("manifest", self.manifest), ("environment", self.env)):
            try:
                path.resolve().relative_to(self.launch.harness_root)
            except ValueError as exc:
                raise ProjectHarnessError(
                    f"Harness {name} must not redirect outside the Project root"
                ) from exc

    def require_environment(self) -> None:
        self._check_local_paths()
        try:
            self.launch.require_environment()
        except ProjectRunnerError as exc:
            raise ProjectHarnessError(str(exc)) from exc

    def sync(self, *, python: Path | str | None = None) -> None:
        """Lock and install this harness into exactly .tarav/env using uv."""
        self._check_local_paths()
        if not self.manifest.is_file():
            raise ProjectHarnessError(
                f"Project harness manifest is absent: {self.manifest}"
            )
        if not self.launch.declared:
            self.project_types()
        uv = shutil.which("uv")
        if uv is None:
            raise ProjectHarnessError("uv is required to sync the Project harness")
        if self.env.exists():
            self.require_environment()
            if python is not None:
                raise ProjectHarnessError(
                    "Existing environment cannot be replaced by selecting another Python"
                )
            selected_python = self.interpreter
        else:
            selected_python = python if python is not None else sys.executable
        environment = {**os.environ, "UV_PROJECT_ENVIRONMENT": str(self.env)}
        environment.pop("VIRTUAL_ENV", None)
        try:
            subprocess.run(
                [
                    uv,
                    "sync",
                    "--project",
                    str(self.manifest.parent),
                    "--no-dev",
                    "--no-python-downloads",
                    "--python",
                    str(selected_python),
                ],
                cwd=self.root,
                env=environment,
                check=True,
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise ProjectHarnessError(
                f"Project harness sync failed; existing files are preserved: {self.root}: {exc}"
            ) from exc
        self.require_environment()


def _manifest(config: dict[str, str], source: Path) -> str:
    # JSON strings are also TOML basic strings, including escaped local paths.
    def quote(value: str) -> str:
        return json.dumps(value, ensure_ascii=False)

    return f"""[build-system]
requires = ["hatchling>=1.24.0"]
build-backend = "hatchling.build"

[project]
name = {quote(config["package"].replace("_", "-") + "-tarav-harness")}
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["tarav"]

[tool.hatch.build.targets.wheel]
packages = [{quote("src/" + config["package"])}]

[tool.uv.sources]
tarav = {{ path = {quote(str(source))}, editable = {str(source.is_dir()).lower()} }}

[tool.uv.workspace]
members = []

[tool.tarav.harness]
package = {quote(config["package"])}
class_name = {quote(config["class_name"])}
type_ship = {quote(config["type_ship"])}
type_name = {quote(config["type_name"])}
"""


# tarav.breadcrumb d6ba8cb735d3af7f6f1877c97fa39b76945f91ef13cab93971e91dbcfe147568
def _project_source(config: dict[str, str]) -> str:
    return f'''"""This Project's code-owned specialization; extend it with Project operations."""

from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l1.project import TaravProject
from tarav.l1.project.workflow import PROJECT_WORKFLOW_SHIP


class {config["class_name"]}(TaravProject):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip({config["type_ship"]!r}),
            name={config["type_name"]!r},
            workflow=PROJECT_WORKFLOW_SHIP,
        )
'''
