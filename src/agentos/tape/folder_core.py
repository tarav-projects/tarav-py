from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError, ValidationError

from agentos._core.clock import utc_now_iso as _utc_now_iso
from agentos._core.errors import CliError
from agentos._core.path_validation import validate_string_for_path
from agentos.tape.naming import period_prefix_for_strategy

MANIFEST_FILENAME = "tape.manifest.json"
SEGMENTS_DIRNAME = "segments"
STAGING_DIRNAME = "staging"

MANIFEST_RECORD_CLASS = "tape.folder.config"
SEGMENT_METADATA_CLASS = "tape.segment.metadata"
STAGING_METADATA_CLASS = "tape.staging.metadata"
MINIMAL_RECORD_KEYS = frozenset({"class", "writer", "created_at"})
ALLOWED_RECORD_EXTRA_KEYS = frozenset({"data"})

SUPPORTED_NAMING_STRATEGIES = ("sequential", "monthly", "daily")

_SEQUENTIAL_SEGMENT_RE = re.compile(r"^(\d+)\.jsonl$")
_MONTHLY_SEGMENT_RE = re.compile(r"^(\d{4})\.jsonl$")
_DAILY_SEGMENT_RE = re.compile(r"^(\d{6})\.jsonl$")


@dataclass(frozen=True)
class TapeFolderConfig:
    tape_name: str
    naming_strategy: str
    max_records_per_segment: int
    tape_class: str | None = None
    allowed_classes: list[str] | None = None
    data_schema: dict[str, object] | None = None
    format_version: str = "1"


@dataclass(frozen=True)
class LocatedRecord:
    source_kind: str
    source_file: Path
    line_no: int
    record: dict[str, object]


def bootstrap_tape_folder(
    root_path: Path,
    *,
    tape_name: str,
    naming_strategy: str,
    max_records_per_segment: int,
    tape_class: str | None = None,
    allowed_classes: list[str] | None = None,
    data_schema: dict[str, object] | None = None,
    ensure: bool = False,
) -> tuple[TapeFolderConfig, bool]:
    root = root_path.expanduser().resolve()
    _validate_tape_name(tape_name)
    _validate_naming_strategy(naming_strategy)
    _validate_max_records_per_segment(max_records_per_segment)
    normalized_tape_class = _normalize_tape_class(tape_class)
    normalized_allowed_classes = _normalize_allowed_classes(allowed_classes)
    normalized_data_schema = _normalize_data_schema(data_schema)

    if root.exists() and not root.is_dir():
        raise CliError(f"tape root path exists and is not a directory: {root}")

    manifest_path = root / MANIFEST_FILENAME
    if manifest_path.exists():
        if not ensure:
            raise CliError(f"tape folder already exists: {root}")
        config = load_tape_folder_config(root)
        return config, False

    root.mkdir(parents=True, exist_ok=True)
    (root / SEGMENTS_DIRNAME).mkdir(parents=True, exist_ok=True)
    (root / STAGING_DIRNAME).mkdir(parents=True, exist_ok=True)

    config = TapeFolderConfig(
        tape_name=tape_name,
        naming_strategy=naming_strategy,
        max_records_per_segment=max_records_per_segment,
        tape_class=normalized_tape_class,
        allowed_classes=normalized_allowed_classes,
        data_schema=normalized_data_schema,
    )
    _write_manifest(root, config)
    return config, True


