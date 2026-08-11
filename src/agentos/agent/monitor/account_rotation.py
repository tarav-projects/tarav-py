# $kw: --from Account.Management
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

from dataclasses import dataclass
from pathlib import Path

from agentos.agent.auth_method_registry import providers_with_auth_methods
from agentos.agent.capture import capture_all_homes
from agentos.agent.materialization import MaterializeResult
from agentos.agent.materialization import materialize_all
from agentos.agent.monitor.models import MonitorInfoRow, MonitorTextRow
from agentos.agent.rotation import rotate_all

ACCOUNT_MATERIALIZE_STATE_KEY = "account_materialize"
ACCOUNT_MATERIALIZE_BLOCK_TITLE = "account-materialize"
MATERIALIZE_STATUS_REQUESTED = "requested"
MATERIALIZE_STATUS_QUEUED = "queued"
MATERIALIZE_STATUS_RUNNING = "running"
MATERIALIZE_STATUS_DONE = "done"
MATERIALIZE_STATUS_SKIPPED = "skipped"
MATERIALIZE_STATUS_FAILED = "failed"
MATERIALIZE_TOP_ROW_STATUSES = frozenset(
    {
        MATERIALIZE_STATUS_REQUESTED,
        MATERIALIZE_STATUS_QUEUED,
        MATERIALIZE_STATUS_RUNNING,
    }
)
MATERIALIZE_VISIBLE_RESULT_STATUSES = frozenset({"materialized", "skipped", "error"})


@dataclass(frozen=True)
class MonitorMaterializeResult:
    provider: str
    status: str
    account: str = ""
    method: str = ""
    home: Path | None = None
    active_ref: str | None = None
    error_type: str | None = None
    message: str | None = None


def _monitor_materialize_result(result: MaterializeResult) -> MonitorMaterializeResult:
    return MonitorMaterializeResult(
        provider=result.provider,
        account=result.account,
        method=result.method,
        home=result.home,
        active_ref=result.active_ref,
        status=result.status,
    )


def sweep_rotations(*, materialize: bool) -> list[MonitorMaterializeResult]:
    """Capture + rotate every provider (optionally materialize). Drive-only.

    Registry-only unless ``materialize`` (then homes are written via
    `materialize_all`). Best-effort per provider: one provider's failure neither
    aborts the sweep nor escapes to the monitor loop. Rotation events are persisted
    by the `rotate` primitive (to the accounts-log)."""

    results: list[MonitorMaterializeResult] = []
    for provider in providers_with_auth_methods():
        try:
            capture_all_homes(provider)
            rotate_all(provider)
            if materialize:
                results.extend(
                    _monitor_materialize_result(result)
                    for result in materialize_all(provider)
                )
        except Exception as exc:
            if materialize:
                results.append(
                    MonitorMaterializeResult(
                        provider=provider,
                        status="error",
                        error_type=type(exc).__name__,
                        message=str(exc),
                    )
                )
            continue
    return results


def materialize_sweep() -> list[MonitorMaterializeResult]:
    """The `m`-keystroke action: a full reconcile sweep (capture + rotate +
    materialize, writes homes). Rotations land in the accounts-log via the
    primitive; the TUI reads them back on the next render."""

    return sweep_rotations(materialize=True)


def set_materialize_state(
    state_data: dict[str, object],
    *,
    tick: int,
    status: str,
) -> None:
    state_data[ACCOUNT_MATERIALIZE_STATE_KEY] = {
        "tick": tick,
        "status": status,
    }


def set_materialize_summary(
    state_data: dict[str, object],
    summary: dict[str, object],
) -> None:
    state_data[ACCOUNT_MATERIALIZE_STATE_KEY] = summary


def materialize_state_payload(state_data: dict[str, object]) -> dict[str, object] | None:
    materialize_state = state_data.get(ACCOUNT_MATERIALIZE_STATE_KEY)
    return materialize_state if isinstance(materialize_state, dict) else None


def materialize_status(state_data: dict[str, object]) -> str | None:
    materialize_state = materialize_state_payload(state_data)
    if materialize_state is None:
        return None
    status = materialize_state.get("status")
    return status if isinstance(status, str) else None


