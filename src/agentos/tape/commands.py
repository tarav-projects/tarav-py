from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from agentos._core.errors import CliError
from agentos._core.utils import (
    _build_writer_payload,
    _load_json_arg,
    _load_json_array_arg,
    _load_json_object_arg,
    _utc_now_iso,
)


def _load_tape_metadata_entry(tape_path: Path) -> dict[str, object]:
    if not tape_path.exists():
        raise CliError(f"tape file does not exist: {tape_path}")
    if not tape_path.is_file():
        raise CliError(f"tape path is not a file: {tape_path}")

    with tape_path.open("r", encoding="utf-8") as handle:
        first_line = handle.readline()
    if not first_line:
        raise CliError(f"tape is empty: {tape_path}")

    try:
        metadata_entry = json.loads(first_line)
    except json.JSONDecodeError as exc:
        raise CliError(f"invalid metadata entry JSON in tape: {exc}") from exc
    if not isinstance(metadata_entry, dict):
        raise CliError("metadata entry must be a JSON object")
    if metadata_entry.get("entry_type") != "tape.meta":
        raise CliError("first tape entry must be entry_type=tape.meta")

    cargo = metadata_entry.get("cargo")
    if not isinstance(cargo, dict):
        raise CliError("metadata cargo must be a JSON object")
    tape_id = str(cargo.get("tape_id", "")).strip()
    tape_name = str(cargo.get("tape_name", "")).strip()
    if not tape_id:
        raise CliError("metadata cargo.tape_id is required")
    if not tape_name:
        raise CliError("metadata cargo.tape_name is required")
    try:
        UUID(tape_id)
    except ValueError as exc:
        raise CliError(f"metadata cargo.tape_id is not a valid UUID: {tape_id}") from exc
    return metadata_entry


def _validate_tape_entry_type(value: object) -> str:
    entry_type = str(value).strip()
    if not entry_type:
        raise CliError("entry type must not be empty")
    if entry_type == "tape.meta":
        raise CliError("entry type tape.meta is reserved for tape init")
    return entry_type


def _normalize_tape_batch_entry(
    raw_entry: object,
    *,
    workflow: str,
    writer: dict[str, str],
) -> dict[str, object]:
    if not isinstance(raw_entry, dict):
        raise CliError("batch entry must be a JSON object")

    allowed_fields = {"entry_type", "cargo", "refs"}
    extra_fields = sorted(set(raw_entry.keys()) - allowed_fields)
    if extra_fields:
        raise CliError(f"unsupported batch entry fields: {', '.join(extra_fields)}")

    if "entry_type" not in raw_entry:
        raise CliError("batch entry field entry_type is required")
    entry_type = _validate_tape_entry_type(raw_entry["entry_type"])

    cargo = raw_entry.get("cargo", {})
    if not isinstance(cargo, dict):
        raise CliError("batch entry field cargo must be a JSON object")

    refs = raw_entry.get("refs", [])
    if not isinstance(refs, list):
        raise CliError("batch entry field refs must be a JSON array")

    return {
        "ts": _utc_now_iso(),
        "writer": dict(writer),
        "workflow": workflow,
        "entry_type": entry_type,
        "refs": refs,
        "cargo": cargo,
    }


def _generate_tape_filename(tag: str, rotation: str, tape_dir: Path) -> tuple[str, dict[str, object]]:
    now = datetime.now(timezone.utc)
    if rotation == "monthly":
        prefix = now.strftime("%Y%m")
        return f"{prefix}-{tag}.jsonl", {"prefix": prefix}
    if rotation == "daily":
        prefix = now.strftime("%Y%m%d")
        return f"{prefix}-{tag}.jsonl", {"prefix": prefix}
    if rotation == "weekly":
        prefix = f"{now.strftime('%G')}W{now.strftime('%V')}"
        return f"{prefix}-{tag}.jsonl", {"prefix": prefix}
    if rotation == "yearly":
        prefix = now.strftime("%Y")
        return f"{prefix}-{tag}.jsonl", {"prefix": prefix}
    if rotation == "run":
        prefix = now.strftime("%Y%m%d-%H%M%S")
        return f"{prefix}-{tag}.jsonl", {"prefix": prefix}
    if rotation == "seq":
        prefix = _next_seq_prefix(tape_dir, tag)
        return f"{prefix}-{tag}.jsonl", {"prefix": prefix}
    if rotation == "random":
        prefix = uuid4().hex[:8]
        return f"{prefix}-{tag}.jsonl", {"prefix": prefix}
    return f"{tag}.jsonl", {}


