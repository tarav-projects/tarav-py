"""`tarav init --system`: create this machine's Tarav System Project.

The System Project is an ordinary Project at `~/Documents/tarav/system/`:
`.tarav/project.json`, its own Type subclassing `TaravSystemProject` in its
harness, its environment, and a Git repository. There is one per machine.
[#NOTE/TODISCUSS we discussed of making the sytem project to comprise ~/Documents/tarav itself, I think]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

from tarav.l0._core.errors import CliError
from tarav.l0._core.persistence import atomic_write_json
from tarav.l0.project import load_project_marker
from tarav.l2.project.harness import ProjectHarness
from tarav.l2.project.system import system_root

PACKAGE, CLASS_NAME = "tarav_system_harness", "SystemProject"
BASE = "tarav.l2.project.system:TaravSystemProject"
IGNORED = ("/.tarav/env/", "/.tarav/state/", "/.tarav/tmp/", "/.tarav/indexes/",
           "__pycache__/", "*.egg-info/", ".DS_Store")


# tarav.breadcrumb f2fc7bc4e6a1
# tarav.breadcrumb a694f14a6978
def init_system(*, tarav_source: Path | str, sync: bool = True) -> ProjectHarness:
    """Create the System Project; refuse when this machine already has one."""
    root = system_root()
    marker = root / ".tarav" / "project.json"
    if marker.exists():
        raise CliError(f"This machine already has a System Project: {root}")
    root.mkdir(parents=True, exist_ok=True)
    ProjectHarness.scaffold(path=root, package=PACKAGE, class_name=CLASS_NAME,
                            tarav_source=tarav_source, base=BASE)
    record = load_project_marker(marker)
    atomic_write_json(marker, {**record, "active": []})
    (root / ".gitignore").write_text("\n".join(IGNORED) + "\n", encoding="utf-8")
    if not (root / ".git").exists():
        subprocess.run(["git", "init", "-q", str(root)], check=True)
    harness = ProjectHarness.from_path(path=root)
    if sync:
        harness.sync()
    return harness


def _init(args: argparse.Namespace) -> int:
    harness = init_system(tarav_source=args.tarav_source)
    print(json.dumps(harness.inspect(), indent=2))
    return 0


def register_init_command(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "init", help="Create this machine's Tarav System Project (~/Documents/tarav/system).")
    parser.add_argument("--system", action="store_true", required=True,
                        help="The System Project: one per machine; refused when it exists.")
    parser.add_argument("--tarav-source", type=Path, required=True,
                        help="The local Tarav checkout or wheel its environment installs.")
    parser.set_defaults(handler=_init)


__all__ = ["init_system", "register_init_command"]
