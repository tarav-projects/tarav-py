"""Account-lifecycle sweep for the monitor — rotate (+ optionally materialize).

The framework-free heart of the account monitor workflow. `sweep_rotations` drives
the lifecycle primitives (`capture_all_homes` → `rotate_all` → optionally
`materialize_all`) across every provider with an auth-method, returning the
rotations that actually changed the active pointer. The auto workflow calls it with
``materialize=False`` (registry-only); the ``m`` keystroke calls it with
``materialize=True`` (writes homes). `push_recent` keeps the last-N display ring and
`rotation_block_rows` renders it — the in-state "5 rows of a log" the TUI shows.
"""

from __future__ import annotations

from dataclasses import dataclass

from agentos._core.clock import utc_now_iso
from agentos.agent.auth_method_registry import providers_with_auth_methods
from agentos.agent.capture import capture_all_homes
from agentos.agent.materialization import materialize_all
from agentos.agent.monitor.models import MonitorState, MonitorTextRow
from agentos.agent.monitor_log import append_monitor_log_event
from agentos.agent.rotation import rotate_all

RECENT_LIMIT = 5
# The in-state rotation ring key — shared by the auto workflow and the `m` keystroke.
ACCOUNT_ROTATION_RECENT_KEY = "account_rotation_recent"


@dataclass(frozen=True)
class RotationEvent:
    ts: str
    provider: str
    account: str
    method: str
    prev: str | None  # previously active ref_id
    new: str | None  # newly active ref_id


def sweep_rotations(*, materialize: bool) -> list[RotationEvent]:
    """Capture + rotate every provider (optionally materialize); return changes.

    Registry-only unless ``materialize`` (then homes are written via
    `materialize_all`). Best-effort per provider: one provider's failure neither
    aborts the sweep nor escapes to the monitor loop. Each changed rotation is also
    written to the monitor audit log (best-effort; the display ring never depends on
    reading it back)."""

    events: list[RotationEvent] = []
    for provider in providers_with_auth_methods():
        try:
            capture_all_homes(provider)
            for result in rotate_all(provider):
                if not result.changed:
                    continue
                events.append(RotationEvent(
                    ts=utc_now_iso(), provider=provider, account=result.account,
                    method=result.method, prev=result.previous_active, new=result.new_active,
                ))
                append_monitor_log_event(
                    event="account_rotation", provider=provider,
                    account=f"{result.account}/{result.method}",
                    payload={"prev": result.previous_active, "new": result.new_active},
                )
            if materialize:
                materialize_all(provider)
        except Exception:
            continue  # per-provider isolation — never crash the tick/keystroke
    return events


def push_recent(
    recent: list[dict[str, object]], events: list[RotationEvent], *, limit: int = RECENT_LIMIT
) -> list[dict[str, object]]:
    """Append events to the chronological ring, keeping the last ``limit``."""

    rows = list(recent) + [
        {"ts": e.ts, "provider": e.provider, "account": e.account,
         "method": e.method, "prev": e.prev, "new": e.new}
        for e in events
    ]
    return rows[-limit:]


def materialize_sweep(state: MonitorState) -> list[RotationEvent]:
    """The `m`-keystroke action: a full reconcile sweep (writes homes), recorded.

    Runs `sweep_rotations(materialize=True)` — capture + rotate + materialize across
    providers — and folds any rotations into the in-state ring so the TUI log
    reflects them on the next render."""

    events = sweep_rotations(materialize=True)
    record_events(state, events)
    return events


def recent_from_state(state: MonitorState) -> list[dict[str, object]]:
    """The rotation ring stored in monitor state (empty when unset)."""

    recent = state.data.get(ACCOUNT_ROTATION_RECENT_KEY)
    return recent if isinstance(recent, list) else []


def record_events(state: MonitorState, events: list[RotationEvent]) -> None:
    """Fold sweep events into the in-state ring (no-op when there are none)."""

    if events:
        state.data[ACCOUNT_ROTATION_RECENT_KEY] = push_recent(recent_from_state(state), events)


def _short(ref: object) -> str:
    return str(ref)[:12] if ref else "-"


def rotation_block_rows(recent: list[dict[str, object]]) -> list[MonitorTextRow]:
    """Render the ring as TUI rows, newest first; a placeholder when empty."""

    if not recent:
        return [MonitorTextRow("(no rotations yet)")]
    rows: list[MonitorTextRow] = []
    for entry in reversed(recent):  # newest first
        account = f"{entry.get('account')}/{entry.get('method')}"
        rows.append(MonitorTextRow(
            f"{entry.get('ts')}  {entry.get('provider')} {account}  "
            f"{_short(entry.get('prev'))}→{_short(entry.get('new'))}"
        ))
    return rows


__all__ = [
    "ACCOUNT_ROTATION_RECENT_KEY",
    "RotationEvent",
    "sweep_rotations",
    "materialize_sweep",
    "push_recent",
    "recent_from_state",
    "record_events",
    "rotation_block_rows",
]