def _next_seq_prefix(tape_dir: Path, tag: str) -> str:
    max_num = -1
    suffix = f"-{tag}.jsonl"
    if tape_dir.is_dir():
        for name in os.listdir(tape_dir):
            if name.endswith(suffix):
                prefix_part = name[: -len(suffix)]
                if re.fullmatch(r"\d+", prefix_part):
                    max_num = max(max_num, int(prefix_part))
    next_num = max_num + 1
    width = max(3, len(str(next_num)))
    return str(next_num).zfill(width)


def _find_tapes_by_tag(tape_dir: Path, tag: str) -> list[Path]:
    if not tape_dir.is_dir():
        return []
    suffix = f"-{tag}.jsonl"
    exact = f"{tag}.jsonl"
    results = []
    for name in sorted(os.listdir(tape_dir)):
        if name.endswith(suffix) or name == exact:
            results.append(tape_dir / name)
    return results


def _find_all_tapes(tape_dir: Path) -> list[Path]:
    if not tape_dir.is_dir():
        return []
    return sorted(
        tape_dir / name
        for name in os.listdir(tape_dir)
        if name.endswith(".jsonl")
    )


def _select_tape(candidates: list[Path], mode: str) -> Path | None:
    if not candidates:
        return None
    if mode == "first":
        return candidates[0]
    if mode == "last":
        return candidates[-1]
    if mode == "latest":
        return max(candidates, key=lambda p: p.stat().st_mtime)
    if mode == "oldest":
        return min(candidates, key=lambda p: p.stat().st_mtime)
    if mode == "smallest":
        return min(candidates, key=lambda p: p.stat().st_size)
    if mode == "largest":
        return max(candidates, key=lambda p: p.stat().st_size)
    raise CliError(f"unknown select mode: {mode}")


def _cmd_tape_init(args: argparse.Namespace) -> int:
    tape_path = Path(args.tape_path).expanduser()
    if tape_path.exists():
        if args.ensure:
            metadata_entry = _load_tape_metadata_entry(tape_path)
            output = {
                "status": "ok",
                "command": "tape init",
                "tape_path": str(tape_path.resolve()),
                "entry": metadata_entry,
                "created": False,
            }
            print(json.dumps(output))
            return 0
        raise CliError(f"tape already exists: {tape_path}")
    tape_path.parent.mkdir(parents=True, exist_ok=True)

    tape_id = args.tape_id if args.tape_id is not None else str(uuid4())
    try:
        UUID(str(tape_id))
    except ValueError as exc:
        raise CliError(f"invalid tape id (expected UUID): {tape_id}") from exc

    custom_cargo = _load_json_object_arg(args.cargo_json, args.cargo_file, field_name="cargo")
    if "tape_id" in custom_cargo or "tape_name" in custom_cargo:
        raise CliError("custom cargo must not define tape_id or tape_name")

    entry = {
        "ts": _utc_now_iso(),
        "writer": _build_writer_payload(args),
        "workflow": str(args.workflow),
        "entry_type": "tape.meta",
        "cargo": {"tape_id": str(tape_id), "tape_name": str(args.tape_name), **custom_cargo},
    }

    with tape_path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(entry))
        handle.write("\n")

    output = {
        "status": "ok",
        "command": "tape init",
        "tape_path": str(tape_path.resolve()),
        "entry": entry,
        "created": True,
    }
    print(json.dumps(output))
    return 0


