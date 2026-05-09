from __future__ import annotations

import argparse
import json
from pathlib import Path

from agentos._core.errors import CliError
from agentos._core.ids import generate_uuid4_string, validate_uuid_string
from agentos._core.project import (
    AgentosProjectHandler,
    add_explicit_project_arguments,
    require_explicit_agentos_project,
)
from agentos._core.project_command_log import (
    project_command_log_path,
    record_project_command_from_args,
)
from agentos.utils.tmp_folder import allocate_project_tmp_folder


def _cmd_utils_uuid(args: argparse.Namespace) -> int:
    count = int(args.count)
    if count < 1:
        raise CliError("--count must be >= 1")

    uuids = [validate_uuid_string(generate_uuid4_string()) for _ in range(count)]

    if args.json:
        payload: dict[str, object] = {
            "status": "ok",
            "command": "utils uuid",
            "count": count,
            "uuids": uuids,
        }
        if count == 1:
            payload["uuid"] = uuids[0]
        print(json.dumps(payload))
        return 0

    print("\n".join(uuids))
    return 0


def _cmd_utils_tmp_folder_new(args: argparse.Namespace) -> int:
    project = require_explicit_agentos_project(
        project=args.project,
        project_base=args.project_base,
        command_name="agentos utils tmp-folder new",
    )
    record_project_command_from_args(
        project=project,
        args=args,
    )
    folder_path = allocate_project_tmp_folder(
        create=bool(args.create),
        project=project.root,
    )
    print(str(folder_path))
    return 0


def _cmd_utils_cmd_logger_path(args: argparse.Namespace) -> int:
    print(str(project_command_log_path(timetag=_timetag_from_month(args.month))))
    return 0


def _cmd_utils_cmd_logger_tail(args: argparse.Namespace) -> int:
    limit = int(args.limit)
    if limit < 1:
        raise CliError("--limit must be >= 1")

    path = project_command_log_path(timetag=_timetag_from_month(args.month))
    for line in _read_cmd_logger_lines(path)[-limit:]:
        if args.json:
            print(line)
            continue
        event = json.loads(line)
        print(_format_cmd_logger_event_row(event))
    return 0


def _cmd_utils_cmd_logger_query(args: argparse.Namespace) -> int:
    limit = int(args.limit)
    if limit < 1:
        raise CliError("--limit must be >= 1")

    path = project_command_log_path(timetag=_timetag_from_month(args.month))
    events = [
        _annotate_cmd_logger_event(json.loads(line))
        for line in _read_cmd_logger_lines(path)
    ]
    filtered_events = [
        event for event in events if _cmd_logger_event_matches_query(event, args)
    ][-limit:]

    if args.json:
        payload = {
            "status": "ok",
            "command": "utils cmd-logger query",
            "month": _month_label(args.month),
            "path": str(path),
            "filters": {
                "under": (
                    str(_normalize_path_filter(args.under))
                    if args.under is not None
                    else None
                ),
                "exists": args.exists,
                "valid_project": args.valid_project,
                "project_id": args.project_id,
                "command": args.command,
                "limit": limit,
            },
            "count": len(filtered_events),
            "events": filtered_events,
        }
        print(json.dumps(payload, indent=2))
        return 0

    for event in filtered_events:
        print(_format_cmd_logger_event_row(event, include_status=True))
    return 0


def _timetag_from_month(month: str | None) -> str | None:
    if month is None:
        return None
    normalized = month.strip()
    if len(normalized) != 6 or not normalized.isdigit():
        raise CliError("--month must use YYYYMM format")
    return f"{normalized[:4]}-{normalized[4:]}-01T00:00:00Z"


def _month_label(month: str | None) -> str:
    timetag = _timetag_from_month(month)
    if timetag is None:
        path = project_command_log_path()
        return path.stem
    return timetag[:4] + timetag[5:7]


