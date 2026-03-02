from __future__ import annotations

import argparse
import json
from pathlib import Path

from agentos._core.errors import CliError
from agentos._core.project import resolve_project_tape_dir
from agentos._core.utils import _load_json_arg
from agentos.tape.folder_core import (
    TapeFolderConfig,
    append_staging_record,
    bootstrap_tape_folder,
    consolidate_staging_records,
    get_manifest_path,
    get_supported_naming_strategies,
    load_tape_folder_config,
    locate_records_for_mode,
    serialize_located_record,
    verify_segment_headers,
)

DEFAULT_TAPE_TYPE = "folder"
DEFAULT_NAMING_STRATEGY = "sequential"
DEFAULT_MAX_RECORDS_PER_SEGMENT = 1000


def _strategy_uses_max_records_per_segment(naming_strategy: str) -> bool:
    return naming_strategy == "sequential"


def _resolve_tape_root(
    *,
    root_path: str | None,
    tape_name: str | None,
) -> tuple[Path, dict[str, object]]:
    if root_path is not None:
        resolved_root = Path(root_path).expanduser().resolve()
        return (
            resolved_root,
            {
                "resolution": "explicit-root",
                "project_root": None,
                "tape": None,
            },
        )

    if tape_name is None:
        raise CliError("either --root or --tape is required")

    resolved_root, project_root, normalized_tape = resolve_project_tape_dir(
        tape_name,
        start_path=Path.cwd(),
    )
    return (
        resolved_root,
        {
            "resolution": "project-tape",
            "project_root": str(project_root),
            "tape": normalized_tape,
        },
    )


def _config_to_payload(config: TapeFolderConfig) -> dict[str, object]:
    return {
        "type": DEFAULT_TAPE_TYPE,
        "tape_name": config.tape_name,
        "tape.class": config.tape_class,
        "naming_strategy": config.naming_strategy,
        "max_records_per_segment": config.max_records_per_segment,
        "data_schema": config.data_schema,
        "format_version": config.format_version,
    }


def _default_config_payload() -> dict[str, object]:
    return {
        "type": DEFAULT_TAPE_TYPE,
        "tape.class": None,
        "naming_strategy": DEFAULT_NAMING_STRATEGY,
        "max_records_per_segment": DEFAULT_MAX_RECORDS_PER_SEGMENT,
        "data_schema": None,
    }


def _warning_policy_payload() -> dict[str, str]:
    return {
        "missing_tape_on_write_without_init": "error",
        "missing_tape_on_write_with_init": "create",
        "existing_tape_with_explicit_init_option_mismatch": "warn",
        "existing_non_default_tape_without_explicit_init_options": "warn",
    }


def _validate_tape_type(value: str, *, field_name: str = "type") -> str:
    normalized = str(value).strip()
    if normalized != DEFAULT_TAPE_TYPE:
        raise CliError(f"unsupported {field_name}: {value} (only '{DEFAULT_TAPE_TYPE}' is supported)")
    return normalized


def _load_optional_json_object_arg(
    json_value: str | None,
    file_value: str | None,
    *,
    field_name: str,
) -> dict[str, object] | None:
    if json_value is None and file_value is None:
        return None
    payload = _load_json_arg(json_value, file_value, field_name=field_name)
    if not isinstance(payload, dict):
        raise CliError(f"{field_name} must be a JSON object")
    return payload