def load_tape_folder_config(root_path: Path) -> TapeFolderConfig:
    root = root_path.expanduser().resolve()
    manifest_path = root / MANIFEST_FILENAME
    if not manifest_path.exists():
        raise CliError(f"tape manifest does not exist: {manifest_path}")
    if not manifest_path.is_file():
        raise CliError(f"tape manifest path is not a file: {manifest_path}")

    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CliError(f"invalid tape manifest JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise CliError("tape manifest must be a JSON object")
    if payload.get("class") != MANIFEST_RECORD_CLASS:
        raise CliError(f"tape manifest must have class={MANIFEST_RECORD_CLASS}")

    config_obj = payload.get("config")
    if not isinstance(config_obj, dict):
        raise CliError("tape manifest config must be a JSON object")

    tape_name = str(config_obj.get("tape_name", "")).strip()
    naming_strategy = str(config_obj.get("naming_strategy", "")).strip()
    max_records_raw = config_obj.get("max_records_per_segment")
    tape_class_raw = config_obj.get("tape.class")
    allowed_classes_raw = config_obj.get("allowed_classes")
    data_schema_raw = config_obj.get("data_schema")
    format_version = str(payload.get("format_version", "1")).strip() or "1"

    _validate_tape_name(tape_name)
    _validate_naming_strategy(naming_strategy)
    if not isinstance(max_records_raw, int):
        raise CliError("tape manifest config.max_records_per_segment must be an integer")
    _validate_max_records_per_segment(max_records_raw)
    normalized_tape_class = _normalize_tape_class(tape_class_raw)
    normalized_allowed_classes = _normalize_allowed_classes(allowed_classes_raw)
    normalized_data_schema = _normalize_data_schema(data_schema_raw)

    segments_dir = root / SEGMENTS_DIRNAME
    staging_dir = root / STAGING_DIRNAME
    if not segments_dir.exists() or not segments_dir.is_dir():
        raise CliError(f"tape segments directory does not exist: {segments_dir}")
    if not staging_dir.exists() or not staging_dir.is_dir():
        raise CliError(f"tape staging directory does not exist: {staging_dir}")

    return TapeFolderConfig(
        tape_name=tape_name,
        naming_strategy=naming_strategy,
        max_records_per_segment=max_records_raw,
        tape_class=normalized_tape_class,
        allowed_classes=normalized_allowed_classes,
        data_schema=normalized_data_schema,
        format_version=format_version,
    )


def append_staging_record(
    root_path: Path,
    *,
    writer_id: str,
    record_class: str,
    created_at: str | None = None,
    data: dict[str, object] | None = None,
) -> tuple[Path, dict[str, object]]:
    config = load_tape_folder_config(root_path)

    normalized_writer = _normalize_writer_id(writer_id)
    normalized_class = _normalize_record_class(record_class)
    normalized_created_at = _normalize_created_at(created_at)
    normalized_data = _normalize_record_data(data)

    root = root_path.expanduser().resolve()
    staging_dir = root / STAGING_DIRNAME
    staging_path = staging_dir / f"{normalized_writer}.jsonl"

    existing_metadata: dict[str, object] | None = None
    if staging_path.exists():
        existing_metadata, _ = _read_staging_records(staging_path)
    else:
        existing_metadata = {
            "class": STAGING_METADATA_CLASS,
            "created_at": _utc_now_iso(),
            "writer": writer_id,
            "staging_filename": staging_path.name,
        }
        _write_jsonl_file(staging_path, [existing_metadata])

    if existing_metadata is None:
        raise CliError(f"failed to initialize staging metadata for file: {staging_path}")

    record = {
        "class": normalized_class,
        "writer": writer_id,
        "created_at": normalized_created_at,
    }
    if normalized_data is not None:
        record["data"] = normalized_data
    _validate_minimal_record(record)
    _validate_record_class_allowed(normalized_class, allowed_classes=config.allowed_classes)
    _validate_record_data_schema(record, data_schema=config.data_schema)
    _append_jsonl_line(staging_path, record)
    return staging_path, record


def consolidate_staging_records(root_path: Path, *, limit: int | None = None) -> dict[str, object]:
    config = load_tape_folder_config(root_path)
    root = root_path.expanduser().resolve()
    staging_dir = root / STAGING_DIRNAME
    segments_dir = root / SEGMENTS_DIRNAME

    if limit is not None and limit <= 0:
        raise CliError("limit must be > 0 when provided")

    staging_files = sorted(path for path in staging_dir.iterdir() if path.name.endswith(".jsonl"))
    staged_by_file: dict[Path, tuple[dict[str, object], list[LocatedRecord]]] = {}
    all_records: list[LocatedRecord] = []

    for staging_path in staging_files:
        metadata, records = _read_staging_records(staging_path)
        staged_by_file[staging_path] = (metadata, records)
        all_records.extend(records)

    if not all_records:
        return {
            "processed_count": 0,
            "remaining_count": 0,
            "segments_touched": [],
            "staging_files": len(staging_files),
        }

    to_process = all_records if limit is None else all_records[:limit]
    processed_line_numbers: dict[Path, set[int]] = {}
    for item in to_process:
        line_numbers = processed_line_numbers.setdefault(item.source_file, set())
        line_numbers.add(item.line_no)

    segment_paths = sorted(path for path in segments_dir.iterdir() if path.name.endswith(".jsonl"))
    segment_counts: dict[str, int] = {}
    segment_names: list[str] = []
    for segment_path in segment_paths:
        _validate_segment_header(segment_path)
        segment_counts[segment_path.name] = _count_segment_data_records(segment_path)
        segment_names.append(segment_path.name)

    touched_segments: set[str] = set()
    for item in to_process:
        created_at = str(item.record.get("created_at", "")).strip()
        timestamp = _parse_timetag(created_at)
        target_name = _resolve_target_segment_name(
            strategy=config.naming_strategy,
            max_records_per_segment=config.max_records_per_segment,
            segment_names=segment_names,
            segment_counts=segment_counts,
            created_at=timestamp,
        )
        target_path = segments_dir / target_name
        if not target_path.exists():
            _create_segment_file(target_path, naming_strategy=config.naming_strategy)
        _append_jsonl_line(target_path, item.record)
        segment_counts[target_name] = segment_counts.get(target_name, 0) + 1
        touched_segments.add(target_name)

    for staging_path, (metadata, records) in staged_by_file.items():
        processed_for_file = processed_line_numbers.get(staging_path, set())
        remaining_records = [record.record for record in records if record.line_no not in processed_for_file]
        _write_jsonl_file(staging_path, [metadata, *remaining_records])

    return {
        "processed_count": len(to_process),
        "remaining_count": len(all_records) - len(to_process),
        "segments_touched": sorted(touched_segments),
        "staging_files": len(staging_files),
    }


def read_committed_records(root_path: Path) -> list[LocatedRecord]:
    _ = load_tape_folder_config(root_path)
    root = root_path.expanduser().resolve()
    segments_dir = root / SEGMENTS_DIRNAME
    segment_paths = sorted(path for path in segments_dir.iterdir() if path.name.endswith(".jsonl"))

    records: list[LocatedRecord] = []
    for segment_path in segment_paths:
        _, segment_records = _read_segment_records(segment_path)
        records.extend(segment_records)
    return records


def read_best_effort_records(root_path: Path) -> list[LocatedRecord]:
    committed = read_committed_records(root_path)

    root = root_path.expanduser().resolve()
    staging_dir = root / STAGING_DIRNAME
    staging_paths = sorted(path for path in staging_dir.iterdir() if path.name.endswith(".jsonl"))
    staging_records: list[LocatedRecord] = []
    for staging_path in staging_paths:
        _, records = _read_staging_records(staging_path)
        staging_records.extend(records)

    merged = [*committed, *staging_records]
    merged.sort(key=_best_effort_sort_key)
    return merged


def verify_segment_headers(root_path: Path) -> dict[str, object]:
    _ = load_tape_folder_config(root_path)
    root = root_path.expanduser().resolve()
    segments_dir = root / SEGMENTS_DIRNAME
    segment_paths = sorted(path for path in segments_dir.iterdir() if path.name.endswith(".jsonl"))
    for segment_path in segment_paths:
        _validate_segment_header(segment_path)
    return {
        "segment_count": len(segment_paths),
        "segment_files": [segment_path.name for segment_path in segment_paths],
    }


def lint_minimal_schema(root_path: Path, *, max_findings: int = 200) -> dict[str, object]:
    config = load_tape_folder_config(root_path)
    root = root_path.expanduser().resolve()
    segments_dir = root / SEGMENTS_DIRNAME
    staging_dir = root / STAGING_DIRNAME

    if max_findings <= 0:
        raise CliError("max_findings must be > 0")

    findings: list[dict[str, object]] = []
    truncated = False
    dropped_findings = 0
    total_records = 0
    valid_records = 0

    def add_finding(
        *,
        code: str,
        message: str,
        source_kind: str,
        source_file: Path,
        line_no: int,
    ) -> None:
        nonlocal truncated, dropped_findings
        if len(findings) >= max_findings:
            truncated = True
            dropped_findings += 1
            return
        findings.append(
            {
                "severity": "error",
                "code": code,
                "message": message,
                "source_kind": source_kind,
                "source_file": source_file.as_posix(),
                "line_no": line_no,
            }
        )

    segment_paths = sorted(path for path in segments_dir.iterdir() if path.name.endswith(".jsonl"))
    for segment_path in segment_paths:
        try:
            _ = _validate_segment_header(segment_path)
        except CliError as exc:
            add_finding(
                code="invalid-segment-header",
                message=str(exc),
                source_kind="committed",
                source_file=segment_path,
                line_no=1,
            )
            continue

        with segment_path.open("r", encoding="utf-8") as handle:
            for line_no, raw_line in enumerate(handle, start=1):
                if line_no == 1:
                    continue
                stripped = raw_line.strip()
                if not stripped:
                    continue
                total_records += 1
                try:
                    record = _parse_json_object_line(stripped, path=segment_path, line_no=line_no)
                    _validate_minimal_record(record)
                    _validate_record_class_allowed(
                        str(record.get("class", "")).strip(),
                        allowed_classes=config.allowed_classes,
                    )
                except CliError as exc:
                    add_finding(
                        code="invalid-record",
                        message=str(exc),
                        source_kind="committed",
                        source_file=segment_path,
                        line_no=line_no,
                    )
                    continue
                valid_records += 1

    staging_paths = sorted(path for path in staging_dir.iterdir() if path.name.endswith(".jsonl"))
    for staging_path in staging_paths:
        try:
            if not staging_path.exists():
                raise CliError(f"staging file does not exist: {staging_path}")
            if not staging_path.is_file():
                raise CliError(f"staging path is not a file: {staging_path}")

            with staging_path.open("r", encoding="utf-8") as handle:
                first_line = handle.readline()
            if not first_line:
                raise CliError(f"staging file is empty: {staging_path}")

            metadata = _parse_json_object_line(first_line, path=staging_path, line_no=1)
            if metadata.get("class") != STAGING_METADATA_CLASS:
                raise CliError(f"first staging record must be class={STAGING_METADATA_CLASS}: {staging_path}")
            declared = str(metadata.get("staging_filename", "")).strip()
            if declared != staging_path.name:
                raise CliError(
                    f"staging metadata filename mismatch: declared={declared} actual={staging_path.name}"
                )
        except CliError as exc:
            add_finding(
                code="invalid-staging-header",
                message=str(exc),
                source_kind="staging",
                source_file=staging_path,
                line_no=1,
            )
            continue

        with staging_path.open("r", encoding="utf-8") as handle:
            for line_no, raw_line in enumerate(handle, start=1):
                if line_no == 1:
                    continue
                stripped = raw_line.strip()
                if not stripped:
                    continue
                total_records += 1
                try:
                    record = _parse_json_object_line(stripped, path=staging_path, line_no=line_no)
                    _validate_minimal_record(record)
                    _validate_record_class_allowed(
                        str(record.get("class", "")).strip(),
                        allowed_classes=config.allowed_classes,
                    )
                except CliError as exc:
                    add_finding(
                        code="invalid-record",
                        message=str(exc),
                        source_kind="staging",
                        source_file=staging_path,
                        line_no=line_no,
                    )
                    continue
                valid_records += 1

    errors = len(findings)
    return {
        "total_records": total_records,
        "valid_records": valid_records,
        "findings": findings,
        "summary": {
            "errors": errors,
            "truncated": truncated,
            "dropped_findings": dropped_findings,
        },
    }


def locate_records_for_mode(root_path: Path, *, mode: str) -> list[LocatedRecord]:
    normalized_mode = str(mode).strip()
    if normalized_mode == "committed":
        return read_committed_records(root_path)
    if normalized_mode == "best_effort":
        return read_best_effort_records(root_path)
    raise CliError(f"unsupported read mode: {mode}")


def get_manifest_path(root_path: Path) -> Path:
    return root_path.expanduser().resolve() / MANIFEST_FILENAME


def get_supported_naming_strategies() -> tuple[str, ...]:
    return SUPPORTED_NAMING_STRATEGIES


def serialize_located_record(record: LocatedRecord) -> dict[str, object]:
    source_path = record.source_file
    return {
        "source_kind": record.source_kind,
        "source_file": source_path.as_posix(),
        "line_no": record.line_no,
        "record": record.record,
    }


def _write_manifest(root: Path, config: TapeFolderConfig) -> None:
    manifest_path = root / MANIFEST_FILENAME
    payload = {
        "class": MANIFEST_RECORD_CLASS,
        "format_version": config.format_version,
        "created_at": _utc_now_iso(),
        "config": {
            "tape_name": config.tape_name,
            "naming_strategy": config.naming_strategy,
            "max_records_per_segment": config.max_records_per_segment,
            "paths": {
                "segments": SEGMENTS_DIRNAME,
                "staging": STAGING_DIRNAME,
            },
        },
    }
    if config.tape_class is not None:
        payload["config"]["tape.class"] = config.tape_class
    if config.allowed_classes is not None:
        payload["config"]["allowed_classes"] = config.allowed_classes
    if config.data_schema is not None:
        payload["config"]["data_schema"] = config.data_schema
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _validate_tape_name(value: str) -> None:
    _ = validate_string_for_path(value, field_name="tape name")


def _validate_naming_strategy(value: str) -> None:
    if value not in SUPPORTED_NAMING_STRATEGIES:
        available = ", ".join(SUPPORTED_NAMING_STRATEGIES)
        raise CliError(f"unsupported naming strategy: {value} (expected one of: {available})")


def _validate_max_records_per_segment(value: int) -> None:
    if value < 0:
        raise CliError("max records per segment must be >= 0")


def _normalize_writer_id(value: str) -> str:
    writer = str(value).strip()
    if not writer:
        raise CliError("writer id must not be empty")
    normalized = re.sub(r"[^a-zA-Z0-9._-]+", "_", writer).strip("_")
    if not normalized:
        raise CliError("writer id has no valid filename characters")
    return normalized


def _normalize_record_class(value: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise CliError("record class must not be empty")
    if normalized in (
        SEGMENT_METADATA_CLASS,
        STAGING_METADATA_CLASS,
        MANIFEST_RECORD_CLASS,
        "tape.metadata",
        "tape.manifest",
    ):
        raise CliError(f"record class is reserved: {normalized}")
    return normalized


def _validate_minimal_record(record: dict[str, object]) -> None:
    actual_keys = set(record.keys())
    missing = sorted(MINIMAL_RECORD_KEYS - actual_keys)
    if missing:
        raise CliError(f"record is missing required fields: {', '.join(missing)}")

    unsupported = sorted(actual_keys - MINIMAL_RECORD_KEYS - ALLOWED_RECORD_EXTRA_KEYS)
    if unsupported:
        raise CliError(f"record has unsupported fields: {', '.join(unsupported)}")

    record_class = str(record.get("class", "")).strip()
    if not record_class:
        raise CliError("record class must not be empty")

    writer = str(record.get("writer", "")).strip()
    if not writer:
        raise CliError("record writer must not be empty")

    created_at = str(record.get("created_at", "")).strip()
    _ = _parse_timetag(created_at)

    if "data" in record and not isinstance(record.get("data"), dict):
        raise CliError("record data must be a JSON object")


def _normalize_record_data(value: dict[str, object] | None) -> dict[str, object] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise CliError("record data must be a JSON object")
    return value


def _normalize_tape_class(value: object | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized:
        raise CliError("tape.class must not be empty when provided")
    return normalized


def _normalize_allowed_classes(value: object | None) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise CliError("tape manifest config.allowed_classes must be a JSON array of strings")

    normalized: list[str] = []
    seen: set[str] = set()
    for idx, item in enumerate(value, start=1):
        if not isinstance(item, str):
            raise CliError(f"allowed_classes[{idx}] must be a string")
        item_class = _normalize_record_class(item)
        if item_class in seen:
            continue
        normalized.append(item_class)
        seen.add(item_class)
    return normalized


def _validate_record_class_allowed(record_class: str, *, allowed_classes: list[str] | None) -> None:
    if allowed_classes is None:
        return
    if record_class not in allowed_classes:
        allowed = ", ".join(allowed_classes) if allowed_classes else "<none>"
        raise CliError(f"record class is not allowed: {record_class} (allowed_classes: {allowed})")


def _normalize_data_schema(value: object | None) -> dict[str, object] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise CliError("tape manifest config.data_schema must be a JSON object")
    schema_uri = value.get("$schema")
    if schema_uri is not None and str(schema_uri).strip() != "https://json-schema.org/draft/2020-12/schema":
        raise CliError(
            "data_schema must use JSON Schema 2020-12 "
            "(expected $schema=https://json-schema.org/draft/2020-12/schema)"
        )
    try:
        Draft202012Validator.check_schema(value)
    except SchemaError as exc:
        raise CliError(f"invalid data_schema: {exc.message}") from exc
    return value


def _validate_record_data_schema(
    record: dict[str, object],
    *,
    data_schema: dict[str, object] | None,
) -> None:
    if data_schema is None:
        return

    data_payload = record.get("data", {})
    if not isinstance(data_payload, dict):
        raise CliError("record data must be a JSON object")

    validator = Draft202012Validator(data_schema, format_checker=FormatChecker())
    try:
        validator.validate(data_payload)
    except ValidationError as exc:
        location = "root" if not exc.path else ".".join(str(token) for token in exc.path)
        raise CliError(f"record data does not match data_schema at {location}: {exc.message}") from exc


def _normalize_created_at(value: str | None) -> str:
    if value is None:
        return _utc_now_iso()
    parsed = _parse_timetag(str(value))
    return _format_timetag(parsed)


def _parse_timetag(value: str) -> datetime:
    candidate = value.strip()
    if not candidate:
        raise CliError("created_at is required and must be ISO8601 UTC")
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise CliError(f"invalid created_at timestamp: {value}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_timetag(value: datetime) -> str:
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _append_jsonl_line(path: Path, payload: dict[str, object]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload))
        handle.write("\n")


def _write_jsonl_file(path: Path, records: Iterable[dict[str, object]]) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record))
            handle.write("\n")
    tmp_path.replace(path)


def _read_staging_records(staging_path: Path) -> tuple[dict[str, object], list[LocatedRecord]]:
    if not staging_path.exists():
        raise CliError(f"staging file does not exist: {staging_path}")
    if not staging_path.is_file():
        raise CliError(f"staging path is not a file: {staging_path}")

    with staging_path.open("r", encoding="utf-8") as handle:
        first_line = handle.readline()
        if not first_line:
            raise CliError(f"staging file is empty: {staging_path}")
        metadata = _parse_json_object_line(first_line, path=staging_path, line_no=1)
        if metadata.get("class") != STAGING_METADATA_CLASS:
            raise CliError(f"first staging record must be class={STAGING_METADATA_CLASS}: {staging_path}")
        declared = str(metadata.get("staging_filename", "")).strip()
        if declared != staging_path.name:
            raise CliError(
                f"staging metadata filename mismatch: declared={declared} actual={staging_path.name}"
            )

        records: list[LocatedRecord] = []
        for line_no, raw_line in enumerate(handle, start=2):
            stripped = raw_line.strip()
            if not stripped:
                continue
            payload = _parse_json_object_line(stripped, path=staging_path, line_no=line_no)
            records.append(
                LocatedRecord(
                    source_kind="staging",
                    source_file=staging_path,
                    line_no=line_no,
                    record=payload,
                )
            )

    return metadata, records


def _read_segment_records(segment_path: Path) -> tuple[dict[str, object], list[LocatedRecord]]:
    metadata = _validate_segment_header(segment_path)
    records: list[LocatedRecord] = []
    with segment_path.open("r", encoding="utf-8") as handle:
        for line_no, raw_line in enumerate(handle, start=1):
            if line_no == 1:
                continue
            stripped = raw_line.strip()
            if not stripped:
                continue
            payload = _parse_json_object_line(stripped, path=segment_path, line_no=line_no)
            records.append(
                LocatedRecord(
                    source_kind="committed",
                    source_file=segment_path,
                    line_no=line_no,
                    record=payload,
                )
            )
    return metadata, records


def _validate_segment_header(segment_path: Path) -> dict[str, object]:
    if not segment_path.exists():
        raise CliError(f"segment file does not exist: {segment_path}")
    if not segment_path.is_file():
        raise CliError(f"segment path is not a file: {segment_path}")

    with segment_path.open("r", encoding="utf-8") as handle:
        first_line = handle.readline()
    if not first_line:
        raise CliError(f"segment file is empty: {segment_path}")

    metadata = _parse_json_object_line(first_line, path=segment_path, line_no=1)
    if metadata.get("class") != SEGMENT_METADATA_CLASS:
        raise CliError(f"first segment record must be class={SEGMENT_METADATA_CLASS}: {segment_path}")

    declared_name = str(metadata.get("segment_filename", "")).strip()
    if declared_name != segment_path.name:
        raise CliError(
            f"segment metadata filename mismatch: declared={declared_name} actual={segment_path.name}"
        )
    return metadata


def _parse_json_object_line(raw_line: str, *, path: Path, line_no: int) -> dict[str, object]:
    try:
        payload = json.loads(raw_line)
    except json.JSONDecodeError as exc:
        raise CliError(f"invalid JSON in {path}:{line_no}: {exc}") from exc
    if not isinstance(payload, dict):
        raise CliError(f"record in {path}:{line_no} must be a JSON object")
    return payload


def _count_segment_data_records(segment_path: Path) -> int:
    _ = _validate_segment_header(segment_path)
    count = 0
    with segment_path.open("r", encoding="utf-8") as handle:
        for line_no, raw_line in enumerate(handle, start=1):
            if line_no == 1:
                continue
            if not raw_line.strip():
                continue
            _ = _parse_json_object_line(raw_line, path=segment_path, line_no=line_no)
            count += 1
    return count


def _create_segment_file(segment_path: Path, *, naming_strategy: str) -> None:
    metadata = {
        "class": SEGMENT_METADATA_CLASS,
        "created_at": _utc_now_iso(),
        "naming_strategy": naming_strategy,
        "segment_filename": segment_path.name,
    }
    _write_jsonl_file(segment_path, [metadata])


def _resolve_target_segment_name(
    *,
    strategy: str,
    max_records_per_segment: int,
    segment_names: list[str],
    segment_counts: dict[str, int],
    created_at: datetime,
) -> str:
    if strategy == "sequential":
        return _resolve_sequential_segment_name(
            max_records_per_segment=max_records_per_segment,
            segment_names=segment_names,
            segment_counts=segment_counts,
        )
    if strategy == "monthly":
        prefix = period_prefix_for_strategy("monthly", created_at)
        return _resolve_calendar_segment_name(
            prefix=prefix,
            segment_re=_MONTHLY_SEGMENT_RE,
            segment_names=segment_names,
            segment_counts=segment_counts,
        )
    if strategy == "daily":
        prefix = period_prefix_for_strategy("daily", created_at)
        return _resolve_calendar_segment_name(
            prefix=prefix,
            segment_re=_DAILY_SEGMENT_RE,
            segment_names=segment_names,
            segment_counts=segment_counts,
        )
    raise CliError(f"unsupported naming strategy: {strategy}")


def _resolve_sequential_segment_name(
    *,
    max_records_per_segment: int,
    segment_names: list[str],
    segment_counts: dict[str, int],
) -> str:
    sequential_candidates = sorted(
        segment_name for segment_name in segment_names if _SEQUENTIAL_SEGMENT_RE.fullmatch(segment_name)
    )
    if sequential_candidates:
        last_name = sequential_candidates[-1]
        current_count = segment_counts.get(last_name, 0)
        if max_records_per_segment == 0 or current_count < max_records_per_segment:
            return last_name

    max_seq = 0
    for segment_name in sequential_candidates:
        match = _SEQUENTIAL_SEGMENT_RE.fullmatch(segment_name)
        if match is None:
            continue
        max_seq = max(max_seq, int(match.group(1)))
    next_seq = max_seq + 1
    width = max(4, len(str(next_seq)))
    next_name = f"{str(next_seq).zfill(width)}.jsonl"
    _register_segment_name(segment_names, segment_counts, next_name)
    return next_name


def _resolve_calendar_segment_name(
    *,
    prefix: str,
    segment_re: re.Pattern[str],
    segment_names: list[str],
    segment_counts: dict[str, int],
) -> str:
    # Calendar-based strategies roll only on period boundary; max_records_per_segment is ignored.
    expected_name = f"{prefix}.jsonl"
    if expected_name not in segment_names:
        _register_segment_name(segment_names, segment_counts, expected_name)
    else:
        match = segment_re.fullmatch(expected_name)
        if match is None:
            raise CliError(f"invalid calendar segment filename: {expected_name}")
    return expected_name


def _register_segment_name(
    segment_names: list[str],
    segment_counts: dict[str, int],
    name: str,
) -> None:
    if name not in segment_names:
        segment_names.append(name)
    segment_counts.setdefault(name, 0)


def _best_effort_sort_key(item: LocatedRecord) -> tuple[str, str, int]:
    created_at_value = item.record.get("created_at")
    created_at = str(created_at_value) if created_at_value is not None else ""
    return (created_at, item.source_file.name, item.line_no)
