from __future__ import annotations

import json
from pathlib import Path

from tarav.chatlas.raw_archive import (
    RAW_PARTITION_MANIFEST_SCHEMA,
    RAW_PARTITION_MANIFEST_SCHEMA_VERSION,
    _load_raw_partition_manifest,
    migrate_raw_partition_manifests,
)


def test_raw_manifest_migration_is_explicit_and_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "raw" / "codex" / "partition-one" / "manifest.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "class": "agentos_chatlas.raw_partition_manifest",
                "schema_version": 1,
                "provider": "codex",
                "home": "/provider/home",
            }
        ),
        encoding="utf-8",
    )

    assert _load_raw_partition_manifest(path) is None

    first = migrate_raw_partition_manifests(tmp_path / "raw")
    migrated = _load_raw_partition_manifest(path)

    assert first["migrated"] == [str(path)]
    assert migrated == {
        "schema": RAW_PARTITION_MANIFEST_SCHEMA,
        "schema_version": RAW_PARTITION_MANIFEST_SCHEMA_VERSION,
        "provider": "codex",
        "home": "/provider/home",
    }

    second = migrate_raw_partition_manifests(tmp_path / "raw")
    assert second["migrated"] == []
    assert second["current"] == [str(path)]
