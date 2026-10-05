"""`python -m tarav.l3.project.launch`: start a Project in its harness environment.

The trusted Project Types come from the harness manifest, which is code the
environment's owner wrote; the marker only selects one of them.
"""

from __future__ import annotations

import argparse
from importlib import import_module
import sys
from collections.abc import Sequence

from tarav.l0._core.errors import CliError
from tarav.l2.project.harness import ProjectHarness

from .harness import main


def trusted_types(path) -> tuple[type, ...]:
    types = []
    for spec in ProjectHarness.from_path(path=path).project_types():
        module, _, name = spec.partition(":")
        types.append(getattr(import_module(module), name))
    return tuple(types)


def launch(argv: Sequence[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--project", required=True)
    known, _ = parser.parse_known_args(arguments)
    try:
        types = trusted_types(known.project)
    except (CliError, ImportError, AttributeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return main(project_type=types, argv=arguments)


if __name__ == "__main__":
    raise SystemExit(launch())
