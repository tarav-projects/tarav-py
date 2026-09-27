"""Migrate Record Archives from direct object paths to Entry Records.

The command previews by default. --apply copies each old object to artifacts/,
writes its ArchiveEntry Record to records/, saves the old index, and replaces
entries.json last. It never deletes the old objects/ files.
"""

from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from tarav.l0._core.persistence import atomic_write_json
from tarav.l0.kernel import Ship
from tarav.archive.records import ArchiveEntry


OLD_INDEX_FILENAME = "entries.before-entry-records.json"
ARCHIVE_TYPES = {
    "Tarav.RecordArchive.Dictionary",
    "Tarav.RecordArchive.Vector",
}


@dataclass(frozen=True)
class EntryMove:
    source: Path
    artifact: Path
    record: Path
    record_data: dict[str, object]


@dataclass(frozen=True)
class ArchiveMove:
    index: Path
    old_index: dict[str, str] | list[str]
    new_index: dict[str, str] | list[str]
    entries: tuple[EntryMove, ...]


def _plan_archive(main: Path) -> ArchiveMove | None:
    data = json.loads(main.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("type") not in ARCHIVE_TYPES:
        return None
    archive = main.parent
    index = archive / "entries.json"
    old_index = json.loads(index.read_text(encoding="utf-8"))
    if data["type"] == "Tarav.RecordArchive.Dictionary":
        if not isinstance(old_index, dict) or any(
            not isinstance(name, str) or not isinstance(path, str)
            for name, path in old_index.items()
        ):
            raise ValueError(f"Invalid Dictionary Archive index: {index}")
        placements = list(old_index.items())
    else:
        if not isinstance(old_index, list) or any(
            not isinstance(path, str) for path in old_index
        ):
            raise ValueError(f"Invalid Vector Archive index: {index}")
        placements = [(str(position), path) for position, path in enumerate(old_index)]

    paths = [path for _, path in placements]
    if paths and all(path.startswith("records/") for path in paths):
        return None
    if (
        not paths
        and (archive / "records").is_dir()
        and (archive / "artifacts").is_dir()
    ):
        return None
    if any(not path.startswith("objects/") for path in paths):
        raise ValueError(f"Mixed or unknown Archive index paths: {index}")

    archive_id = Ship(data["id"])
    moves = []
    new_paths = []
    for placement, path in placements:
        relative = Path(path)
        if (
            len(relative.parts) != 2
            or relative.parts[0] != "objects"
            or relative.suffix != ".json"
        ):
            raise ValueError(f"Invalid old object path in {index}: {path}")
        source = archive / relative
        if not source.is_file() or source.is_symlink():
            raise ValueError(f"Missing or unsafe Archive object: {source}")
        artifact_relative = f"artifacts/{relative.name}"
        artifact = archive / artifact_relative
        key = uuid5(
            NAMESPACE_URL,
            f"Tarav.RecordArchive.Entry:{archive_id}:{placement}:{path}",
        ).hex
        record_relative = f"records/{key}.json"
        record = archive / record_relative
        record_data = ArchiveEntry(
            archive=archive_id, artifact=artifact_relative
        ).to_record()
        if artifact.exists() and artifact.read_bytes() != source.read_bytes():
            raise ValueError(f"Conflicting migrated artifact: {artifact}")
        if (
            record.exists()
            and json.loads(record.read_text(encoding="utf-8")) != record_data
        ):
            raise ValueError(f"Conflicting migrated Archive entry: {record}")
        moves.append(EntryMove(source, artifact, record, record_data))
        new_paths.append(record_relative)

    backup = archive / OLD_INDEX_FILENAME
    if backup.exists() and json.loads(backup.read_text(encoding="utf-8")) != old_index:
        raise ValueError(f"Conflicting old Archive index backup: {backup}")
    if isinstance(old_index, dict):
        new_index: dict[str, str] | list[str] = dict(
            zip(old_index, new_paths, strict=True)
        )
    else:
        new_index = new_paths
    return ArchiveMove(index, old_index, new_index, tuple(moves))


def migrate(root: Path, *, apply: bool = False) -> dict[str, object]:
    root = root.expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError(f"Archive root must be a directory: {root}")
    plans = []
    for main in sorted(root.rglob("main.json")):
        if ".git" in main.parts:
            continue
        plan = _plan_archive(main)
        if plan is not None:
            plans.append(plan)

    if apply:
        for plan in plans:
            archive = plan.index.parent
            (archive / "artifacts").mkdir(exist_ok=True)
            (archive / "records").mkdir(exist_ok=True)
            for entry in plan.entries:
                if not entry.artifact.exists():
                    shutil.copy2(entry.source, entry.artifact)
                if not entry.record.exists():
                    atomic_write_json(entry.record, entry.record_data)
            backup = archive / OLD_INDEX_FILENAME
            if not backup.exists():
                atomic_write_json(backup, plan.old_index)
            atomic_write_json(plan.index, plan.new_index)

    return {
        "root": str(root),
        "archives": len(plans),
        "entries": sum(len(plan.entries) for plan in plans),
        "applied": apply,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(json.dumps(migrate(args.root, apply=args.apply), indent=2))
