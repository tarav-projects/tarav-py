"""Move typed Record Archive placement indexes out of main.json.

The runtime reads only the new format. Run once with an explicit root; without
--apply this command only reports the Archives that need migration.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

# tarav.breadcrumb 0361634799189d07f7de5ff879c3b66b4b565f6f29f23178847f1eee7fc14660
import tarav_bypass  # noqa: F401

from tarav.l0._core.persistence import atomic_write_json


def _old_object_path(value: str) -> None:
    path = Path(value)
    if len(path.parts) != 2 or path.parts[0] != "objects" or not path.name:
        raise ValueError(f"Invalid old Archive object path: {value}")


def migrate(root: Path, *, apply: bool = False) -> dict[str, object]:
    root = root.expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError(f"Archive root must be a directory: {root}")

    moves: list[tuple[Path, Path, dict[str, object], dict[str, str] | list[str]]] = []
    for main in sorted(root.rglob("main.json")):
        if ".git" in main.parts:
            continue
        record = json.loads(main.read_text(encoding="utf-8"))
        if not isinstance(record, dict):
            continue
        kind = record.get("type")
        if (
            kind
            not in {
                "Tarav.RecordArchive.Dictionary",
                "Tarav.RecordArchive.Vector",
            }
            or "entries" not in record
        ):
            continue
        entries = record["entries"]
        if kind == "Tarav.RecordArchive.Dictionary":
            if not isinstance(entries, dict) or any(
                not isinstance(name, str)
                or not name
                or name in {".", ".."}
                or "/" in name
                or "\\" in name
                or not isinstance(path, str)
                for name, path in entries.items()
            ):
                raise ValueError(f"Invalid Dictionary Archive entries: {main}")
        elif not isinstance(entries, list) or any(
            not isinstance(path, str) for path in entries
        ):
            raise ValueError(f"Invalid Vector Archive entries: {main}")

        paths = entries.values() if isinstance(entries, dict) else entries
        for path in paths:
            _old_object_path(path)
            if not (main.parent / path).is_file():
                raise ValueError(
                    f"Archive entry object is missing: {main.parent / path}"
                )
        target = main.with_name("entries.json")
        if (
            target.exists()
            and json.loads(target.read_text(encoding="utf-8")) != entries
        ):
            raise ValueError(f"Conflicting Archive entry registry: {target}")
        updated = {key: value for key, value in record.items() if key != "entries"}
        moves.append((main, target, updated, entries))

    if apply:
        for main, target, updated, entries in moves:
            atomic_write_json(target, entries)
            atomic_write_json(main, updated)

    return {"root": str(root), "archives": len(moves), "applied": apply}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(migrate(args.root, apply=args.apply), indent=2))