def _cmd_tape_append(args: argparse.Namespace) -> int:
    tape_path = Path(args.tape_path).expanduser()
    metadata_entry = _load_tape_metadata_entry(tape_path)
    metadata_cargo = metadata_entry.get("cargo")
    if not isinstance(metadata_cargo, dict):
        raise CliError("metadata cargo must be a JSON object")

    entry_type = _validate_tape_entry_type(args.entry_type)

    cargo = _load_json_object_arg(args.cargo_json, args.cargo_file, field_name="cargo")
    refs = _load_json_array_arg(args.refs_json, args.refs_file, field_name="refs")

    with tape_path.open("r", encoding="utf-8") as handle:
        entry_index = sum(1 for _ in handle) + 1

    entry = {
        "ts": _utc_now_iso(),
        "writer": _build_writer_payload(args),
        "workflow": str(args.workflow),
        "entry_type": entry_type,
        "refs": refs,
        "cargo": cargo,
    }
    with tape_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry))
        handle.write("\n")

    output = {
        "status": "ok",
        "command": "tape append",
        "tape_path": str(tape_path.resolve()),
        "tape_id": metadata_cargo.get("tape_id"),
        "tape_name": metadata_cargo.get("tape_name"),
        "entry_index": entry_index,
        "entry": entry,
    }
    print(json.dumps(output))
    return 0


def _cmd_tape_append_batch(args: argparse.Namespace) -> int:
    tape_path = Path(args.tape_path).expanduser()
    metadata_entry = _load_tape_metadata_entry(tape_path)
    metadata_cargo = metadata_entry.get("cargo")
    if not isinstance(metadata_cargo, dict):
        raise CliError("metadata cargo must be a JSON object")

    payload = _load_json_arg(args.entries_json, args.entries_file, field_name="entries")
    if not isinstance(payload, list):
        raise CliError("entries must be a JSON array")
    if not payload:
        raise CliError("entries must not be empty")

    workflow = str(args.workflow)
    writer = _build_writer_payload(args)
    normalized_entries: list[dict[str, object]] = []
    results: list[dict[str, object]] = []
    has_errors = False

    for idx, raw_entry in enumerate(payload, start=1):
        try:
            normalized_entry = _normalize_tape_batch_entry(
                raw_entry,
                workflow=workflow,
                writer=writer,
            )
            normalized_entries.append(normalized_entry)
            results.append({"index": idx, "status": "validated"})
        except CliError as exc:
            has_errors = True
            results.append({"index": idx, "status": "error", "error": str(exc)})

    if has_errors:
        for result in results:
            if result.get("status") == "validated":
                result["status"] = "not_appended"
                result["error"] = "batch validation failed"
        failed_count = sum(1 for result in results if result.get("status") == "error")
        output = {
            "status": "error",
            "command": "tape append-batch",
            "tape_path": str(tape_path.resolve()),
            "tape_id": metadata_cargo.get("tape_id"),
            "tape_name": metadata_cargo.get("tape_name"),
            "input_count": len(payload),
            "appended_count": 0,
            "failed_count": failed_count,
            "atomic": True,
            "results": results,
        }
        print(json.dumps(output))
        return 1

    with tape_path.open("r", encoding="utf-8") as handle:
        existing_count = sum(1 for _ in handle)

    serialized_batch = "".join(f"{json.dumps(entry)}\n" for entry in normalized_entries)
    with tape_path.open("a", encoding="utf-8") as handle:
        handle.write(serialized_batch)

    output_results: list[dict[str, object]] = []
    for idx, entry in enumerate(normalized_entries, start=1):
        output_results.append(
            {
                "index": idx,
                "status": "ok",
                "entry_index": existing_count + idx,
                "entry": entry,
            }
        )

    output = {
        "status": "ok",
        "command": "tape append-batch",
        "tape_path": str(tape_path.resolve()),
        "tape_id": metadata_cargo.get("tape_id"),
        "tape_name": metadata_cargo.get("tape_name"),
        "input_count": len(payload),
        "appended_count": len(normalized_entries),
        "failed_count": 0,
        "atomic": True,
        "results": output_results,
    }
    print(json.dumps(output))
    return 0


