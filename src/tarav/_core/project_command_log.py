# $kw: --from Agentos.Project
from __future__ import annotations

import json
from pathlib import Path

from tarav._core.clock import utc_now_iso
from tarav._core.project import TaravProjectHandler, tarav_home_dir

ACTIVITY_LOG_SCHEMA_VERSION = 2
ACTIVITY_LOG_DIR = ("activity",)


def activity_log_path(*, timetag: str | None = None) -> Path:
    effective_timetag = utc_now_iso() if timetag is None else timetag
    year_month = effective_timetag[:4] + effective_timetag[5:7]
    return tarav_home_dir().joinpath(*ACTIVITY_LOG_DIR, f"{year_month}.jsonl")


def record_activity_event(
    *,
    event_type: str,
    command: str,
    argv: list[str] | tuple[str, ...],
    status: str,
    payload: dict[str, object],
) -> None:
    timetag = utc_now_iso()
    event = {
        "schema_version": ACTIVITY_LOG_SCHEMA_VERSION,
        "timetag": timetag,
        "event_type": event_type,
        "command": command,
        "argv": list(argv),
        "status": status,
        "payload": payload,
    }

    path = activity_log_path(timetag=timetag)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event, sort_keys=True) + "\n")
    except OSError:
        return


def record_project_command(
    *,
    project: TaravProjectHandler,
    agentos_command: dict[str, object],
) -> None:
    payload = {
        "project_id": project.project_id,
        "project_root": str(project.root),
        "agentos_command": agentos_command,
    }
    record_activity_event(
        event_type="project.command",
        command=str(agentos_command.get("command", "")),
        argv=list(agentos_command.get("argv", [])),
        status="ok",
        payload=payload,
    )


def record_project_command_from_args(
    *,
    project: TaravProjectHandler,
    args: object,
) -> None:
    record_project_command(
        project=project,
        agentos_command=command_payload_from_args(args),
    )


def command_payload_from_args(args: object) -> dict[str, object]:
    command_parts: list[str] = []
    current = getattr(args, "command", None)
    while isinstance(current, str) and current:
        command_parts.append(current)
        current_key = current.replace("-", "_")
        nested_attr_name = "_".join(
            [part.replace("-", "_") for part in command_parts] + ["command"]
        )
        local_attr_name = f"{current_key}_command"
        current = getattr(args, nested_attr_name, getattr(args, local_attr_name, None))

    payload: dict[str, object] = {
        "command": " ".join(command_parts),
        "argv": list(getattr(args, "_agentos_argv", [])),
    }
    return payload


__all__ = [
    "activity_log_path",
    "command_payload_from_args",
    "record_activity_event",
    "record_project_command",
    "record_project_command_from_args",
]
