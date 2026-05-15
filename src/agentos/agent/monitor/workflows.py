from __future__ import annotations

import datetime
import time
from typing import Any

from agentos._core.errors import CliError
from agentos.agent.monitor.loop import MonitorWorkflow
from agentos.agent.monitor.models import (
    MonitorFrame,
    MonitorResetRow,
    MonitorRow,
    MonitorState,
    MonitorTarget,
    MonitorTextRow,
    MonitorUsageTimeRow,
    MonitorWorkflowConfig,
)
from agentos.agent.providers import build_registered_account_agent


class LimitsTrackingWorkflow:
    name = "limits-tracking"

    def __init__(self, config: MonitorWorkflowConfig) -> None:
        self.config = config

    def run(self, state: MonitorState, frame: MonitorFrame) -> None:
        run_count = state.workflow_run_counts.get(self.name, 0) + 1
        state.workflow_run_counts[self.name] = run_count
        workflow_state = self._workflow_state(state)
        workflow_state["last_tick"] = frame.tick
        workflow_state["run_count"] = run_count
        workflow_state["refresh_interval_sec"] = self.config.refresh_interval_sec

        now = time.monotonic()
        target_states = self._target_states(workflow_state)
        for target in self.config.targets:
            target_key = _target_key(target)
            target_state = self._target_state(
                target_states, target=target, target_key=target_key
            )
            last_refresh_at = target_state.get("last_refresh_at_monotonic")
            should_refresh = not isinstance(last_refresh_at, int | float)
            if not should_refresh:
                should_refresh = (
                    now - float(last_refresh_at) >= self.config.refresh_interval_sec
                )
            if should_refresh:
                self._refresh_target(
                    target_state, target=target, now=now, tick=frame.tick
                )

        self._write_frame_block(frame, workflow_state=workflow_state)

    def _workflow_state(self, state: MonitorState) -> dict[str, object]:
        existing = state.data.get(self.name)
        if isinstance(existing, dict):
            return existing
        workflow_state: dict[str, object] = {
            "targets": {},
        }
        state.data[self.name] = workflow_state
        return workflow_state

    def _target_states(self, workflow_state: dict[str, object]) -> dict[str, object]:
        existing = workflow_state.get("targets")
        if isinstance(existing, dict):
            return existing
        target_states: dict[str, object] = {}
        workflow_state["targets"] = target_states
        return target_states

    def _target_state(
        self,
        target_states: dict[str, object],
        *,
        target: MonitorTarget,
        target_key: str,
    ) -> dict[str, object]:
        existing = target_states.get(target_key)
        if isinstance(existing, dict):
            return existing
        target_state = _new_target_state(target)
        target_states[target_key] = target_state
        return target_state

    def _refresh_target(
        self,
        target_state: dict[str, object],
        *,
        target: MonitorTarget,
        now: float,
        tick: int,
    ) -> None:
        try:
            agent = build_registered_account_agent(
                provider=target.provider, account=target.account, home=target.home
            )
            account_status = agent.account_status()
        except Exception as exc:
            target_state.update(
                {
                    "status": "error",
                    "last_refresh_at_monotonic": now,
                    "last_refresh_tick": tick,
                    "refresh_count": _target_refresh_count(target_state) + 1,
                    "account_status": None,
                    "error": {
                        "type": type(exc).__name__,
                        "message": str(exc),
                    },
                }
            )
            return
        target_state.update(
            {
                "status": "ok",
                "last_refresh_at_monotonic": now,
                "last_refresh_tick": tick,
                "refresh_count": _target_refresh_count(target_state) + 1,
                "account_status": account_status.summary(),
                "error": None,
            }
        )

    def _write_frame_block(
        self, frame: MonitorFrame, *, workflow_state: dict[str, object]
    ) -> None:
        rows: list[MonitorRow] = []
        target_summaries: list[dict[str, object]] = []
        target_states = self._target_states(workflow_state)
        for index, target in enumerate(self.config.targets):
            if index > 0:
                rows.append(MonitorTextRow(""))
            target_key = _target_key(target)
            raw_target_state = target_states.get(target_key)
            target_state = (
                raw_target_state if isinstance(raw_target_state, dict) else {}
            )
            target_summaries.append(_target_state_summary(target_state))
            rows.extend(_target_rows(target=target, target_state=target_state))
        data = {
            "refresh_interval_sec": self.config.refresh_interval_sec,
            "run_count": workflow_state.get("run_count"),
            "targets": target_summaries,
        }
        frame.add_block(self.name, rows=rows, data=data)