def _build_write_init_options(
    args: argparse.Namespace,
    *,
    resolution: dict[str, object],
    root_path: Path,
) -> tuple[dict[str, object], dict[str, object], bool]:
    explicit: dict[str, object] = {}

    init_type = getattr(args, "init_tape_type", None)
    init_naming = getattr(args, "init_naming", None)
    init_max_records = getattr(args, "init_max_records_per_segment", None)
    init_tape_name = getattr(args, "init_tape_name", None)
    init_tape_class = getattr(args, "init_tape_class", None)
    init_data_schema = _load_optional_json_object_arg(
        getattr(args, "init_data_schema_json", None),
        getattr(args, "init_data_schema_file", None),
        field_name="init data_schema",
    )

    if init_type is not None:
        explicit["type"] = _validate_tape_type(init_type, field_name="init type")
    if init_naming is not None:
        explicit["naming_strategy"] = str(init_naming)
    if init_max_records is not None:
        explicit["max_records_per_segment"] = int(init_max_records)
    if init_tape_name is not None:
        explicit["tape_name"] = str(init_tape_name)
    if init_tape_class is not None:
        explicit["tape.class"] = str(init_tape_class)
    if init_data_schema is not None:
        explicit["data_schema"] = init_data_schema

    default_tape_name = (
        str(resolution["tape"])
        if resolution.get("tape") is not None
        else root_path.name
    )

    resolved = {
        "type": DEFAULT_TAPE_TYPE,
        "tape_name": str(explicit.get("tape_name", default_tape_name)),
        "tape.class": explicit.get("tape.class"),
        "naming_strategy": str(explicit.get("naming_strategy", DEFAULT_NAMING_STRATEGY)),
        "max_records_per_segment": int(
            explicit.get("max_records_per_segment", DEFAULT_MAX_RECORDS_PER_SEGMENT)
        ),
        "data_schema": explicit.get("data_schema"),
    }

    has_explicit_options = len(explicit) > 0
    return resolved, explicit, has_explicit_options


def _warning_list_for_existing_tape(
    existing: TapeFolderConfig,
    *,
    explicit_init_options: dict[str, object],
) -> list[str]:
    warnings: list[str] = []

    if explicit_init_options:
        if "type" in explicit_init_options and explicit_init_options["type"] != DEFAULT_TAPE_TYPE:
            warnings.append(
                "init option mismatch: tape type differs from existing config "
                f"(requested={explicit_init_options['type']} existing={DEFAULT_TAPE_TYPE})"
            )

        if (
            "naming_strategy" in explicit_init_options
            and str(explicit_init_options["naming_strategy"]) != existing.naming_strategy
        ):
            warnings.append(
                "init option mismatch: naming_strategy differs from existing config "
                f"(requested={explicit_init_options['naming_strategy']} existing={existing.naming_strategy})"
            )

        if (
            "max_records_per_segment" in explicit_init_options
            and int(explicit_init_options["max_records_per_segment"]) != existing.max_records_per_segment
            and _strategy_uses_max_records_per_segment(existing.naming_strategy)
            and _strategy_uses_max_records_per_segment(
                str(explicit_init_options.get("naming_strategy", existing.naming_strategy))
            )
        ):
            warnings.append(
                "init option mismatch: max_records_per_segment differs from existing config "
                f"(requested={explicit_init_options['max_records_per_segment']} "
                f"existing={existing.max_records_per_segment})"
            )

        if "tape_name" in explicit_init_options and str(explicit_init_options["tape_name"]) != existing.tape_name:
            warnings.append(
                "init option mismatch: tape_name differs from existing config "
                f"(requested={explicit_init_options['tape_name']} existing={existing.tape_name})"
            )

        if "tape.class" in explicit_init_options and str(explicit_init_options["tape.class"]) != str(
            existing.tape_class
        ):
            warnings.append(
                "init option mismatch: tape.class differs from existing config "
                f"(requested={explicit_init_options['tape.class']} existing={existing.tape_class})"
            )

        if "data_schema" in explicit_init_options and explicit_init_options["data_schema"] != existing.data_schema:
            warnings.append("init option mismatch: data_schema differs from existing config")

        return warnings

    max_records_non_default = (
        _strategy_uses_max_records_per_segment(existing.naming_strategy)
        and existing.max_records_per_segment != DEFAULT_MAX_RECORDS_PER_SEGMENT
    )
    is_non_default = (
        existing.naming_strategy != DEFAULT_NAMING_STRATEGY
        or max_records_non_default
        or existing.tape_class is not None
        or existing.data_schema is not None
    )
    if is_non_default:
        details: list[str] = [f"naming_strategy={existing.naming_strategy}"]
        if _strategy_uses_max_records_per_segment(existing.naming_strategy):
            details.append(f"max_records_per_segment={existing.max_records_per_segment}")
        else:
            details.append("max_records_per_segment ignored for this naming strategy")
        if existing.tape_class is not None:
            details.append(f"tape.class={existing.tape_class}")
        if existing.data_schema is not None:
            details.append("data_schema=present")
        warnings.append("tape uses non-default config (" + ", ".join(details) + ")")
    return warnings


