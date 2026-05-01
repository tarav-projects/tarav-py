from __future__ import annotations

import json
from pathlib import Path

from agentos._core.clock import utc_now_iso
from agentos._core.project import AgentosProjectHandler, agentos_home_dir

PROJECT_COMMAND_LOG_SCHEMA_VERSION = 1
PROJECT_COMMAND_LOG_DIR = ("projects", "activity")


def project_command_log_path(*, timetag: str | None = None) -> Path:
    effective_timetag = utc_now_iso() if timetag is None else timetag
    year_month = effective_timetag[:4] + effective_timetag[5:7]
    return agentos_home_dir().joinpath(*PROJECT_COMMAND_LOG_DIR, f"{year_month}.jsonl")


def record_project_command(
    *,
    project: AgentosProjectHandler,
    agentos_command: dict[str, object],
) -> None:
    timetag = utc_now_iso()
    event = {
        "schema_version": PROJECT_COMMAND_LOG_SCHEMA_VERSION,
        "timetag": timetag,
        "project_id": project.project_id,
        "project_root": str(project.root),
        "agentos_command": agentos_command,
    }

    path = project_command_log_path(timetag=timetag)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event, sort_keys=True) + "\n")
    except OSError:
        return


def command_payload_from_args(args: object) -> dict[str, object]:
    command_parts: list[str] = []
    current = getattr(args, "command", None)
    while isinstance(current, str) and current:
        command_parts.append(current)
        attr_name = "_".join(
            [part.replace("-", "_") for part in command_parts] + ["command"]
        )
        current = getattr(args, attr_name, None)

    payload: dict[str, object] = {
        "command": " ".join(command_parts),
        "argv": list(getattr(args, "_agentos_argv", [])),
    }
    return payload
