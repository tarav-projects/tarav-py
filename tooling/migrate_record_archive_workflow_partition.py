"""Move one Record Archive workflow partition from its name to its Ship path.

The complete directory is renamed, preserving all nested Records and Git
repositories. Without --apply this command only reports the proposed move.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from tarav.runtime import get_runtime


def migrate(
    root: Path, workflow_name: str, *, apply: bool = False
) -> dict[str, object]:
    root = root.expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError(f"Archive root must be a directory: {root}")
    workflow = get_runtime().workflows.get(workflow_name)
    source = root / workflow.workflow_name
    target = root / str(workflow().id)
    if source.is_symlink():
        raise ValueError(f"Workflow partition must not be a symlink: {source}")
    if source.exists() and not source.is_dir():
        raise ValueError(f"Workflow partition must be a directory: {source}")
    if target.exists() or target.is_symlink():
        raise FileExistsError(f"Ship partition already exists: {target}")
    if not source.exists():
        raise FileNotFoundError(f"Workflow name partition does not exist: {source}")

    children = sorted(path.name for path in source.iterdir())
    if apply:
        source.rename(target)
    return {
        "source": str(source),
        "target": str(target),
        "children": children,
        "applied": apply,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--workflow", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(migrate(args.root, args.workflow, apply=args.apply), indent=2))
