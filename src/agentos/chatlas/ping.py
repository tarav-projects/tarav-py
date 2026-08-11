from __future__ import annotations

import json
import secrets
import time as _time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agentos.chatlas.core import chatlas_update
from agentos.chatlas.paths import default_chatlas_root
from agentos.chatlas.query import chatlas_query
from agentos.chatlas.time_interface import format_local_timestamp

_PING_STATE_DIRNAME = "ping"
_PING_STATE_FILENAME = "state.json"
_PENDING_MAX_AGE = timedelta(hours=24)
_ACTIVE_AFTER_SLACK = timedelta(seconds=60)


def ping_state_path(chatlas_root: Path | None = None) -> Path:
    root = chatlas_root if chatlas_root is not None else default_chatlas_root()
    return root / _PING_STATE_DIRNAME / _PING_STATE_FILENAME


def _load_pending(state_path: Path, *, now: datetime) -> list[dict]:
    if not state_path.exists():
        return []
    try:
        state = json.loads(state_path.read_text())
    except (json.JSONDecodeError, OSError):
        return []
    pending = []
    for record in state.get("pending", []):
        try:
            emitted_at = datetime.fromisoformat(record["emitted_at"])
        except (KeyError, ValueError):
            continue
        if now - emitted_at <= _PENDING_MAX_AGE:
            pending.append(record)
    return pending


def _save_pending(state_path: Path, pending: list[dict]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps({"pending": pending}, indent=2) + "\n")


def chatlas_ping(
    *,
    lines: int = 5,
    interval_seconds: float = 1.0,
    rounds: int = 4,
    window_seconds: int = 300,
    providers: tuple[str, ...] | None = None,
    chatlas_root: Path | None = None,
    update_fn=chatlas_update,
    query_fn=chatlas_query,
    sleep=_time.sleep,
    emit=print,
) -> dict[str, object]:
    state_path = ping_state_path(chatlas_root)
    now = datetime.now(timezone.utc)
    run_id = secrets.token_hex(4)

    pending = _load_pending(state_path, now=now)
    current_run: list[dict] = []
    previous_resolved: list[dict] = []
    self_resolved: list[dict] = []
    round_reports: list[dict] = []

    def _probe(record: dict, *, resolved_at: datetime) -> dict | None:
        emitted_at = datetime.fromisoformat(record["emitted_at"])
        active_after = (emitted_at - _ACTIVE_AFTER_SLACK).isoformat()
        payload = query_fn(
            tool_contains=(record["marker"],),
            active_after=active_after,
            providers=providers,
            chatlas_root=chatlas_root,
        )
        rows = [row for row in payload.get("rows", []) if isinstance(row, dict)]
        if not rows:
            return None
        row = rows[0]
        return {
            **record,
            "session_id": row.get("session_id"),
            "identity_hash": row.get("identity_hash"),
            "resolved_at": resolved_at.isoformat(),
            "latency_seconds": max(0.0, (resolved_at - emitted_at).total_seconds()),
        }

    for round_number in range(1, rounds + 1):
        emitted_markers = []
        for line_number in range(1, lines + 1):
            emitted_at = datetime.now(timezone.utc)
            marker = f"chatlas-ping-{run_id}-r{round_number}-{line_number:02d}"
            emit(f"{marker} {format_local_timestamp(emitted_at.isoformat())}")
            record = {
                "marker": marker,
                "run_id": run_id,
                "emitted_at": emitted_at.isoformat(),
            }
            current_run.append(record)
            emitted_markers.append(marker)
            if line_number < lines and interval_seconds > 0:
                sleep(interval_seconds)

        update_fn(providers=providers, window_seconds=window_seconds, chatlas_root=chatlas_root)

        check_time = datetime.now(timezone.utc)
        round_found: list[str] = []
        for record in list(pending):
            resolution = _probe(record, resolved_at=check_time)
            if resolution is not None:
                previous_resolved.append(resolution)
                pending.remove(record)
                round_found.append(record["marker"])
        for record in list(current_run):
            resolution = _probe(record, resolved_at=check_time)
            if resolution is not None:
                self_resolved.append(resolution)
                current_run.remove(record)
                round_found.append(record["marker"])
        round_reports.append({
            "round": round_number,
            "emitted": emitted_markers,
            "found": round_found,
        })

    remaining = pending + current_run
    _save_pending(state_path, remaining)

    return {
        "status": "ok",
        "command": "chatlas ping",
        "run_id": run_id,
        "config": {
            "lines": lines,
            "interval_seconds": interval_seconds,
            "rounds": rounds,
            "window_seconds": window_seconds,
            "providers": list(providers) if providers is not None else None,
        },
        "rounds": round_reports,
        "self_visible": bool(self_resolved),
        "self_resolved": self_resolved,
        "previous_resolved": previous_resolved,
        "pending_count": len(remaining),
        "state_path": str(state_path),
    }


__all__ = ["chatlas_ping", "ping_state_path"]