def _ensure_tape_for_write(
    root_path: Path,
    *,
    write_init_requested: bool,
    init_values: dict[str, object],
    explicit_init_options: dict[str, object],
) -> tuple[TapeFolderConfig, bool, list[str]]:
    manifest_path = get_manifest_path(root_path)
    exists = manifest_path.exists()

    if not exists:
        if not write_init_requested:
            raise CliError(
                f"tape is not initialized: {root_path}; pass --init for implicit creation or run `agentos tape init`"
            )
        config, _ = bootstrap_tape_folder(
            root_path,
            tape_name=str(init_values["tape_name"]),
            naming_strategy=str(init_values["naming_strategy"]),
            max_records_per_segment=int(init_values["max_records_per_segment"]),
            tape_class=init_values.get("tape.class"),
            data_schema=init_values.get("data_schema"),
            ensure=False,
        )
        return config, True, []

    existing_config = load_tape_folder_config(root_path)
    warnings = _warning_list_for_existing_tape(
        existing_config,
        explicit_init_options=explicit_init_options,
    )
    return existing_config, False, warnings


def _prepare_write_context(
    args: argparse.Namespace,
    *,
    resolution: dict[str, object],
    root_path: Path,
) -> tuple[TapeFolderConfig, bool, list[str]]:
    init_values, explicit_init_options, has_explicit_init_options = _build_write_init_options(
        args,
        resolution=resolution,
        root_path=root_path,
    )
    if has_explicit_init_options and not args.write_init:
        raise CliError("init options require --init")

    return _ensure_tape_for_write(
        root_path,
        write_init_requested=bool(args.write_init),
        init_values=init_values,
        explicit_init_options=explicit_init_options,
    )


def _parse_append_batch_entries(raw_payload: object) -> list[dict[str, object]]:
    if not isinstance(raw_payload, list):
        raise CliError("entries must be a JSON array")
    if not raw_payload:
        raise CliError("entries must not be empty")

    normalized: list[dict[str, object]] = []
    for idx, raw_entry in enumerate(raw_payload, start=1):
        if not isinstance(raw_entry, dict):
            raise CliError(f"entries[{idx}] must be a JSON object")

        allowed = {"class", "created_at", "data"}
        extra = sorted(set(raw_entry.keys()) - allowed)
        if extra:
            raise CliError(f"entries[{idx}] has unsupported fields: {', '.join(extra)}")

        record_class = str(raw_entry.get("class", "")).strip()
        if not record_class:
            raise CliError(f"entries[{idx}].class is required")

        created_at = raw_entry.get("created_at")
        if created_at is not None and not isinstance(created_at, str):
            raise CliError(f"entries[{idx}].created_at must be a string")

        data = raw_entry.get("data")
        if data is not None and not isinstance(data, dict):
            raise CliError(f"entries[{idx}].data must be a JSON object")

        normalized.append(
            {
                "class": record_class,
                "created_at": created_at,
                "data": data,
            }
        )

    return normalized


