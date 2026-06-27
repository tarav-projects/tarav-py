"""Account-lifecycle sweep for the monitor — rotate (+ optionally materialize).

The framework-free heart of the account monitor workflow. `sweep_rotations` drives
the lifecycle primitives (`capture_all_homes` → `rotate_all` → optionally
`materialize_all`) across every provider with an auth-method. The auto workflow calls
it with ``materialize=False`` (registry-only); the ``m`` keystroke calls
`materialize_sweep` (``materialize=True``, writes homes). Rotation events are logged
by the `rotate` primitive itself to the durable accounts-log; the TUI's "5 rows of a
log" is rendered by `rotation_block_rows` from `read_recent_events`.
"""

from __future__ import annotations

from agentos.agent.auth_method_registry import providers_with_auth_methods
from agentos.agent.capture import capture_all_homes
from agentos.agent.materialization import materialize_all
from agentos.agent.monitor.models import MonitorTextRow
from agentos.agent.rotation import rotate_all


def sweep_rotations(*, materialize: bool) -> None:
    """Capture + rotate every provider (optionally materialize). Drive-only.

    Registry-only unless ``materialize`` (then homes are written via
    `materialize_all`). Best-effort per provider: one provider's failure neither
    aborts the sweep nor escapes to the monitor loop. Rotation events are persisted
    by the `rotate` primitive (to the accounts-log) — the sweep returns nothing."""

    for provider in providers_with_auth_methods():
        try:
            capture_all_homes(provider)
            rotate_all(provider)
            if materialize:
                materialize_all(provider)
        except Exception:
            continue  # per-provider isolation — never crash the tick/keystroke


def materialize_sweep() -> None:
    """The `m`-keystroke action: a full reconcile sweep (capture + rotate +
    materialize, writes homes). Rotations land in the accounts-log via the
    primitive; the TUI reads them back on the next render."""

    sweep_rotations(materialize=True)


def collect_non_aligned_homes() -> list[dict[str, object]]:
    """The current drifted homes across every provider (read-only, drift-only).

    Consumes the status-report primitive (`build_status_report`) per provider and
    keeps only entries whose status is in the ``drift`` family (``drift``,
    ``drift:home-newer``, ``drift:home-older``, ``drift:no-active``). Non-drift
    statuses (``aligned``, ``error:*``, ``undeterminable``) are excluded. Best-effort
    per provider: one provider's failure never blanks the rest. Each kept entry gets
    its ``provider`` attached; ordered by (provider, home) for a stable display."""

    from agentos.agent.account_status_report import build_status_report

    entries: list[dict[str, object]] = []
    for provider in providers_with_auth_methods():
        try:
            report = build_status_report(provider)
        except Exception:
            continue  # per-provider isolation — never crash the render
        homes = report.get("homes")
        if not isinstance(homes, list):
            continue
        for item in homes:
            if not isinstance(item, dict):
                continue
            if not str(item.get("status", "")).startswith("drift"):
                continue
            entries.append({**item, "provider": provider})
    return sorted(entries, key=lambda e: (str(e.get("provider")), str(e.get("home"))))


def non_aligned_block_rows(entries: list[dict[str, object]]) -> list[MonitorTextRow]:
    """Render drifted homes as TUI rows: ``[status] acct/method  home  — reason``."""

    rows: list[MonitorTextRow] = []
    for entry in entries:
        account = entry.get("account")
        method = entry.get("method")
        tag = f"{account}/{method}" if account and method else (str(account) if account else "")
        text = f"[{entry.get('status')}] {tag}  {entry.get('home')}".rstrip()
        reason = entry.get("reason")
        if reason:
            text += f"  — {reason}"
        rows.append(MonitorTextRow(text))
    return rows


def _short(ref: object) -> str:
    return str(ref)[:12] if ref else "-"


def rotation_block_rows(records: list[dict[str, object]]) -> list[MonitorTextRow]:
    """Render accounts-log ``rotate`` records as TUI rows; placeholder when empty.

    ``records`` come from `accounts_log.read_recent_events` (already newest-first):
    each is ``{recorded_at, provider, account, method, payload:{previous_active,
    new_active}}``."""

    if not records:
        return [MonitorTextRow("(no rotations yet)")]
    rows: list[MonitorTextRow] = []
    for record in records:
        account = f"{record.get('account')}/{record.get('method')}"
        payload = record.get("payload")
        payload = payload if isinstance(payload, dict) else {}
        rows.append(MonitorTextRow(
            f"{record.get('recorded_at')}  {record.get('provider')} {account}  "
            f"{_short(payload.get('previous_active'))}→{_short(payload.get('new_active'))}"
        ))
    return rows


__all__ = [
    "sweep_rotations",
    "materialize_sweep",
    "rotation_block_rows",
    "collect_non_aligned_homes",
    "non_aligned_block_rows",
]
