"""Runtime bootstrap and subprocess launch for an explicit Project harness."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import runpy
import subprocess
import sys
from collections.abc import Sequence

from tarav.l0._core.errors import CliError
from tarav.l0.kernel import TaravEnvironment, entity
from tarav.l1.project import TaravProject
from tarav.l2.project.harness import ProjectHarness, ProjectHarnessError
from tarav.l3.runtime import create_runtime, set_runtime


def bootstrap(*, project_type: type[TaravProject], path: Path | str):
    """Trusted package source selects its Type; the marker supplies instance data."""
    environment = TaravEnvironment()
    environment.bind_type(entity(project_type).name, project_type)
    runtime = create_runtime(environment=environment)
    set_runtime(runtime)
    project = TaravProject.load_project(path=path)
    if type(project) is not project_type:
        raise ProjectHarnessError(
            "Project marker does not identify the launched package's exact Type"
        )
    return project, runtime


def run(
    *,
    path: Path | str = ".",
    code: str | None = None,
    file: Path | str | None = None,
    arguments: Sequence[str] = (),
) -> int:
    """Launch only the configured installed package in this Project's environment."""
    if code is not None and file is not None:
        raise ProjectHarnessError("Choose code or file, not both")
    harness = ProjectHarness.from_path(path=path)
    config = harness.configuration()
    harness.require_environment()
    command = [
        str(harness.interpreter),
        "-I",
        "-m",
        config["package"],
        "--project",
        str(harness.root),
    ]
    if code is not None:
        command.append("--code=" + code)
    elif file is not None:
        command.extend(["--file", str(Path(file).expanduser().resolve())])
    command.extend(["--", *arguments])
    try:
        return subprocess.run(command, cwd=harness.root, check=False).returncode
    except OSError as exc:
        raise ProjectHarnessError(
            f"Cannot launch Project environment: {harness.interpreter}: {exc}"
        ) from exc


def main(*, project_type: type[TaravProject], argv: Sequence[str] | None = None) -> int:
    """Entrypoint called by the installed Project package's __main__.py."""
    parser = argparse.ArgumentParser(
        description="Run code with this Project and its Tarav runtime."
    )
    parser.add_argument("--project", type=Path, required=True)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--code")
    source.add_argument("--file", type=Path)
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    try:
        project, runtime = bootstrap(project_type=project_type, path=args.project)
        arguments = (
            args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
        )
        sys.argv = [
            str(args.file) if args.file is not None else "<project-harness>",
            *arguments,
        ]
        namespace = {"project": project, "runtime": runtime, "__name__": "__main__"}
        if args.code is not None:
            exec(compile(args.code, "<project-harness>", "exec"), namespace)
        elif args.file is not None:
            runpy.run_path(str(args.file), init_globals=namespace, run_name="__main__")
        else:
            print(json.dumps(project.to_record(), indent=2))
        return 0
    except CliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


__all__ = ["bootstrap", "run", "main"]