def _cmd_tape_init(args: argparse.Namespace) -> int:
    root_path, resolution = _resolve_tape_root(
        root_path=args.root_path,
        tape_name=args.tape_name,
    )

    _validate_tape_type(args.tape_type)
    data_schema = _load_optional_json_object_arg(
        args.data_schema_json,
        args.data_schema_file,
        field_name="data_schema",
    )
    tape_display_name = (
        str(args.tape_display_name)
        if args.tape_display_name is not None
        else (str(resolution["tape"]) if resolution.get("tape") is not None else root_path.name)
    )

    config, created = bootstrap_tape_folder(
        root_path,
        tape_name=tape_display_name,
        naming_strategy=str(args.naming_strategy),
        max_records_per_segment=int(args.max_records_per_segment),
        tape_class=args.tape_class,
        data_schema=data_schema,
        ensure=bool(args.ensure),
    )

    output = {
        "status": "ok",
        "command": "tape init",
        "root_path": str(root_path),
        "manifest_path": str(get_manifest_path(root_path)),
        "created": created,
        "config": _config_to_payload(config),
        **resolution,
    }
    print(json.dumps(output))
    return 0


def _cmd_tape_append(args: argparse.Namespace) -> int:
    root_path, resolution = _resolve_tape_root(
        root_path=args.root_path,
        tape_name=args.tape_name,
    )

    config, tape_created, warnings = _prepare_write_context(
        args,
        resolution=resolution,
        root_path=root_path,
    )

    data = _load_optional_json_object_arg(
        args.data_json,
        args.data_file,
        field_name="data",
    )

    staging_path, record = append_staging_record(
        root_path,
        writer_id=str(args.writer_id),
        record_class=str(args.record_class),
        created_at=args.created_at,
        data=data,
    )

    output = {
        "status": "ok",
        "command": "tape append",
        "root_path": str(root_path),
        "staging_path": str(staging_path),
        "tape_created": tape_created,
        "config": _config_to_payload(config),
        "record": record,
        **resolution,
    }
    if warnings:
        output["warnings"] = warnings
    print(json.dumps(output))
    return 0


def _cmd_tape_append_batch(args: argparse.Namespace) -> int:
    root_path, resolution = _resolve_tape_root(
        root_path=args.root_path,
        tape_name=args.tape_name,
    )

    config, tape_created, warnings = _prepare_write_context(
        args,
        resolution=resolution,
        root_path=root_path,
    )

    payload = _load_json_arg(args.entries_json, args.entries_file, field_name="entries")
    entries = _parse_append_batch_entries(payload)

    results: list[dict[str, object]] = []
    for idx, entry in enumerate(entries, start=1):
        staging_path, record = append_staging_record(
            root_path,
            writer_id=str(args.writer_id),
            record_class=str(entry["class"]),
            created_at=entry["created_at"],
            data=entry["data"],
        )
        results.append(
            {
                "index": idx,
                "status": "ok",
                "staging_path": str(staging_path),
                "record": record,
            }
        )

    output = {
        "status": "ok",
        "command": "tape append-batch",
        "root_path": str(root_path),
        "tape_created": tape_created,
        "config": _config_to_payload(config),
        "input_count": len(entries),
        "appended_count": len(entries),
        "results": results,
        **resolution,
    }
    if warnings:
        output["warnings"] = warnings
    print(json.dumps(output))
    return 0


def _cmd_tape_consolidate(args: argparse.Namespace) -> int:
    root_path, resolution = _resolve_tape_root(
        root_path=args.root_path,
        tape_name=args.tape_name,
    )

    config, tape_created, warnings = _prepare_write_context(
        args,
        resolution=resolution,
        root_path=root_path,
    )

    result = consolidate_staging_records(root_path, limit=args.limit)
    output = {
        "status": "ok",
        "command": "tape consolidate",
        "root_path": str(root_path),
        "tape_created": tape_created,
        "config": _config_to_payload(config),
        **resolution,
        **result,
    }
    if warnings:
        output["warnings"] = warnings
    print(json.dumps(output))
    return 0