def materialize_summary_payload(
    results: list[MonitorMaterializeResult],
    *,
    tick: int,
) -> dict[str, object]:
    counts = {
        "materialized": 0,
        "aligned": 0,
        "skipped": 0,
        "check": 0,
        "error": 0,
    }
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
    if counts.get("error", 0):
        status = MATERIALIZE_STATUS_FAILED
    elif counts.get("materialized", 0):
        status = MATERIALIZE_STATUS_DONE
    elif counts.get("skipped", 0):
        status = MATERIALIZE_STATUS_SKIPPED
    else:
        status = MATERIALIZE_STATUS_DONE
    return {
        "tick": tick,
        "status": status,
        "counts": counts,
        "results": [
            {
                "provider": result.provider,
                "account": result.account,
                "method": result.method,
                "home": str(result.home) if result.home is not None else None,
                "active_ref": result.active_ref,
                "status": result.status,
                "error_type": result.error_type,
                "message": result.message,
            }
            for result in results
        ],
    }


def materialize_status_block_rows(summary: dict[str, object]) -> list[MonitorTextRow | MonitorInfoRow]:
    rows: list[MonitorTextRow | MonitorInfoRow] = [
        MonitorInfoRow("status", str(summary.get("status", "unknown"))),
        _materialize_count_row(summary),
    ]
    result_rows = _materialize_result_rows(summary, limit=5)
    rows.extend(result_rows)
    if not result_rows:
        rows.append(MonitorTextRow("(no drifted homes required materialization)"))
    return rows


def _materialize_count_row(summary: dict[str, object]) -> MonitorTextRow:
    counts = _materialize_counts(summary)
    return MonitorTextRow(
        "materialized: {materialized}  skipped: {skipped}  failed: {error}".format(
            materialized=counts.get("materialized", 0),
            skipped=counts.get("skipped", 0),
            error=counts.get("error", 0),
        )
    )


def _materialize_counts(summary: dict[str, object]) -> dict[str, object]:
    counts = summary.get("counts")
    return counts if isinstance(counts, dict) else {}


def _materialize_result_rows(
    summary: dict[str, object],
    *,
    limit: int,
) -> list[MonitorTextRow]:
    rows: list[MonitorTextRow] = []
    results = summary.get("results")
    if not isinstance(results, list):
        return rows
    for item in results:
        if len(rows) >= limit:
            return rows
        if not isinstance(item, dict):
            continue
        if item.get("status") not in MATERIALIZE_VISIBLE_RESULT_STATUSES:
            continue
        rows.append(_materialize_result_row(item))
    return rows


def _materialize_result_row(item: dict[str, object]) -> MonitorTextRow:
    home = item.get("home") or "-"
    account = item.get("account")
    method = item.get("method")
    tag = f"{account}/{method}" if account and method else "-"
    text = f"[{item.get('status', 'unknown')}] {item.get('provider')} {tag}  {home}"
    message = item.get("message")
    if message:
        text += f"  — {message}"
    return MonitorTextRow(text)


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
            continue
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
    "MonitorMaterializeResult",
    "ACCOUNT_MATERIALIZE_STATE_KEY",
    "ACCOUNT_MATERIALIZE_BLOCK_TITLE",
    "MATERIALIZE_STATUS_REQUESTED",
    "MATERIALIZE_STATUS_QUEUED",
    "MATERIALIZE_STATUS_RUNNING",
    "MATERIALIZE_STATUS_DONE",
    "MATERIALIZE_STATUS_SKIPPED",
    "MATERIALIZE_STATUS_FAILED",
    "MATERIALIZE_TOP_ROW_STATUSES",
    "MATERIALIZE_VISIBLE_RESULT_STATUSES",
    "set_materialize_state",
    "set_materialize_summary",
    "materialize_state_payload",
    "materialize_status",
    "materialize_summary_payload",
    "materialize_status_block_rows",
    "rotation_block_rows",
    "collect_non_aligned_homes",
    "non_aligned_block_rows",
]