def _read_cmd_logger_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [
        line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _format_cmd_logger_event_row(
    event: dict[str, object],
    *,
    include_status: bool = False,
) -> str:
    command = _event_command(event)
    fields = [
        str(event.get("timetag", "")),
        str(event.get("project_id", "")),
    ]
    if include_status:
        fields.extend(
            [
                _format_bool_field(event.get("project_exists")),
                _format_bool_field(event.get("valid_project")),
            ]
        )
    fields.extend([command, str(event.get("project_root", ""))])
    return "\t".join(fields)


def _format_bool_field(value: object) -> str:
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return ""


def _event_command(event: dict[str, object]) -> str:
    command_payload = event.get("agentos_command", {})
    if not isinstance(command_payload, dict):
        return ""
    return str(command_payload.get("command", ""))


def _annotate_cmd_logger_event(event: dict[str, object]) -> dict[str, object]:
    annotated = dict(event)
    root = _event_project_root(event)
    project_exists = root.exists()
    annotated["project_exists"] = project_exists
    annotated["valid_project"] = _valid_agentos_project(root) if project_exists else False
    return annotated


def _event_project_root(event: dict[str, object]) -> Path:
    return Path(str(event.get("project_root", ""))).expanduser().resolve()


def _valid_agentos_project(root: Path) -> bool:
    try:
        AgentosProjectHandler(root).validate()
    except (CliError, OSError, ValueError, KeyError, TypeError):
        return False
    return True


def _cmd_logger_event_matches_query(
    event: dict[str, object],
    args: argparse.Namespace,
) -> bool:
    if args.project_id is not None and event.get("project_id") != args.project_id:
        return False
    if args.command is not None and args.command not in _event_command(event):
        return False
    if args.under is not None and not _path_is_under(
        _event_project_root(event),
        _normalize_path_filter(args.under),
    ):
        return False
    if not _tri_state_matches(args.exists, bool(event.get("project_exists"))):
        return False
    if not _tri_state_matches(args.valid_project, bool(event.get("valid_project"))):
        return False
    return True


def _normalize_path_filter(path: Path | str) -> Path:
    return Path(path).expanduser().resolve()


def _path_is_under(path: Path, root: Path) -> bool:
    return path == root or path.is_relative_to(root)


def _tri_state_matches(filter_value: str, actual: bool) -> bool:
    if filter_value == "any":
        return True
    if filter_value == "yes":
        return actual
    if filter_value == "no":
        return not actual
    raise AssertionError(f"unsupported tri-state value: {filter_value}")


def register_utils_commands(subparsers: argparse._SubParsersAction) -> None:
    utils_parser = subparsers.add_parser(
        "utils",
        help="General utility helpers for agents.",
    )
    utils_subparsers = utils_parser.add_subparsers(dest="utils_command", required=True)

    uuid_parser = utils_subparsers.add_parser(
        "uuid",
        help="Generate UUIDv4 identifiers.",
    )
    uuid_parser.add_argument(
        "--count",
        type=int,
        default=1,
        help="Number of UUIDs to generate.",
    )
    uuid_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON payload with generated UUIDs.",
    )
    uuid_parser.set_defaults(handler=_cmd_utils_uuid)

    tmp_folder_parser = utils_subparsers.add_parser(
        "tmp-folder",
        help="Allocate temporary folders under an existing project's .agentos/tmp.",
    )
    tmp_folder_subparsers = tmp_folder_parser.add_subparsers(
        dest="utils_tmp_folder_command",
        required=True,
    )

    tmp_folder_new_parser = tmp_folder_subparsers.add_parser(
        "new",
        help="Generate a random tmp-folder path under the resolved existing project's .agentos/tmp.",
    )
    tmp_folder_new_parser.add_argument(
        "--create",
        action="store_true",
        help="Create the generated folder. By default only prints the path.",
    )
    add_explicit_project_arguments(
        tmp_folder_new_parser,
        project_help=(
            "Required project selector unless --project-base is supplied. "
            "Bare --project targets current pwd. "
            "Tmp-folder allocation requires an existing project."
        ),
    )
    tmp_folder_new_parser.set_defaults(handler=_cmd_utils_tmp_folder_new)

    cmd_logger_parser = utils_subparsers.add_parser(
        "cmd-logger",
        help="Inspect the rare-use project command activity log.",
    )
    cmd_logger_subparsers = cmd_logger_parser.add_subparsers(
        dest="utils_cmd_logger_command",
        required=True,
    )

    cmd_logger_path_parser = cmd_logger_subparsers.add_parser(
        "path",
        help="Print the project command activity log path for a month.",
    )
    cmd_logger_path_parser.add_argument(
        "--month",
        help="Month to inspect in YYYYMM format. Defaults to the current UTC month.",
    )
    cmd_logger_path_parser.set_defaults(handler=_cmd_utils_cmd_logger_path)

    cmd_logger_tail_parser = cmd_logger_subparsers.add_parser(
        "tail",
        help="Print recent project command activity events.",
    )
    cmd_logger_tail_parser.add_argument(
        "--month",
        help="Month to inspect in YYYYMM format. Defaults to the current UTC month.",
    )
    cmd_logger_tail_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of events to print.",
    )
    cmd_logger_tail_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit raw JSONL events.",
    )
    cmd_logger_tail_parser.set_defaults(handler=_cmd_utils_cmd_logger_tail)

    cmd_logger_query_parser = cmd_logger_subparsers.add_parser(
        "query",
        help="Filter project command activity events.",
    )
    cmd_logger_query_parser.add_argument(
        "--month",
        help="Month to inspect in YYYYMM format. Defaults to the current UTC month.",
    )
    cmd_logger_query_parser.add_argument(
        "--under",
        type=Path,
        help="Keep events whose project root is equal to or under this path.",
    )
    cmd_logger_query_parser.add_argument(
        "--exists",
        choices=("any", "yes", "no"),
        default="any",
        help="Filter by whether the logged project root currently exists.",
    )
    cmd_logger_query_parser.add_argument(
        "--valid-project",
        choices=("any", "yes", "no"),
        default="any",
        help="Filter by whether the logged root is currently a valid Agentos project.",
    )
    cmd_logger_query_parser.add_argument(
        "--project-id",
        help="Keep events with this exact logged project id.",
    )
    cmd_logger_query_parser.add_argument(
        "--command",
        help="Keep events whose logged command contains this text.",
    )
    cmd_logger_query_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of matching events to print.",
    )
    cmd_logger_query_parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a structured JSON payload.",
    )
    cmd_logger_query_parser.set_defaults(handler=_cmd_utils_cmd_logger_query)
