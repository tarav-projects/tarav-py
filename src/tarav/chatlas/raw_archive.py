from __future__ import annotations

import json
import os
from pathlib import Path
from shutil import copy2
import stat
from typing import TYPE_CHECKING, Any, Literal

from tarav.l0._core.errors import CliError
from tarav.l0._core.persistence import atomic_write_json
from tarav.agent.primitives import SessionSource
from tarav.chatlas._cache_io import write_text_if_changed

if TYPE_CHECKING:
    from tarav.chatlas.provider_home_adapter import ChatlasDeltaSession, ChatlasProviderInstance

RAW_PARTITION_MANIFEST_SCHEMA = "tarav.chatlas.raw-partition-manifest"
RAW_PARTITION_MANIFEST_SCHEMA_VERSION = 2
_LEGACY_RAW_PARTITION_MANIFEST_CLASS = "agentos_chatlas.raw_partition_manifest"
RAW_PARTITION_MANIFEST_FILENAME = "manifest.json"

CopyResult = Literal["added", "updated", "unchanged", "skipped"]


def _copy_delta_session_sources(
    delta_session: "ChatlasDeltaSession",
    *,
    raw_root: Path,
    empty_report: dict[str, int],
) -> dict[str, int]:
    report = dict(empty_report)
    for source in delta_session.sources:
        report["scanned_source_count"] += 1
        if source.path.is_dir():
            report["skipped_source_count"] += 1
            continue
        destination = _copied_source_path(
            delta_session.session.provider_instance,
            raw_root=raw_root,
            source_path=source.path,
        )
        copy_result = _copy_file_if_changed(source.path, destination)
        if copy_result == "added":
            report["copied_file_count"] += 1
            report["added_file_count"] += 1
        elif copy_result == "updated":
            report["copied_file_count"] += 1
            report["updated_file_count"] += 1
        elif copy_result == "unchanged":
            report["unchanged_file_count"] += 1
        else:
            report["skipped_source_count"] += 1
    return report


def _copied_paths_for_sources(
    instance: "ChatlasProviderInstance",
    *,
    raw_root: Path,
    sources: tuple[SessionSource, ...],
) -> tuple[Path, ...]:
    return tuple(
        _copied_source_path(instance, raw_root=raw_root, source_path=source.path)
        for source in sources
    )


def _copied_source_path(
    instance: "ChatlasProviderInstance",
    *,
    raw_root: Path,
    source_path: Path,
) -> Path:
    if instance.agent.home is not None:
        try:
            relative = source_path.resolve().relative_to(instance.agent.home.resolve())
        except ValueError:
            relative = _absolute_path_relpath(source_path)
        return raw_root / instance.partition_key / "home" / relative
    return raw_root / instance.partition_key / "paths" / _absolute_path_relpath(source_path)