def _cmd_tape_query(args: argparse.Namespace) -> int:
    root_path, resolution = _resolve_tape_root(
        root_path=args.root_path,
        tape_name=args.tape_name,
    )
    consolidate_payload: dict[str, object] | None = None
    if args.pre_consolidate:
        consolidate_payload = consolidate_staging_records(root_path)

    records = locate_records_for_mode(root_path, mode=args.read_mode)

    matched = records
    if args.record_class_filter is not None:
        matched = [item for item in matched if item.record.get("class") == args.record_class_filter]

    total_matched = len(matched)
    if args.first_n is not None:
        matched = matched[: args.first_n]
    elif args.last_n is not None:
        matched = matched[-args.last_n :] if args.last_n < len(matched) else matched

    output: dict[str, object] = {
        "status": "ok",
        "command": "tape query",
        "root_path": str(root_path),
        "mode": args.read_mode,
        **resolution,
    }
    if consolidate_payload is not None:
        output["consolidated"] = consolidate_payload

    if args.count_only:
        output["count"] = total_matched
    else:
        output["total_matched"] = total_matched
        output["returned"] = len(matched)
        if args.with_source:
            output["entries"] = [serialize_located_record(item) for item in matched]
        else:
            output["entries"] = [item.record for item in matched]

    print(json.dumps(output))
    return 0


def _cmd_tape_verify(args: argparse.Namespace) -> int:
    root_path, resolution = _resolve_tape_root(
        root_path=args.root_path,
        tape_name=args.tape_name,
    )
    result = verify_segment_headers(root_path)
    output = {
        "status": "ok",
        "command": "tape verify",
        "root_path": str(root_path),
        **resolution,
        **result,
    }
    print(json.dumps(output))
    return 0


def _cmd_tape_config(args: argparse.Namespace) -> int:
    root_path, resolution = _resolve_tape_root(
        root_path=args.root_path,
        tape_name=args.tape_name,
    )
    config = load_tape_folder_config(root_path)
    output = {
        "status": "ok",
        "command": "tape config",
        "root_path": str(root_path),
        "manifest_path": str(get_manifest_path(root_path)),
        "defaults": _default_config_payload(),
        "warning_policy": _warning_policy_payload(),
        "config": _config_to_payload(config),
        **resolution,
    }
    print(json.dumps(output))
    return 0


def _cmd_tape_doctor(args: argparse.Namespace) -> int:
    root_path, resolution = _resolve_tape_root(
        root_path=args.root_path,
        tape_name=args.tape_name,
    )
    config = load_tape_folder_config(root_path)
    verify_payload = verify_segment_headers(root_path)
    committed_count = len(locate_records_for_mode(root_path, mode="committed"))
    best_effort_count = len(locate_records_for_mode(root_path, mode="best_effort"))

    staging_dir = root_path / "staging"
    staging_files = sorted(
        path.name for path in staging_dir.iterdir() if path.is_file() and path.name.endswith(".jsonl")
    )
    warnings = _warning_list_for_existing_tape(
        config,
        explicit_init_options={},
    )

    output = {
        "status": "ok",
        "command": "tape doctor",
        "root_path": str(root_path),
        "manifest_path": str(get_manifest_path(root_path)),
        "defaults": _default_config_payload(),
        "warning_policy": _warning_policy_payload(),
        "config": _config_to_payload(config),
        "segment_count": verify_payload["segment_count"],
        "committed_record_count": committed_count,
        "best_effort_record_count": best_effort_count,
        "staging_file_count": len(staging_files),
        "staging_files": staging_files,
        "warnings": warnings,
        **resolution,
    }
    print(json.dumps(output))
    return 0


def _add_tape_target_group(parser: argparse.ArgumentParser) -> None:
    target_group = parser.add_mutually_exclusive_group(required=True)
    target_group.add_argument(
        "--tape",
        dest="tape_name",
        help="Logical tape name resolved to <project>/.agentos/tapes/<name>/.",
    )
    target_group.add_argument(
        "--root",
        dest="root_path",
        help="Explicit tape root directory (headless mode).",
    )


