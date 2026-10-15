"""Runtime bootstrap and subprocess launch for an explicit Project harness."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import runpy
import sys
from collections.abc import Sequence

from tarav.l0._core.errors import CliError
from tarav.l0.kernel import TaravEnvironment
from tarav.l1.project import TaravProject
from tarav.l1.python_env import run_python
from tarav.l2.project.harness import ProjectHarness, ProjectHarnessError
from tarav.l2.project.runner import ProjectRunnerConfigurator, ProjectRunnerError
from tarav.l3.runtime import create_runtime, set_runtime


def bootstrap(*, path: Path | str):
    """A runtime for this process, and the Project its project.json describes."""
    runtime = create_runtime(environment=TaravEnvironment())
    set_runtime(runtime)
    return TaravProject.load_project(path=path), runtime


def run(
    *,
    path: Path | str = ".",
    code: str | None = None,
    file: Path | str | None = None,
    arguments: Sequence[str] = (),
) -> int:
    """Launch this Project's harness environment with its trusted Project Types."""
    harness = ProjectHarness.from_path(path=path)
    command = harness.command(code=code, file=file, arguments=arguments)
    try:
        configuration = ProjectRunnerConfigurator(harness.launch).configure()
    except ProjectRunnerError as exc:
        raise ProjectHarnessError(str(exc)) from exc
    return run_python(command, configuration=configuration)


def main(argv: Sequence[str] | None = None) -> int:
    """Run code with the Project at --project, loaded as its harness says."""
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
        project, runtime = bootstrap(path=args.project)
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
            print(json.dumps(project.records.to_record(), indent=2))
        return 0
    except (CliError, TypeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


__all__ = ["bootstrap", "run", "main"]
