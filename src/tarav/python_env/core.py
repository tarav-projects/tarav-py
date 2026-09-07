"""The Python environment that is currently running Tarav."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path


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


def run_source(source: str, arguments: Sequence[str] = ()) -> int:
    """Run ``source`` with the Tarav interpreter and return its exit code."""

    return _execute(["-c", source, *arguments])


def run_file(path: str | Path, arguments: Sequence[str] = ()) -> int:
    """Run the script at ``path`` with the Tarav interpreter.

    The interpreter's own ``-`` convention is preserved: a path of ``-`` reads
    the script from standard input, which keeps heredocs usable for source too
    long to quote on one command line.
    """

    return _execute([str(path), *arguments])


def _execute(arguments: Sequence[str]) -> int:
    return subprocess.run([str(interpreter()), *arguments], check=False).returncode