def _absolute_path_relpath(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved.is_absolute():
        try:
            relative_text = os.path.relpath(str(resolved), resolved.anchor)
        except ValueError:
            return Path(resolved.name)
        return Path(relative_text)
    return resolved


def _copy_file_if_changed(source_path: Path, destination_path: Path) -> CopyResult:
    try:
        if not source_path.is_file():
            return "skipped"
        if destination_path.is_file() and _file_metadata_matches(source_path, destination_path):
            return "unchanged"
        existed = destination_path.exists() or destination_path.is_symlink()
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        copy2(source_path, destination_path)
    except FileNotFoundError:
        return "skipped"
    except OSError as exc:
        raise CliError(f"failed to copy Chatlas raw source {source_path}: {exc}") from exc
    return "updated" if existed else "added"


def _file_metadata_matches(left: Path, right: Path) -> bool:
    try:
        left_stat = left.stat()
        right_stat = right.stat()
    except OSError:
        return False
    return (
        int(left_stat.st_mtime_ns) == int(right_stat.st_mtime_ns)
        and int(left_stat.st_size) == int(right_stat.st_size)
    )


def _raw_partition_manifest_path(raw_root: Path, *, instance: "ChatlasProviderInstance") -> Path:
    return raw_root / instance.partition_key / RAW_PARTITION_MANIFEST_FILENAME


def _load_raw_partition_manifest(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if (
        not isinstance(payload, dict)
        or payload.get("schema") != RAW_PARTITION_MANIFEST_SCHEMA
        or payload.get("schema_version") != RAW_PARTITION_MANIFEST_SCHEMA_VERSION
    ):
        return None
    return payload


def _raw_partition_manifest_string(manifest: dict[str, Any] | None, field_name: str) -> str | None:
    if manifest is None:
        return None
    value = manifest.get(field_name)
    return value if isinstance(value, str) and value else None


def _raw_partition_manifest_home(raw_root: Path, *, instance: "ChatlasProviderInstance") -> str | None:
    manifest = _load_raw_partition_manifest(_raw_partition_manifest_path(raw_root, instance=instance))
    if manifest is None:
        return None
    home = manifest.get("home")
    return home if isinstance(home, str) and home else None


def _raw_partition_manifest_payload(
    instance: "ChatlasProviderInstance",
    *,
    raw_root: Path,
    provider_instance_home: str | None,
) -> dict[str, Any]:
    raw_home = instance.raw_home(raw_root)
    source_roots: list[dict[str, str]] = []
    if provider_instance_home is not None and raw_home is not None:
        source_roots.append(
            {
                "role": "home",
                "source_root": provider_instance_home,
                "raw_root": str(raw_home),
            }
        )
    return {
        "schema": RAW_PARTITION_MANIFEST_SCHEMA,
        "schema_version": RAW_PARTITION_MANIFEST_SCHEMA_VERSION,
        "provider": instance.provider,
        "provider_instance_fingerprint": instance.fingerprint,
        "instance": instance.instance,
        "home": provider_instance_home,
        "raw_home": str(raw_home) if raw_home is not None else None,
        "home_source": "configured_agent_home" if provider_instance_home is not None else None,
        "source_roots": source_roots,
    }


def _create_raw_partition_manifest_if_missing(
    instance: "ChatlasProviderInstance",
    *,
    raw_root: Path,
    provider_instance_home: str | None,
) -> None:
    path = _raw_partition_manifest_path(raw_root, instance=instance)
    if path.exists():
        return
    payload = _raw_partition_manifest_payload(
        instance,
        raw_root=raw_root,
        provider_instance_home=provider_instance_home,
    )
    write_text_if_changed(path, json.dumps(payload, sort_keys=True, indent=2) + "\n")


def migrate_raw_partition_manifests(raw_root: Path) -> dict[str, object]:
    """Explicitly migrate retained v1 manifests; ordinary readers stay strict."""

    migrated: list[str] = []
    current: list[str] = []
    unrecognized: list[str] = []
    for path in sorted(raw_root.glob(f"*/*/{RAW_PARTITION_MANIFEST_FILENAME}")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            unrecognized.append(str(path))
            continue
        if not isinstance(payload, dict):
            unrecognized.append(str(path))
            continue
        if (
            payload.get("schema") == RAW_PARTITION_MANIFEST_SCHEMA
            and payload.get("schema_version") == RAW_PARTITION_MANIFEST_SCHEMA_VERSION
        ):
            current.append(str(path))
            continue
        if (
            payload.get("class") != _LEGACY_RAW_PARTITION_MANIFEST_CLASS
            or payload.get("schema_version") != 1
        ):
            unrecognized.append(str(path))
            continue
        migrated_payload = dict(payload)
        migrated_payload.pop("class")
        migrated_payload["schema"] = RAW_PARTITION_MANIFEST_SCHEMA
        migrated_payload["schema_version"] = RAW_PARTITION_MANIFEST_SCHEMA_VERSION
        atomic_write_json(path, migrated_payload, ensure_ascii=False)
        migrated.append(str(path))
    return {
        "status": "ok" if not unrecognized else "attention",
        "command": "chatlas index migrate",
        "raw_root": str(raw_root),
        "migrated": migrated,
        "current": current,
        "unrecognized": unrecognized,
    }


def _path_metadata_signature(path: Path) -> dict[str, object]:
    signature: dict[str, object] = {"path": str(path)}
    try:
        source_stat = path.stat()
    except OSError:
        signature["exists"] = False
        return signature

    signature["exists"] = True
    signature["mtime_ns"] = int(source_stat.st_mtime_ns)
    mode = source_stat.st_mode
    if stat.S_ISREG(mode):
        signature["size"] = int(source_stat.st_size)
    elif stat.S_ISDIR(mode):
        signature["storage_kind"] = "directory"
    else:
        signature["storage_kind"] = "other"
    return signature
