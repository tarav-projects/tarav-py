"""The Python environment that is currently running Tarav."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from tarav.l0._core.errors import CliError

from .runner import RunnerConfiguration


class PythonRunError(CliError):
    """A configured Python process could not be launched."""


def interpreter() -> Path:
    """Return the interpreter running Tarav.

    This is self-describing rather than discovered: whatever Python imported
    Tarav to reach this call is the environment a caller needs for a script
    that imports Tarav too. Under a tool install that is the tool environment;
    under a project run it is the project environment. Either answer is the
    honest one for the process asking.
    """

    return Path(sys.executable)


def environment_root() -> Path:
    """Return the prefix of the environment running Tarav."""

    return Path(sys.prefix)


def run_source(
    source: str,
    *,
    configuration: RunnerConfiguration,
    arguments: Sequence[str] = (),
) -> int:
    """Run inline source with the supplied configuration."""

    return run_python(["-c", source, *arguments], configuration=configuration)


def run_file(
    path: str | Path,
    *,
    configuration: RunnerConfiguration,
    arguments: Sequence[str] = (),
) -> int:
    """Run the script at ``path`` with the supplied configuration.

    The interpreter's own ``-`` convention is preserved: a path of ``-`` reads
    the script from standard input, which keeps heredocs usable for source too
    long to quote on one command line.
    """

    selected = str(path)
    if selected != "-":
        selected = str(Path(selected).expanduser().resolve())
    return run_python([selected, *arguments], configuration=configuration)


def run_python(
    arguments: Sequence[str], *, configuration: RunnerConfiguration
) -> int:
    """Run one explicit Python argument vector with a resolved configuration."""
    # tarav.breadcrumb f342326ee3e6fed178a6d6ed8cf66adf548b7a87b8ed42d841bf4efa853edfad

    if not isinstance(configuration, RunnerConfiguration):
        raise TypeError("configuration must be a RunnerConfiguration")
    try:
        return subprocess.run(
            [str(configuration.interpreter), *arguments],
            cwd=configuration.cwd,
            check=False,
        ).returncode
    except OSError as exc:
        raise PythonRunError(
            f"Cannot launch Python interpreter: {configuration.interpreter}: {exc}"
        ) from exc