def build_monitor_workflows(
    configs: tuple[MonitorWorkflowConfig, ...],
) -> tuple[MonitorWorkflow, ...]:
    workflows: list[MonitorWorkflow] = []
    limits_tracking_configs = tuple(
        config for config in configs if config.name == "limits-tracking"
    )
    if limits_tracking_configs:
        workflows.append(
            LimitsTrackingWorkflow(
                _merge_limits_tracking_configs(limits_tracking_configs)
            )
        )
    for config in configs:
        if config.name == "limits-tracking":
            continue
        raise CliError(f"unknown monitor workflow {config.name!r}")
    return tuple(workflows)


def _merge_limits_tracking_configs(
    configs: tuple[MonitorWorkflowConfig, ...],
) -> MonitorWorkflowConfig:
    if len(configs) == 1:
        return configs[0]
    targets: list[MonitorTarget] = []
    target_keys: set[tuple[str, str, str]] = set()
    raw_configs: list[dict[str, object]] = []
    refresh_interval_sec = min(config.refresh_interval_sec for config in configs)
    for config in configs:
        for target in config.targets:
            target_key = (target.provider, target.account, str(target.home))
            if target_key in target_keys:
                continue
            target_keys.add(target_key)
            targets.append(target)
        raw_configs.append(config.raw_config)
    return MonitorWorkflowConfig(
        name="limits-tracking",
        targets=tuple(targets),
        refresh_interval_sec=refresh_interval_sec,
        raw_config={
            "workflow": "limits-tracking",
            "refresh_interval_sec": refresh_interval_sec,
            "configs": raw_configs,
        },
    )


def _target_key(target: MonitorTarget) -> str:
    return f"{target.provider}/{target.account}@{target.home}"


def _new_target_state(target: MonitorTarget) -> dict[str, object]:
    return {
        "provider": target.provider,
        "account": target.account,
        "home": str(target.home),
        "status": "pending",
        "refresh_count": 0,
    }


def _target_refresh_count(target_state: dict[str, object]) -> int:
    count = target_state.get("refresh_count", 0)
    if isinstance(count, int):
        return count
    return 0


def _target_state_summary(target_state: dict[str, object]) -> dict[str, object]:
    return dict(target_state)


def _target_rows(
    *, target: MonitorTarget, target_state: dict[str, object]
) -> list[MonitorRow]:
    rows: list[MonitorRow] = [MonitorTextRow(f"  {_target_title(target)}")]
    if target_state.get("status") == "error":
        rows.append(MonitorTextRow(f"    error | {_error_message(target_state)}"))
        return rows
    account_status = target_state.get("account_status")
    if isinstance(account_status, dict):
        limit_rows = _account_limit_rows(account_status)
        if limit_rows:
            rows.extend(limit_rows)
            return rows
        rows.append(MonitorTextRow(f"    usage | {_limits_summary(account_status)}"))
    return rows


def _target_title(target: MonitorTarget) -> str:
    prefix = "⬢ " if target.provider == "codex" else ""
    return f"{prefix}{target.provider}/{target.account}:"


def _error_message(target_state: dict[str, object]) -> str:
    error = target_state.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str) and message:
            return message
    return "unknown error"


def _account_limit_rows(account_status: dict[str, Any]) -> list[MonitorRow]:
    limits = account_status.get("limits")
    if not isinstance(limits, list):
        return []

    rows: list[MonitorRow] = []
    now = datetime.datetime.now(tz=datetime.UTC)
    for limit in limits:
        if not isinstance(limit, dict):
            continue
        usage_over_time = limit.get("usage_over_time")
        if not isinstance(usage_over_time, dict):
            continue
        used_percent = _int_value(usage_over_time.get("used_percent"))
        elapsed_percent = _elapsed_percent(usage_over_time, recorded_at=now)
        if used_percent is None or elapsed_percent is None:
            continue
        label = _limit_label(limit, usage_over_time)
        ratio = _usage_time_ratio(used_percent, elapsed_percent)
        rows.append(
            MonitorUsageTimeRow(
                _usage_time_line(
                    used_percent=used_percent,
                    elapsed_percent=elapsed_percent,
                    ratio=ratio,
                    label=label,
                ),
                used_percent=max(0, min(100, used_percent)),
                elapsed_percent=max(0, min(100, elapsed_percent)),
                ratio=ratio,
                label=label,
            )
        )
        reset_line = _reset_line(usage_over_time, recorded_at=now)
        if reset_line is not None:
            marker_percent = (
                max(0, min(100, used_percent))
                if used_percent > elapsed_percent
                else None
            )
            rows.append(
                MonitorResetRow(
                    reset_line,
                    elapsed_percent=max(0, min(100, elapsed_percent)),
                    marker_percent=marker_percent,
                )
            )
    return rows


def _usage_time_line(
    *, used_percent: int, elapsed_percent: int, ratio: float | None, label: str
) -> str:
    return (
        "    usage/time"
        f" | {_format_usage_percent_plain(used_percent)} / {_format_usage_percent_plain(elapsed_percent)}"
        f" = {_format_usage_time_ratio_text(ratio)}"
        f" | {label}"
    )