def _cmd_tape_path(args: argparse.Namespace) -> int:
    tag = str(args.tag).strip()
    if not tag:
        raise CliError("tag must not be empty")

    tape_dir = Path(args.tape_dir).expanduser().resolve()
    select_mode = args.select_mode
    rotation = args.rotation
    use_filter_tag = bool(args.filter_tag)

    if select_mode is None and rotation is None:
        rotation = "monthly"

    selected: Path | None = None
    candidates_count = 0
    if select_mode is not None:
        if use_filter_tag:
            candidates = _find_tapes_by_tag(tape_dir, tag)
        else:
            candidates = _find_all_tapes(tape_dir)
        candidates_count = len(candidates)
        selected = _select_tape(candidates, select_mode)

    if selected is not None:
        output: dict[str, object] = {
            "status": "ok",
            "command": "tape path",
            "tape_path": str(selected),
            "filename": selected.name,
            "source": "selected",
            "select": select_mode,
            "tag": tag,
            "filter_tag": use_filter_tag,
            "candidates": candidates_count,
        }
        print(json.dumps(output))
        return 0

    if rotation is None:
        raise CliError(f"no tape found with --select {select_mode} and no --rotation fallback")

    filename, rotation_info = _generate_tape_filename(tag, rotation, tape_dir)
    tape_path = tape_dir / filename

    output = {
        "status": "ok",
        "command": "tape path",
        "tape_path": str(tape_path),
        "filename": filename,
        "source": "generated",
        "rotation": rotation,
        "tag": tag,
        **rotation_info,
    }
    print(json.dumps(output))
    return 0


def _read_tape_entries(tape_path: Path) -> tuple[dict[str, object], list[dict[str, object]]]:
    metadata_entry = _load_tape_metadata_entry(tape_path)
    entries: list[dict[str, object]] = []
    with tape_path.open("r", encoding="utf-8") as handle:
        for line_num, line in enumerate(handle, start=1):
            if line_num == 1:
                continue
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(entry, dict):
                entries.append(entry)
    return metadata_entry, entries


def _cmd_tape_list(args: argparse.Namespace) -> int:
    tape_path = Path(args.tape_path).expanduser()
    metadata_entry, entries = _read_tape_entries(tape_path)
    metadata_cargo = metadata_entry.get("cargo", {})

    entry_type_filter = getattr(args, "entry_type_filter", None)
    cargo_contains = getattr(args, "cargo_contains", None)

    matched: list[dict[str, object]] = []
    for entry in entries:
        if entry_type_filter is not None:
            if entry.get("entry_type") != entry_type_filter:
                continue
        if cargo_contains is not None:
            cargo_str = json.dumps(entry.get("cargo", {}))
            if cargo_contains not in cargo_str:
                continue
        matched.append(entry)

    total_matched = len(matched)

    first_n = getattr(args, "first_n", None)
    last_n = getattr(args, "last_n", None)
    if first_n is not None:
        matched = matched[:first_n]
    elif last_n is not None:
        matched = matched[-last_n:] if last_n < len(matched) else matched

    count_only = getattr(args, "count_only", False)

    base: dict[str, object] = {
        "status": "ok",
        "command": "tape list",
        "tape_path": str(tape_path.resolve()),
        "tape_id": metadata_cargo.get("tape_id"),
        "tape_name": metadata_cargo.get("tape_name"),
    }

    if count_only:
        base["count"] = total_matched
    else:
        base["total_matched"] = total_matched
        base["returned"] = len(matched)
        base["entries"] = matched

    print(json.dumps(base))
    return 0


def _cmd_tape_summary(args: argparse.Namespace) -> int:
    tape_path = Path(args.tape_path).expanduser()
    metadata_entry, entries = _read_tape_entries(tape_path)
    metadata_cargo = metadata_entry.get("cargo", {})

    entry_types: dict[str, int] = {}
    first_ts: str | None = None
    last_ts: str | None = None

    for entry in entries:
        et = str(entry.get("entry_type", ""))
        entry_types[et] = entry_types.get(et, 0) + 1
        ts = entry.get("ts")
        if isinstance(ts, str) and ts:
            if first_ts is None or ts < first_ts:
                first_ts = ts
            if last_ts is None or ts > last_ts:
                last_ts = ts

    output = {
        "status": "ok",
        "command": "tape summary",
        "tape_path": str(tape_path.resolve()),
        "tape_id": metadata_cargo.get("tape_id"),
        "tape_name": metadata_cargo.get("tape_name"),
        "entry_count": len(entries),
        "entry_types": entry_types,
        "first_ts": first_ts,
        "last_ts": last_ts,
    }
    print(json.dumps(output))
    return 0


