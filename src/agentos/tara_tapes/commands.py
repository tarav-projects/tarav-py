from __future__ import annotations

import argparse
import json
from pathlib import Path

from agentos._core.json_input import load_json_arg, load_json_object_arg
from agentos.tara_tapes.check import check_tape, check_tapes
from agentos.tara_tapes.core import (
    append_tara_tape_stage_record,
    bootstrap_tara_tape,
    commit_tara_tape_stage,
    get_tara_tape_manifest_path,
    list_tara_tape_segments,
    load_tara_tape_manifest,
    read_tara_tape_records,
    read_tara_tape_segment_records,
    verify_tara_tape,
)
from agentos.tara_tapes.quarantine import quarantine_tapes


def _resolve_root(root: Path) -> Path:
    return root.expanduser().resolve()


def _cmd_tara_tapes_init(args: argparse.Namespace) -> int:
    root = _resolve_root(args.root)
    manifest_extra = load_json_object_arg(
        args.manifest_json,
        args.manifest_file,
        field_name="manifest",
    )
    manifest, created = bootstrap_tara_tape(
        root,
        tape_name=args.tape_name,
        created_at=args.created_at,
        manifest_extra=manifest_extra,
    )
    print(
        json.dumps(
            {
                "root_path": str(root),
                "manifest_path": str(get_tara_tape_manifest_path(root)),
                "tape_created": created,
                "manifest": manifest,
            },
            indent=2,
        )
    )
    return 0


def _cmd_tara_tapes_manifest(args: argparse.Namespace) -> int:
    root = _resolve_root(args.root)
    print(json.dumps(load_tara_tape_manifest(root), indent=2))
    return 0


def _cmd_tara_tapes_append(args: argparse.Namespace) -> int:
    root = _resolve_root(args.root)
    record = load_json_arg(args.record_json, args.record_file, field_name="record")
    stage_path = append_tara_tape_stage_record(
        root,
        writer_id=args.writer_id,
        segment_name=args.segment,
        record=record,
    )
    print(
        json.dumps(
            {
                "root_path": str(root),
                "writer_id": args.writer_id,
                "segment": args.segment,
                "stage_path": str(stage_path),
                "record": record,
            },
            indent=2,
        )
    )
    return 0


def _cmd_tara_tapes_commit(args: argparse.Namespace) -> int:
    root = _resolve_root(args.root)
    payload = {
        "root_path": str(root),
        **commit_tara_tape_stage(root),
    }
    print(json.dumps(payload, indent=2))
    return 0


def _cmd_tara_tapes_segments(args: argparse.Namespace) -> int:
    root = _resolve_root(args.root)
    segments = list_tara_tape_segments(root)
    print(
        json.dumps(
            {
                "root_path": str(root),
                "segments": segments,
                "segment_count": len(segments),
            },
            indent=2,
        )
    )
    return 0


def _cmd_tara_tapes_read_segment(args: argparse.Namespace) -> int:
    root = _resolve_root(args.root)
    records = read_tara_tape_segment_records(root, segment_name=args.segment)
    print(
        json.dumps(
            {
                "root_path": str(root),
                "segment": args.segment,
                "records": records,
                "record_count": len(records),
            },
            indent=2,
        )
    )
    return 0


def _cmd_tara_tapes_scan(args: argparse.Namespace) -> int:
    root = _resolve_root(args.root)
    records = read_tara_tape_records(root)
    print(
        json.dumps(
            {
                "root_path": str(root),
                "records": records,
                "record_count": len(records),
            },
            indent=2,
        )
    )
    return 0


def _cmd_tara_tapes_verify(args: argparse.Namespace) -> int:
    root = _resolve_root(args.root)
    print(json.dumps(verify_tara_tape(root), indent=2))
    return 0


def _cmd_tara_tapes_check(args: argparse.Namespace) -> int:
    root = _resolve_root(args.root)
    if args.single:
        result = check_tape(root)
    else:
        result = check_tapes(root)
    print(json.dumps(result, indent=2))
    return 0


def _cmd_tara_tapes_quarantine(args: argparse.Namespace) -> int:
    root = _resolve_root(args.root)
    quarantine_home = _resolve_root(args.quarantine_home) if args.quarantine_home else None
    result = quarantine_tapes(root, quarantine_home=quarantine_home)
    print(json.dumps(result, indent=2))
    return 0