def _add_write_init_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--init",
        action="store_true",
        dest="write_init",
        help="Allow first-write tape initialization when missing.",
    )
    parser.add_argument(
        "--init-type",
        default=None,
        dest="init_tape_type",
        choices=[DEFAULT_TAPE_TYPE],
        help="Tape backend type used when --init creates a new tape.",
    )
    parser.add_argument(
        "--init-naming",
        default=None,
        dest="init_naming",
        choices=list(get_supported_naming_strategies()),
        help="Naming strategy used when --init creates a new tape.",
    )
    parser.add_argument(
        "--init-max-records-per-segment",
        default=None,
        type=int,
        dest="init_max_records_per_segment",
        help="Segment rollover limit used for sequential naming (ignored for monthly/daily).",
    )
    parser.add_argument(
        "--init-tape-name",
        default=None,
        dest="init_tape_name",
        help="Human-friendly tape name used when --init creates a new tape.",
    )
    parser.add_argument(
        "--init-tape-class",
        default=None,
        dest="init_tape_class",
        help="Tape class stored as config field `tape.class` when --init creates a new tape.",
    )
    init_data_schema_group = parser.add_mutually_exclusive_group(required=False)
    init_data_schema_group.add_argument(
        "--init-data-schema-json",
        default=None,
        dest="init_data_schema_json",
        help="JSON Schema 2020-12 for record `data` payload (JSON object).",
    )
    init_data_schema_group.add_argument(
        "--init-data-schema-file",
        default=None,
        dest="init_data_schema_file",
        help="Path to JSON file with JSON Schema 2020-12 for record `data` payload.",
    )