def register_tape_commands(subparsers: argparse._SubParsersAction) -> None:
    tape_parser = subparsers.add_parser(
        "tape",
        help="Append-only JSONL tape operations.",
    )
    tape_subparsers = tape_parser.add_subparsers(dest="tape_command", required=True)

    tape_init_parser = tape_subparsers.add_parser(
        "init",
        help="Create a new append-only tape with a metadata entry.",
    )
    tape_init_parser.add_argument(
        "--tape",
        required=True,
        dest="tape_path",
        help="Path to the JSONL tape file.",
    )
    tape_init_parser.add_argument(
        "--workflow",
        required=True,
        help="Workflow/application identifier for the metadata entry.",
    )
    tape_init_parser.add_argument(
        "--tape-name",
        required=True,
        dest="tape_name",
        help="Human-friendly tape name.",
    )
    tape_init_parser.add_argument(
        "--writer-agent",
        required=True,
        dest="writer_agent",
        help="Writer agent identifier.",
    )
    tape_init_parser.add_argument(
        "--writer-skill",
        required=True,
        dest="writer_skill",
        help="Writer skill identifier.",
    )
    tape_init_parser.add_argument(
        "--writer-version",
        required=True,
        dest="writer_version",
        help="Writer version.",
    )
    tape_init_parser.add_argument(
        "--tape-id",
        default=None,
        dest="tape_id",
        help="Explicit tape UUID (auto-generated if omitted).",
    )
    tape_init_parser.add_argument(
        "--ensure",
        action="store_true",
        dest="ensure",
        help="If tape exists, return its metadata instead of failing.",
    )
    tape_init_cargo_group = tape_init_parser.add_mutually_exclusive_group()
    tape_init_cargo_group.add_argument(
        "--cargo-json",
        dest="cargo_json",
        help="Custom metadata cargo JSON object.",
    )
    tape_init_cargo_group.add_argument(
        "--cargo-file",
        dest="cargo_file",
        help="Path to JSON file with custom metadata cargo object.",
    )
    tape_init_parser.set_defaults(handler=_cmd_tape_init)

    tape_append_parser = tape_subparsers.add_parser(
        "append",
        help="Append a new entry to an existing tape.",
    )
    tape_append_parser.add_argument(
        "--tape",
        required=True,
        dest="tape_path",
        help="Path to the JSONL tape file.",
    )
    tape_append_parser.add_argument(
        "--workflow",
        required=True,
        help="Workflow/application identifier for the appended entry.",
    )
    tape_append_parser.add_argument(
        "--entry-type",
        required=True,
        dest="entry_type",
        help="Entry type (for example: relation.proposed).",
    )
    tape_append_parser.add_argument(
        "--writer-agent",
        required=True,
        dest="writer_agent",
        help="Writer agent identifier.",
    )
    tape_append_parser.add_argument(
        "--writer-skill",
        required=True,
        dest="writer_skill",
        help="Writer skill identifier.",
    )
    tape_append_parser.add_argument(
        "--writer-version",
        required=True,
        dest="writer_version",
        help="Writer version.",
    )
    tape_append_cargo_group = tape_append_parser.add_mutually_exclusive_group()
    tape_append_cargo_group.add_argument(
        "--cargo-json",
        dest="cargo_json",
        help="Entry cargo JSON object.",
    )
    tape_append_cargo_group.add_argument(
        "--cargo-file",
        dest="cargo_file",
        help="Path to JSON file with entry cargo object.",
    )
    tape_append_refs_group = tape_append_parser.add_mutually_exclusive_group()
    tape_append_refs_group.add_argument(
        "--refs-json",
        dest="refs_json",
        help="Entry refs JSON array.",
    )
    tape_append_refs_group.add_argument(
        "--refs-file",
        dest="refs_file",
        help="Path to JSON file with entry refs array.",
    )
    tape_append_parser.set_defaults(handler=_cmd_tape_append)

    tape_append_batch_parser = tape_subparsers.add_parser(
        "append-batch",
        help="Append multiple entries to an existing tape atomically.",
    )
    tape_append_batch_parser.add_argument(
        "--tape",
        required=True,
        dest="tape_path",
        help="Path to the JSONL tape file.",
    )
    tape_append_batch_parser.add_argument(
        "--workflow",
        required=True,
        help="Workflow/application identifier for all appended entries.",
    )
    tape_append_batch_parser.add_argument(
        "--writer-agent",
        required=True,
        dest="writer_agent",
        help="Writer agent identifier.",
    )
    tape_append_batch_parser.add_argument(
        "--writer-skill",
        required=True,
        dest="writer_skill",
        help="Writer skill identifier.",
    )
    tape_append_batch_parser.add_argument(
        "--writer-version",
        required=True,
        dest="writer_version",
        help="Writer version.",
    )
    tape_append_batch_entries_group = tape_append_batch_parser.add_mutually_exclusive_group(
        required=True
    )
    tape_append_batch_entries_group.add_argument(
        "--entries-json",
        dest="entries_json",
        help="JSON array of entries to append.",
    )
    tape_append_batch_entries_group.add_argument(
        "--entries-file",
        dest="entries_file",
        help="Path to JSON file with an array of entries to append.",
    )
    tape_append_batch_parser.set_defaults(handler=_cmd_tape_append_batch)

    tape_path_parser = tape_subparsers.add_parser(
        "path",
        help="Generate or select a tape file path.",
    )
    tape_path_parser.add_argument(
        "--dir",
        required=True,
        dest="tape_dir",
        help="Directory where tape files are stored.",
    )
    tape_path_parser.add_argument(
        "--tag",
        required=True,
        help="Tag suffix for the tape file (e.g. miner name).",
    )
    tape_path_parser.add_argument(
        "--rotation",
        default=None,
        choices=["monthly", "daily", "weekly", "yearly", "run", "seq", "random", "none"],
        help="Naming generation scheme.",
    )
    tape_path_parser.add_argument(
        "--select",
        default=None,
        dest="select_mode",
        choices=["first", "last", "latest", "oldest", "smallest", "largest"],
        help="Select an existing tape from the directory.",
    )
    tape_path_parser.add_argument(
        "--filter-tag",
        action="store_true",
        dest="filter_tag",
        help="When selecting, only consider tapes matching --tag.",
    )
    tape_path_parser.set_defaults(handler=_cmd_tape_path)

    tape_list_parser = tape_subparsers.add_parser(
        "list",
        help="List entries from an existing tape with optional filtering.",
    )
    tape_list_parser.add_argument(
        "--tape",
        required=True,
        dest="tape_path",
        help="Path to the JSONL tape file.",
    )
    tape_list_parser.add_argument(
        "--entry-type",
        default=None,
        dest="entry_type_filter",
        help="Filter by exact entry_type match.",
    )
    tape_list_parser.add_argument(
        "--cargo-contains",
        default=None,
        dest="cargo_contains",
        help="Filter by substring match on serialized cargo JSON.",
    )
    tape_list_slice_group = tape_list_parser.add_mutually_exclusive_group()
    tape_list_slice_group.add_argument(
        "--last",
        type=int,
        default=None,
        dest="last_n",
        help="Return only the last N matched entries.",
    )
    tape_list_slice_group.add_argument(
        "--first",
        type=int,
        default=None,
        dest="first_n",
        help="Return only the first N matched entries.",
    )
    tape_list_parser.add_argument(
        "--count",
        action="store_true",
        dest="count_only",
        help="Output only the count of matched entries.",
    )
    tape_list_parser.set_defaults(handler=_cmd_tape_list)

    tape_summary_parser = tape_subparsers.add_parser(
        "summary",
        help="Show a summary of tape contents.",
    )
    tape_summary_parser.add_argument(
        "--tape",
        required=True,
        dest="tape_path",
        help="Path to the JSONL tape file.",
    )
    tape_summary_parser.set_defaults(handler=_cmd_tape_summary)
