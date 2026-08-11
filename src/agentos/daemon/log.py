# $kw: ^agentos-daemon-operational-log --from Agentos.Daemon --from Agentos.Hook --note [CT] daemon delivery and execution records exclude opaque hook context and exception text --supp ^c20260811-9u ^c20260811-50u
from __future__ import annotations

import datetime
import json
import os
from pathlib import Path

from agentos._core.clock import iso_z
from agentos._core.project import agentos_home_dir
from agentos.hooks import HookInvocation


DAEMON_LOG_CLASS = "agentos.daemon-event"
DAEMON_LOG_SCHEMA_VERSION = 1


def daemon_log_path(*, now: datetime.datetime | None = None) -> Path:
    current = now or datetime.datetime.now(tz=datetime.UTC)
    return agentos_home_dir() / "daemon" / "log" / f"{current:%Y%m%d}.jsonl"


def append_daemon_log(
    event: str,
    *,
    event_id: str | None = None,
    invocation: HookInvocation | None = None,
    callback_id: str | None = None,
    error: BaseException | None = None,
) -> Path | None:
    now = datetime.datetime.now(tz=datetime.UTC)
    record = {
        "schema_version": DAEMON_LOG_SCHEMA_VERSION,
        "class": DAEMON_LOG_CLASS,
        "recorded_at": iso_z(now),
        "event": event,
        "event_id": event_id,
        "hook_name": invocation.name if invocation is not None else None,
        "ctx_type": invocation.ctx_type if invocation is not None else None,
        "callback_id": callback_id,
        "error_type": type(error).__name__ if error is not None else None,
        "pid": os.getpid(),
    }
    path = daemon_log_path(now=now)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(path.parent.parent, 0o700)
        os.chmod(path.parent, 0o700)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")))
            handle.write("\n")
        os.chmod(path, 0o600)
    except OSError:
        return None
    return path


__all__ = ["append_daemon_log", "daemon_log_path"]