def register_tara_tapes_commands(subparsers: argparse._SubParsersAction) -> None:
    tara_tapes_parser = subparsers.add_parser(
        "tara-tapes",
        help="Tara spec-first JSONL tape operations.",
    )
    tara_tapes_subparsers = tara_tapes_parser.add_subparsers(dest="tara_tapes_command")

    init_parser = tara_tapes_subparsers.add_parser(
        "init",
        help="Create a Tara-compliant tape root.",
    )
    init_parser.add_argument(
        "--root",
        required=True,
        type=Path,
        help="Tape root directory.",
    )
    init_parser.add_argument(
        "--tape-name",
        default=None,
        help="Manifest tape_name value (default: root folder name).",
    )
    init_parser.add_argument(
        "--created-at",
        default=None,
        help="Manifest created_at override (ISO 8601).",
    )
    init_parser.add_argument(
        "--manifest-json",
        default=None,
        help="Extra manifest JSON object merged into the created manifest.",
    )
    init_parser.add_argument(
        "--manifest-file",
        default=None,
        help="Path to JSON file with extra manifest fields.",
    )
    init_parser.set_defaults(handler=_cmd_tara_tapes_init)

    manifest_parser = tara_tapes_subparsers.add_parser(
        "manifest",
        help="Print the tape manifest.",
    )
    manifest_parser.add_argument(
        "--root",
        required=True,
        type=Path,
        help="Tape root directory.",
    )
    manifest_parser.set_defaults(handler=_cmd_tara_tapes_manifest)

    append_parser = tara_tapes_subparsers.add_parser(
        "append",
        help="Append one JSON value to a stage file.",
    )
    append_parser.add_argument(
        "--root",
        required=True,
        type=Path,
        help="Tape root directory.",
    )
    append_parser.add_argument(
        "--writer-id",
        required=True,
        help="Writer partition under stage/.",
    )
    append_parser.add_argument(
        "--segment",
        required=True,
        help="Segment filename under stage/<writer_id>/ (must end with .jsonl).",
    )
    append_record_group = append_parser.add_mutually_exclusive_group(required=True)
    append_record_group.add_argument(
        "--record-json",
        default=None,
        help="Inline JSON value to append.",
    )
    append_record_group.add_argument(
        "--record-file",
        default=None,
        help="Path to a file containing a JSON value to append.",
    )
    append_parser.set_defaults(handler=_cmd_tara_tapes_append)

    commit_parser = tara_tapes_subparsers.add_parser(
        "commit",
        help="Merge staged files into committed segments and delete processed stage files.",
    )
    commit_parser.add_argument(
        "--root",
        required=True,
        type=Path,
        help="Tape root directory.",
    )
    commit_parser.set_defaults(handler=_cmd_tara_tapes_commit)

    segments_parser = tara_tapes_subparsers.add_parser(
        "segments",
        help="List committed segment filenames.",
    )
    segments_parser.add_argument(
        "--root",
        required=True,
        type=Path,
        help="Tape root directory.",
    )
    segments_parser.set_defaults(handler=_cmd_tara_tapes_segments)

    read_segment_parser = tara_tapes_subparsers.add_parser(
        "read-segment",
        help="Read one committed segment as raw JSON values.",
    )
    read_segment_parser.add_argument(
        "--root",
        required=True,
        type=Path,
        help="Tape root directory.",
    )
    read_segment_parser.add_argument(
        "--segment",
        required=True,
        help="Committed segment filename to read.",
    )
    read_segment_parser.set_defaults(handler=_cmd_tara_tapes_read_segment)

    scan_parser = tara_tapes_subparsers.add_parser(
        "scan",
        help="Scan all committed segments as raw JSON values.",
    )
    scan_parser.add_argument(
        "--root",
        required=True,
        type=Path,
        help="Tape root directory.",
    )
    scan_parser.set_defaults(handler=_cmd_tara_tapes_scan)

    verify_parser = tara_tapes_subparsers.add_parser(
        "verify",
        help="Verify Tara tape layout and JSONL validity.",
    )
    verify_parser.add_argument(
        "--root",
        required=True,
        type=Path,
        help="Tape root directory.",
    )
    verify_parser.set_defaults(handler=_cmd_tara_tapes_verify)

    check_parser = tara_tapes_subparsers.add_parser(
        "check",
        help="Check tara-tapes-v0.1 conformance for tapes under a directory.",
    )
    check_parser.add_argument(
        "--root",
        required=True,
        type=Path,
        help="Directory containing tape subdirectories (or a single tape root with --single).",
    )
    check_parser.add_argument(
        "--single",
        action="store_true",
        default=False,
        help="Check a single tape root instead of scanning for tape subdirectories.",
    )
    check_parser.set_defaults(handler=_cmd_tara_tapes_check)

    quarantine_parser = tara_tapes_subparsers.add_parser(
        "quarantine",
        help="Move non-conformant tapes to ~/.taraproject/quarantine-tapes/.",
    )
    quarantine_parser.add_argument(
        "--root",
        required=True,
        type=Path,
        help="Directory containing tape subdirectories to check.",
    )
    quarantine_parser.add_argument(
        "--quarantine-home",
        default=None,
        type=Path,
        help="Override quarantine destination (default: ~/.taraproject/quarantine-tapes/).",
    )
    quarantine_parser.set_defaults(handler=_cmd_tara_tapes_quarantine)
