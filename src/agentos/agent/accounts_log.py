"""The accounts lifecycle event log — a durable, secret-free audit of account
primitives (capture / activate / materialize / rotate).

Each primitive emits one event here on a real effect (never on a dry-run / no-op).
Because the `_all` sweeps and the CLI handlers all funnel through the per-item
primitives, every consumer inherits logging for free. Events carry only ids
(`ref_id` / `artifact_id`) and addresses — never `Auth.Data`.

The file rolls daily by ``YYYYMMDD.jsonl`` (UTC). Appending is **best-effort**: it
never raises into the calling primitive, so a logging failure can never break
capture/rotate/activate/materialize. Sibling to `monitor_log` (operational monitor
events), not a subtype.
"""

from __future__ import annotations

import datetime
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from agentos._core.project import agentos_home_dir

ACCOUNTS_LOG_CLASS = "agentos.agent.accounts-log"
ACCOUNTS_LOG_SCHEMA_VERSION = 1


def accounts_log_dir() -> Path:
    return agentos_home_dir() / "agent" / "accounts-log"


def append_account_event(
    *,
    event: str,
    provider: str,
    account: str,
    method: str,
    payload: Mapping[str, Any] | None = None,
    home: Path | str | None = None,
) -> Path | None:
    """Append one account-lifecycle event to today's dated JSONL log.

    Best-effort: returns the written path on success, else ``None``. Never raises
    into the caller.
    """
    try:
        recorded_at = datetime.datetime.now(tz=datetime.UTC)
        log_dir = accounts_log_dir()
        record_path = log_dir / f"{recorded_at:%Y%m%d}.jsonl"
        record = {
            "schema_version": ACCOUNTS_LOG_SCHEMA_VERSION,
            "class": ACCOUNTS_LOG_CLASS,
            "recorded_at": _iso_z(recorded_at),
            "event": event,
            "provider": provider,
            "account": account,
            "method": method,
            "home": _home_str(home),
            "payload": dict(payload) if payload is not None else {},
        }
        # Serialize before opening the file so an unserializable payload leaves no
        # partial line behind.
        line = json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
        log_dir.mkdir(parents=True, exist_ok=True)
        with record_path.open("a", encoding="utf-8") as handle:
            handle.write(line)
        return record_path
    except Exception:
        return None


def read_recent_events(
    *, event: str | None = None, limit: int = 5
) -> list[dict[str, Any]]:
    """The most-recent account-lifecycle events, newest-first (best-effort).

    Scans the dated ``YYYYMMDD.jsonl`` files newest filename first (dates sort
    lexically) and collects records — optionally filtered to a single ``event`` —
    until ``limit`` is reached, so "last N" can span a day boundary. Missing dir,
    unreadable files, and malformed lines are skipped; never raises.
    """
    if limit <= 0:
        return []
    out: list[dict[str, Any]] = []
    log_dir = accounts_log_dir()
    try:
        files = sorted(log_dir.glob("*.jsonl"), reverse=True)
    except Exception:
        return []
    for path in files:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except Exception:
            continue
        for line in reversed(lines):  # within a file, newest line is last
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except Exception:
                continue
            if not isinstance(record, dict):
                continue
            if event is not None and record.get("event") != event:
                continue
            out.append(record)
            if len(out) >= limit:
                return out
    return out


def _home_str(home: Path | str | None) -> str | None:
    if home is None:
        return None
    try:
        return str(Path(home).expanduser())
    except Exception:
        return str(home)


def _iso_z(value: datetime.datetime) -> str:
    return value.astimezone(datetime.UTC).isoformat().replace("+00:00", "Z")


__all__ = [
    "ACCOUNTS_LOG_CLASS",
    "ACCOUNTS_LOG_SCHEMA_VERSION",
    "accounts_log_dir",
    "append_account_event",
    "read_recent_events",
]
