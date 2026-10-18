"""General configured Python runner CLI."""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path

from tarav.l0._core.errors import CliError
from tarav.l1.python_env import (
    CurrentRunnerConfigurator, RunRegistry, registry_root, run_python,
)
from tarav.l1.project.index import observe_project
from tarav.l1.usage import describe_text
from tarav.l2.project.runner import ProjectRunnerConfigurator

_LOG = logging.getLogger(__name__)


# tarav.breadcrumb 327c61e63acb
# tarav.breadcrumb e5466e3d2fb0
def _run(args: argparse.Namespace) -> int:
    if not args.arguments or args.arguments[0] != "--" or len(args.arguments) == 1:
        raise CliError("Expected Python arguments after -- (for example: tarav run -- script.py)")
    configurator = (
        CurrentRunnerConfigurator()
        if args.project is None
        else ProjectRunnerConfigurator.from_path(args.project)
    )
    configuration = configurator.configure()
    if args.project is not None:
        project = _project_identity(args.project)
        if project is not None:
            observe_project(project["root"])
    words = list(args.arguments[1:])
    registry = RunRegistry()
    entry, stdin = None, None
    try:
        partition, metadata, source, stdin = _registry_input(
            args, words, cwd=configuration.cwd, interpreter=configuration.interpreter)
        entry = registry.begin(partition=partition, source=source, metadata=metadata)
    except Exception:
        _LOG.warning("Could not describe run for the registry", exc_info=True)
    args.run_entry = entry.id if entry is not None else None
    exit_code = None
    try:
        # Only a run whose standard input was consumed here needs it replayed.
        replay = {} if stdin is None else {"stdin": stdin}
        exit_code = run_python(words, configuration=configuration, **replay)
        return exit_code
    finally:
        registry.finish(entry, exit_code=exit_code)


def _git_state(folder: Path) -> dict[str, object] | None:
    def git(*arguments: str) -> str:
        return subprocess.run(
            ["git", "-C", str(folder), *arguments], capture_output=True, text=True,
            check=True, timeout=3,
        ).stdout.strip()

    try:
        return {"commit": git("rev-parse", "HEAD"),
                "dirty": bool(git("status", "--porcelain", "--untracked-files=no"))}
    except (OSError, subprocess.SubprocessError):
        return None


def _project_identity(path: Path) -> dict[str, object] | None:
    import json
    for root in (Path(path).resolve(), *Path(path).resolve().parents):
        for marker in (root / ".tarav" / "project.json", root / "project.json"):
            try:
                record = json.loads(marker.read_text(encoding="utf-8"))
                return {"id": str(record["project_id"]), "root": str(root),
                        "name": str(record.get("name") or root.name)}
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                continue
    return None


# tarav.breadcrumb ea483ff850b7
def _registry_input(
    args: argparse.Namespace, words: list[str], *, cwd, interpreter,
) -> tuple[str | None, dict[str, object], bytes | None, bytes | None]:
    """What the registry keeps for this call: partition, metadata, source, replayed stdin."""
    from tarav import __version__

    calling = Path.cwd()
    working = Path(cwd) if cwd is not None else calling
    first, rest = words[0], words[1:]
    metadata: dict[str, object] = {
        "calling_directory": str(calling), "working_directory": str(working),
        "interpreter": str(interpreter), "tarav_version": __version__,
        "git": _git_state(calling),
    }
    source = stdin = None
    if first == "-c":
        metadata["mode"] = "code"
        source = rest[0].encode("utf-8") if rest else None
        rest = rest[1:]
    elif first == "-m":
        metadata.update(mode="module", module=rest[0] if rest else None)
        rest = rest[1:]
    elif first == "-":
        metadata["mode"] = "stdin"
        source = stdin = sys.stdin.buffer.read()
    elif first.startswith("-"):
        metadata["mode"] = "options"
        rest = words
    else:
        script = (working / Path(first).expanduser()).resolve()
        metadata.update(mode="script", script=str(script))
        try:
            source = script.read_bytes()
        except OSError:
            source = None
    metadata["arguments"] = rest
    project = _project_identity(args.project) if args.project is not None else None
    metadata["project"] = project
    return (project["id"] if project else None), metadata, source, stdin


# tarav.breadcrumb 69070277f687
def _describe_run(args: argparse.Namespace) -> dict[str, object]:
    words = list(args.arguments[1:]) if args.arguments[:1] == ["--"] else []
    use: dict[str, object] = {}
    if args.project is not None:
        use["project"] = str(args.project)
    if getattr(args, "run_entry", None):
        use["registry_entry"] = args.run_entry
    if not words:
        return use
    first, rest = words[0], words[1:]
    if first == "-c":
        use["mode"] = "code"
        use["code"] = describe_text(rest[0]) if rest else None
        rest = rest[1:]
    elif first == "-m":
        use["mode"] = "module"
        use["module"] = rest[0] if rest else None
        rest = rest[1:]
    elif first == "-":
        use["mode"] = "stdin"
    else:
        use["mode"] = "script"
        use["script"] = first
    if rest:
        use["script_args"] = len(rest)
    return use


def register_run_command(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "run",
        help="Run Python with current or Project configuration.",
        epilog=(
            "examples:\n"
            "  tarav run -- script.py --flag value\n"
            "  tarav run --project -- script.py\n"
            "  tarav run --project /path/to/project -- script.py\n"
            "  tarav run --project /path/to/project -- -c 'print(1)'\n\n"
            "The code each run executes is retained, by Project, under:\n"
            f"  {registry_root()}"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    # tarav.breadcrumb f2341073c5f3
    parser.add_argument(
        "--project",
        type=Path,
        nargs="?",
        const=Path("."),
        help="Search this directory and parents for a Project; optionally start at PATH.",
    )
    parser.add_argument(
        "arguments",
        nargs=argparse.REMAINDER,
        metavar="PYTHON_ARG",
        help="After --, arguments passed unchanged to Python.",
    )
    parser.set_defaults(handler=_run, usage_descriptor=_describe_run)


__all__ = ["register_run_command"]
