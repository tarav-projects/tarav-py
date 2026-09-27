# $kw: --from Account.Management
from __future__ import annotations

import datetime
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from tarav.l0._core.clock import iso_z
from tarav.l0._core.project import tarav_home_dir, home_path_str

MONITOR_LOG_CLASS = "agentos.agent.monitor-log"
MONITOR_LOG_SCHEMA_VERSION = 1


def monitor_log_dir() -> Path:
    return tarav_home_dir() / "agent" / "monitor-log"


def append_monitor_log_event(
    *,
    event: str,
    payload: Mapping[str, Any] | None = None,
    tick: int | None = None,
    provider: str | None = None,
    account: str | None = None,
    home: Path | str | None = None,
) -> Path | None:
    """Append one monitor event to today's dated JSONL log.

    The file rolls daily by ``YYYYMMDD.jsonl`` (UTC). This is **best-effort**:
    it never raises into the caller, so a logging failure can never crash or
    stall the monitor loop. Returns the written path on success, else ``None``.
    """
    try:
        recorded_at = datetime.datetime.now(tz=datetime.UTC)
        log_dir = monitor_log_dir()
        record_path = log_dir / f"{recorded_at:%Y%m%d}.jsonl"
        record = {
            "schema_version": MONITOR_LOG_SCHEMA_VERSION,
            "class": MONITOR_LOG_CLASS,
            "recorded_at": iso_z(recorded_at),
            "event": event,
            "tick": tick,
            "provider": provider,
            "account": account,
            "home": home_path_str(home),
            "payload": dict(payload) if payload is not None else {},
        }


        line = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
        log_dir.mkdir(parents=True, exist_ok=True)
        with record_path.open("a", encoding="utf-8") as handle:
            handle.write(line)
        return record_path
    except Exception:
        return None


__all__ = [
    "MONITOR_LOG_CLASS",
    "MONITOR_LOG_SCHEMA_VERSION",
    "append_monitor_log_event",
    "monitor_log_dir",
]