def register_tape_commands(subparsers: argparse._SubParsersAction) -> None:
    tape_parser = subparsers.add_parser(
        "tape",
        help="Folder-backed JSONL tape operations.",
    )
    tape_subparsers = tape_parser.add_subparsers(dest="tape_command", required=True)

    naming_strategies = list(get_supported_naming_strategies())

    init_parser = tape_subparsers.add_parser(
        "init",
        help="Initialize a folder-backed tape.",
    )
    _add_tape_target_group(init_parser)
    init_parser.add_argument(
        "--type",
        default=DEFAULT_TAPE_TYPE,
        dest="tape_type",
        choices=[DEFAULT_TAPE_TYPE],
        help="Tape backend type.",
    )
    init_parser.add_argument(
        "--tape-name",
        default=None,
        dest="tape_display_name",
        help="Human-friendly tape name (defaults to tape identifier or root basename).",
    )
    init_parser.add_argument(
        "--tape-class",
        default=None,
        dest="tape_class",
        help="Tape class stored as config field `tape.class`.",
    )
    init_parser.add_argument(
        "--naming",
        default=DEFAULT_NAMING_STRATEGY,
        dest="naming_strategy",
        choices=naming_strategies,
        help="Committed segment naming strategy.",
    )
    init_parser.add_argument(
        "--max-records-per-segment",
        default=DEFAULT_MAX_RECORDS_PER_SEGMENT,
        type=int,
        dest="max_records_per_segment",
        help="Rollover limit for sequential naming (ignored for monthly/daily).",
    )
    init_data_schema_group = init_parser.add_mutually_exclusive_group(required=False)
    init_data_schema_group.add_argument(
        "--data-schema-json",
        default=None,
        dest="data_schema_json",
        help="JSON Schema 2020-12 for record `data` payload (JSON object).",
    )
    init_data_schema_group.add_argument(
        "--data-schema-file",
        default=None,
        dest="data_schema_file",
        help="Path to JSON file with JSON Schema 2020-12 for record `data` payload.",
    )
    init_parser.add_argument(
        "--ensure",
        action="store_true",
        dest="ensure",
        help="If tape exists, return existing config instead of failing.",
    )
    init_parser.set_defaults(handler=_cmd_tape_init)

    append_parser = tape_subparsers.add_parser(
        "append",
        help="Append one record to tape staging.",
    )
    _add_tape_target_group(append_parser)
    append_parser.add_argument(
        "--writer-id",
        required=True,
        dest="writer_id",
        help="Writer/process identifier.",
    )
    append_parser.add_argument(
        "--class",
        required=True,
        dest="record_class",
        help="Record class string.",
    )
    append_parser.add_argument(
        "--override-created-at",
        default=None,
        dest="created_at",
        help="Override record created_at (defaults to auto UTC timestamp).",
    )
    append_data_group = append_parser.add_mutually_exclusive_group(required=False)
    append_data_group.add_argument(
        "--data-json",
        default=None,
        dest="data_json",
        help="Record data JSON object (validated against tape data_schema when configured).",
    )
    append_data_group.add_argument(
        "--data-file",
        default=None,
        dest="data_file",
        help="Path to JSON file with record data object.",
    )
    _add_write_init_options(append_parser)
    append_parser.set_defaults(handler=_cmd_tape_append)

    append_batch_parser = tape_subparsers.add_parser(
        "append-batch",
        help="Append multiple records to tape staging.",
    )
    _add_tape_target_group(append_batch_parser)
    append_batch_parser.add_argument(
        "--writer-id",
        required=True,
        dest="writer_id",
        help="Writer/process identifier.",
    )
    append_batch_entries_group = append_batch_parser.add_mutually_exclusive_group(required=True)
    append_batch_entries_group.add_argument(
        "--entries-json",
        dest="entries_json",
        help="JSON array of records to append.",
    )
    append_batch_entries_group.add_argument(
        "--entries-file",
        dest="entries_file",
        help="Path to JSON file with records array.",
    )
    _add_write_init_options(append_batch_parser)
    append_batch_parser.set_defaults(handler=_cmd_tape_append_batch)

    consolidate_parser = tape_subparsers.add_parser(
        "consolidate",
        help="Copy staged records into committed segments.",
    )
    _add_tape_target_group(consolidate_parser)
    consolidate_parser.add_argument(
        "--limit",
        default=None,
        type=int,
        dest="limit",
        help="Process at most N staged records in this run.",
    )
    _add_write_init_options(consolidate_parser)
    consolidate_parser.set_defaults(handler=_cmd_tape_consolidate)

    query_parser = tape_subparsers.add_parser(
        "query",
        help="Query records from a folder-backed tape.",
    )
    _add_tape_target_group(query_parser)
    query_parser.add_argument(
        "--mode",
        default="committed",
        dest="read_mode",
        choices=["committed", "best_effort"],
        help="Read mode for source selection and ordering.",
    )
    query_parser.add_argument(
        "--consolidate",
        action="store_true",
        dest="pre_consolidate",
        help="Run consolidate before reading records.",
    )
    query_parser.add_argument(
        "--class",
        default=None,
        dest="record_class_filter",
        help="Filter by exact record class.",
    )
    query_slice_group = query_parser.add_mutually_exclusive_group()
    query_slice_group.add_argument(
        "--first",
        default=None,
        type=int,
        dest="first_n",
        help="Return only the first N matched records.",
    )
    query_slice_group.add_argument(
        "--last",
        default=None,
        type=int,
        dest="last_n",
        help="Return only the last N matched records.",
    )
    query_parser.add_argument(
        "--count",
        action="store_true",
        dest="count_only",
        help="Output only the count of matched records.",
    )
    query_parser.add_argument(
        "--with-source",
        action="store_true",
        dest="with_source",
        help="Include source filename and line number per record.",
    )
    query_parser.set_defaults(handler=_cmd_tape_query)

    verify_parser = tape_subparsers.add_parser(
        "verify",
        help="Validate committed segment metadata headers.",
    )
    _add_tape_target_group(verify_parser)
    verify_parser.set_defaults(handler=_cmd_tape_verify)

    config_parser = tape_subparsers.add_parser(
        "config",
        help="Show effective config, defaults, and warning policy.",
    )
    _add_tape_target_group(config_parser)
    config_parser.set_defaults(handler=_cmd_tape_config)

    doctor_parser = tape_subparsers.add_parser(
        "doctor",
        help="Inspect tape health and record/staging counts.",
    )
    _add_tape_target_group(doctor_parser)
    doctor_parser.set_defaults(handler=_cmd_tape_doctor)
