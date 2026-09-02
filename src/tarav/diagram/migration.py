"""One-boundary migration from the Annotation-tape Diagram to typed Ships."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any

from tarav._core.persistence import atomic_write_json

from . import (
    BLOCK_SHIP_TYPE,
    CHATLAS_INDEX_ANNOTATION_TYPES,
    CHATLAS_INDEX_SHIP_TYPES,
    LINE_SHIP_TYPE,
    MODEL_SHIP_TYPE,
    NAMESPACE_CLASS,
    SCHEMA_VERSION,
    AnnotationDraft,
    DiagramBlockLocation,
    DiagramError,
    DiagramLocation,
    ShipDraft,
    _merge_ship_record,
)

JsonObject = dict[str, Any]
LEGACY_MODEL_ANNOTATION_TYPE = "Diagram.Model.Annotation"
LEGACY_BLOCK_ANNOTATION_TYPE = "Diagram.Block.Annotation"
LEGACY_LINE_ANNOTATION_TYPE = "Diagram.Line.Annotation"


@dataclass(frozen=True, slots=True)
class NamespaceMigrationReport:
    namespace_id: str
    source_commit: str
    ships: int
    editions: int
    annotations: int
    backup: str | None

    def to_dict(self) -> JsonObject:
        return {
            "namespace_id": self.namespace_id,
            "source_commit": self.source_commit,
            "ships": self.ships,
            "editions": self.editions,
            "annotations": self.annotations,
            "backup": self.backup,
        }


def migrate_namespace_v1(
    root: Path,
    *,
    backup: Path | None = None,
) -> NamespaceMigrationReport:
    """Advance one schema-v1 Namespace while retaining an optional raw backup."""

    resolved = root.expanduser().resolve()
    namespace_path = resolved / "namespace.json"
    annotations_root = resolved / "annotations"
    if not (resolved / ".git").is_dir() or not annotations_root.is_dir():
        raise DiagramError(f"Diagram Namespace repository is invalid: {resolved}")
    namespace = _read(namespace_path)
    if (
        namespace.get("class") != NAMESPACE_CLASS
        or namespace.get("schema_version") != 1
    ):
        raise DiagramError(f"Diagram Namespace is not schema v1: {resolved}")
    source_commit = _git(resolved, "rev-parse", "HEAD")
    source_records = {
        path.stem: _read(path) for path in sorted(annotations_root.glob("*.json"))
    }

    backup_path: Path | None = None
    if backup is not None:
        backup_path = backup.expanduser().resolve()
        if backup_path.exists():
            raise DiagramError(
                f"Diagram migration backup already exists: {backup_path}"
            )
        (backup_path / "annotations").mkdir(parents=True)
        shutil.copy2(namespace_path, backup_path / "namespace.json")
        for annotation_id in source_records:
            shutil.copy2(
                annotations_root / f"{annotation_id}.json",
                backup_path / "annotations" / f"{annotation_id}.json",
            )
        atomic_write_json(
            backup_path / "migration.json",
            {
                "class": "Tarav.Diagram.Attic.Legacy.Namespace",
                "schema_version": 1,
                "source": str(resolved),
                "source_namespace_id": namespace.get("id"),
                "source_commit": source_commit,
                "retained_at": _timestamp(),
                "reason": "Annotation-tape data retained before typed-Ship migration.",
            },
            ensure_ascii=False,
        )

    ship_records: dict[str, JsonObject] = {}
    standalone: dict[str, JsonObject] = {}
    for annotation_id, record in source_records.items():
        converted = _convert_entity_record(annotation_id, record)
        if converted is None:
            standalone[annotation_id] = _convert_standalone_record(record)
            continue
        current = ship_records.get(converted.id)
        merged, _, _ = _merge_ship_record(converted.id, current, converted.record)
        ship_records[converted.id] = merged

    shutil.rmtree(annotations_root)
    annotations_root.mkdir()
    ships_root = resolved / "ships"
    if ships_root.exists():
        shutil.rmtree(ships_root)
    ships_root.mkdir()
    for ship_id, record in ship_records.items():
        atomic_write_json(ships_root / f"{ship_id}.json", record, ensure_ascii=False)
    for annotation_id, record in standalone.items():
        atomic_write_json(
            annotations_root / f"{annotation_id}.json", record, ensure_ascii=False
        )

    migrated_namespace = dict(namespace)
    migrated_namespace.pop("allowed_types", None)
    migrated_namespace.update(
        {
            "schema_version": SCHEMA_VERSION,
            "allowed_ship_types": list(CHATLAS_INDEX_SHIP_TYPES),
            "allowed_annotation_types": list(CHATLAS_INDEX_ANNOTATION_TYPES),
        }
    )
    atomic_write_json(namespace_path, migrated_namespace, ensure_ascii=False)
    return NamespaceMigrationReport(
        str(namespace["id"]),
        source_commit,
        len(ship_records),
        sum(len(record.get("editions", [])) for record in ship_records.values()),
        len(standalone),
        str(backup_path) if backup_path is not None else None,
    )


def _convert_entity_record(annotation_id: str, record: JsonObject) -> ShipDraft | None:
    annotation = AnnotationDraft(annotation_id, record)
    payload = dict(annotation.record)
    annotation_type = payload.pop("type")
    if annotation_type == LEGACY_MODEL_ANNOTATION_TYPE:
        ship_id = str(payload.pop("model_ship"))
        return ShipDraft(
            ship_id,
            {"type": MODEL_SHIP_TYPE, "editions": [{"id": annotation_id, **payload}]},
        )
    if annotation_type == LEGACY_BLOCK_ANNOTATION_TYPE:
        location = DiagramBlockLocation.from_dict(payload.pop("location"))
        return ShipDraft(
            location.block_ship,
            {
                "type": BLOCK_SHIP_TYPE,
                "model_ship": location.model_ship,
                "editions": [{"id": annotation_id, **payload}],
            },
        )
    if annotation_type == LEGACY_LINE_ANNOTATION_TYPE:
        location = DiagramLocation.from_dict(payload.pop("location"))
        return ShipDraft(
            location.line_ship,
            {
                "type": LINE_SHIP_TYPE,
                "model_ship": location.model_ship,
                "block_ship": location.block_ship,
                "editions": [{"id": annotation_id, **payload}],
            },
        )
    return None


def _convert_standalone_record(record: JsonObject) -> JsonObject:
    converted = dict(record)
    if (
        converted.get("type") == "Diagram.Line.Gate.Annotation"
        and "target_annotation" in converted
    ):
        converted["target_edition"] = converted.pop("target_annotation")
    return converted


def _read(path: Path) -> JsonObject:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise DiagramError(f"Diagram JSON is not an object: {path}")
    return value


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ("git", "-C", str(root), *args),
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise DiagramError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("namespace")
    parser.add_argument("--backup")
    args = parser.parse_args(argv)
    report = migrate_namespace_v1(
        Path(args.namespace),
        backup=Path(args.backup) if args.backup else None,
    )
    print(json.dumps(report.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
