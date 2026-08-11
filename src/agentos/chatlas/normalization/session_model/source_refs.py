from __future__ import annotations

from typing import Any

from agentos.chatlas._payload_helpers import int_or_none, string_or_none


def primary_backing_artifact(session: dict[str, Any]) -> dict[str, Any] | None:
    primary = session.get("primary_backing_artifact")
    if isinstance(primary, dict):
        return primary
    artifacts = session.get("backing_artifacts")
    if not isinstance(artifacts, list):
        return None
    for artifact in artifacts:
        if isinstance(artifact, dict) and artifact.get("role") == "transcript":
            return artifact
    return None


def source_ref_id_for_artifact(
    artifact: dict[str, Any],
    *,
    sources: list[dict[str, object]],
) -> str | None:
    role = artifact.get("role")
    storage_kind = artifact.get("storage_kind")
    path = artifact.get("path")
    for source in sources:
        if (
            source.get("role") == role
            and source.get("storage_kind") == storage_kind
            and source.get("path") == path
        ):
            return string_or_none(source.get("source_ref_id"))
    return None


def source_ref_first_event_index(source_refs: object) -> int | None:
    for event_index in source_ref_event_indices(source_refs):
        return event_index
    return None


def source_ref_first_record_index(source_refs: object) -> int | None:
    for record_index in source_ref_record_indices(source_refs):
        return record_index
    return None


def source_ref_first_line(source_refs: object) -> int | None:
    if not isinstance(source_refs, list):
        return None
    for source_ref in source_refs:
        if not isinstance(source_ref, dict):
            continue
        line = int_or_none(source_ref.get("line"))
        if line is not None:
            return line
    return None


def source_ref_event_indices(source_refs: object) -> list[int]:
    if not isinstance(source_refs, list):
        return []
    event_indices: list[int] = []
    for source_ref in source_refs:
        if not isinstance(source_ref, dict):
            continue
        event_index = int_or_none(source_ref.get("event_index"))
        if event_index is not None:
            event_indices.append(event_index)
    return event_indices


def source_ref_record_indices(source_refs: object) -> list[int]:
    if not isinstance(source_refs, list):
        return []
    record_indices: list[int] = []
    for source_ref in source_refs:
        if not isinstance(source_ref, dict):
            continue
        record_index = int_or_none(source_ref.get("record_index"))
        if record_index is not None:
            record_indices.append(record_index)
    return record_indices


def record_native_dict(record: dict[str, object]) -> dict[str, object]:
    native = record.get("native")
    if isinstance(native, dict):
        return native
    derived: dict[str, object] = {}
    record_index = source_ref_first_record_index(record.get("source_refs"))
    if record_index is not None:
        derived["record_index"] = record_index
    event_index = source_ref_first_event_index(record.get("source_refs"))
    if event_index is not None:
        derived["event_index"] = event_index
    line = source_ref_first_line(record.get("source_refs"))
    if line is not None:
        derived["line"] = line
    for key in ("content_index", "request_index"):
        value = int_or_none(record.get(key))
        if value is not None:
            derived[key] = value
    return derived


def record_native_int_field(
    record: dict[str, object],
    key: str,
) -> int | None:
    value = int_or_none(record_native_dict(record).get(key))
    if value is not None:
        return value
    if key == "record_index":
        return source_ref_first_record_index(record.get("source_refs"))
    if key == "event_index":
        return source_ref_first_event_index(record.get("source_refs"))
    if key == "line":
        return source_ref_first_line(record.get("source_refs"))
    return None


def record_native_string_field(
    record: dict[str, object],
    key: str,
) -> str | None:
    return string_or_none(record_native_dict(record).get(key))
