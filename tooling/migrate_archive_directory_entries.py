"""Move Archive directory Records to the Kernel ``main.json`` convention.

This is an explicit one-time data migration and is never imported by runtime
readers. Existing Git history remains the recovery checkpoint. The working
tree may already contain changes to the entry Records themselves, but no
unrelated dirty paths are accepted.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
import subprocess

from tarav.l1.archive import Archive
from tarav.l1.archive.artifact_records import ArchiveRecord, ArtifactRecord, record_registry


def _git(records: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(records), *args],
        check=True,
        text=True,
        capture_output=True,
    ).stdout


def _dirty_paths(records: Path) -> set[Path]:
    output = _git(records, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    paths: set[Path] = set()
    entries = iter(output.split("\0"))
    for entry in entries:
        if not entry:
            continue
        status = entry[:2]
        paths.add(Path(entry[3:]))
        if "R" in status or "C" in status:
            origin = next(entries)
            if origin:
                paths.add(Path(origin))
    return paths


def _payload(path: Path, expected: type[ArchiveRecord | ArtifactRecord]) -> None:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, Mapping):
        raise ValueError(f"Archive directory entry is not an object: {path}")
    if value.get("schema_version") != 2:
        raise ValueError(f"Archive directory entry needs schema migration: {path}")
    if record_registry().resolve(value) is not expected:
        raise ValueError(f"Archive directory entry has the wrong Type: {path}")


def migrate(root: Path, *, apply: bool = False) -> dict[str, object]:
    archive_root = root.expanduser().resolve(strict=True)
    records = archive_root / "records"
    checkpoint = _git(records, "rev-parse", "HEAD").strip()

    moves: list[tuple[Path, Path, type[ArchiveRecord | ArtifactRecord]]] = []
    archive_source = records / "archive.json"
    archive_target = records / "main.json"
    if archive_source.exists():
        moves.append((archive_source, archive_target, ArchiveRecord))

    artifacts = records / "artifacts"
    if artifacts.is_dir():
        for source in sorted(artifacts.glob("*/registration.json")):
            moves.append((source, source.with_name("main.json"), ArtifactRecord))

    for source, target, expected in moves:
        if target.exists():
            raise ValueError(f"Archive directory contains both entry names: {target.parent}")
        _payload(source, expected)

    allowed_dirty = {source.relative_to(records) for source, _, _ in moves}
    unrelated_dirty = _dirty_paths(records) - allowed_dirty
    if unrelated_dirty:
        paths = ", ".join(str(path) for path in sorted(unrelated_dirty))
        raise ValueError(f"Archive Records contain unrelated changes: {paths}")

    if apply:
        for source, target, _ in moves:
            source.replace(target)
        archive = Archive.open(archive_root)
        for _, target, expected in moves:
            loaded = record_registry().load(target.parent)
            if type(loaded) is not expected:
                raise ValueError(f"Migrated entry resolved incorrectly: {target}")
        if archive.root != archive_root:
            raise ValueError("Migrated Archive root changed unexpectedly")

    return {
        "root": str(records),
        "checkpoint": checkpoint,
        "moved_files": len(moves),
        "applied": apply,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(migrate(args.root, apply=args.apply), indent=2))