def _limits_summary(account_status: dict[str, Any]) -> str:
    usage_summary = account_status.get("usage_summary")
    if isinstance(usage_summary, str) and usage_summary:
        return usage_summary
    usage_error = _usage_error_message(account_status)
    if usage_error is not None:
        return f"error | {usage_error}"
    limits = account_status.get("limits")
    if not isinstance(limits, list) or not limits:
        return "none"
    summaries: list[str] = []
    for limit in limits:
        if not isinstance(limit, dict):
            continue
        label = limit.get("limit_label") or limit.get("limit_name")
        usage = limit.get("usage_over_time")
        if isinstance(label, str) and isinstance(usage, dict):
            used_percent = usage.get("used_percent")
            if isinstance(used_percent, int | float):
                summaries.append(f"{label} {used_percent}%")
    if summaries:
        return ", ".join(summaries)
    return "unknown"


def _usage_error_message(account_status: dict[str, Any]) -> str | None:
    usage_errors = account_status.get("usage_errors")
    if not isinstance(usage_errors, list) or not usage_errors:
        return None
    first_error = usage_errors[0]
    if not isinstance(first_error, dict):
        return "unknown usage error"
    message = first_error.get("message")
    if isinstance(message, str) and message:
        return message
    error_type = first_error.get("type")
    if isinstance(error_type, str) and error_type:
        return error_type
    return "unknown usage error"


def _limit_label(limit: dict[str, Any], usage_over_time: dict[str, object]) -> str:
    duration_mins = _int_value(usage_over_time.get("period_duration_mins"))
    if duration_mins == 300:
        return "Burst"
    if duration_mins == 10_080:
        return "Weekly"
    label = limit.get("limit_label") or limit.get("limit_name")
    if isinstance(label, str) and label:
        return label
    return "usage"


def _reset_line(
    usage_over_time: dict[str, object], *, recorded_at: datetime.datetime
) -> str | None:
    reset_at = _parse_datetime(_string_value(usage_over_time.get("resets_at")))
    if reset_at is None:
        reset_at = _parse_datetime(_string_value(usage_over_time.get("period_ends_at")))
    if reset_at is None:
        return None
    reset_display = reset_at.astimezone().strftime("%a %m-%d %H:%M")
    remaining_display = _format_remaining_duration(
        int((reset_at - recorded_at).total_seconds())
    )
    return f"        resets | {reset_display} | {remaining_display}"


def _elapsed_percent(
    usage_over_time: dict[str, object], *, recorded_at: datetime.datetime
) -> int | None:
    period_started_at = _parse_datetime(
        _string_value(usage_over_time.get("period_started_at"))
    )
    period_ends_at = _parse_datetime(
        _string_value(usage_over_time.get("period_ends_at"))
    )
    if period_started_at is None:
        duration_mins = _int_value(usage_over_time.get("period_duration_mins"))
        if duration_mins is not None and period_ends_at is not None:
            period_started_at = period_ends_at - datetime.timedelta(
                minutes=duration_mins
            )
    if period_ends_at is None:
        period_ends_at = _parse_datetime(
            _string_value(usage_over_time.get("resets_at"))
        )
    if (
        period_started_at is None
        or period_ends_at is None
        or period_ends_at <= period_started_at
    ):
        return None
    duration_seconds = (period_ends_at - period_started_at).total_seconds()
    if duration_seconds <= 0:
        return None
    elapsed_seconds = (recorded_at - period_started_at).total_seconds()
    elapsed_ratio = max(0.0, min(1.0, elapsed_seconds / duration_seconds))
    return round(elapsed_ratio * 100)


def _format_usage_percent_plain(value: int) -> str:
    return f"{max(0, min(100, value))}%".rjust(3)


def _usage_time_ratio(used_percent: int, elapsed_percent: int) -> float | None:
    clamped_elapsed_percent = max(0, min(100, elapsed_percent))
    if clamped_elapsed_percent == 0:
        return None
    clamped_used_percent = max(0, min(100, used_percent))
    return clamped_used_percent / clamped_elapsed_percent


def _format_usage_time_ratio_text(ratio: float | None) -> str:
    if ratio is None:
        return "n/a"
    return f"{ratio:.1f}"


def _format_remaining_duration(diff_seconds: int) -> str:
    if diff_seconds <= 0:
        return "0m"
    total_minutes = diff_seconds // 60
    if total_minutes == 0:
        total_minutes = 1
    days, remaining_minutes = divmod(total_minutes, 24 * 60)
    hours, minutes = divmod(remaining_minutes, 60)
    parts: list[str] = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    return " ".join(parts) or "0m"


def _parse_datetime(value: str | None) -> datetime.datetime | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=datetime.UTC)
    return parsed.astimezone(datetime.UTC)


def _int_value(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _string_value(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None
