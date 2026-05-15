from __future__ import annotations

import time
from typing import Any

from agentos._core.errors import CliError
from agentos.agent.monitor.loop import MonitorWorkflow
from agentos.agent.monitor.models import MonitorFrame, MonitorState, MonitorTarget, MonitorWorkflowConfig
from agentos.agent.providers import build_registered_account_agent


class LimitsTrackingWorkflow:
    name = "limits-tracking"

    def __init__(self, config: MonitorWorkflowConfig) -> None:
        self.config = config
        self._frame_block_index: int | None = None

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
            target_state = self._target_state(target_states, target=target, target_key=target_key)
            last_refresh_at = target_state.get("last_refresh_at_monotonic")
            should_refresh = not isinstance(last_refresh_at, int | float)
            if not should_refresh:
                should_refresh = now - float(last_refresh_at) >= self.config.refresh_interval_sec
            if should_refresh:
                self._refresh_target(target_state, target=target, now=now, tick=frame.tick)

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
        target_state: dict[str, object] = {
            "provider": target.provider,
            "account": target.account,
            "home": str(target.home),
            "status": "pending",
            "refresh_count": 0,
        }
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
            agent = build_registered_account_agent(provider=target.provider, account=target.account, home=target.home)
            account_status = agent.account_status(refresh_usage=True)
        except Exception as exc:
            target_state.update(
                {
                    "status": "error",
                    "last_refresh_at_monotonic": now,
                    "last_refresh_tick": tick,
                    "refresh_count": _refresh_count(target_state) + 1,
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
                "refresh_count": _refresh_count(target_state) + 1,
                "account_status": account_status.summary(),
                "error": None,
            }
        )

    def _write_frame_block(self, frame: MonitorFrame, *, workflow_state: dict[str, object]) -> None:
        lines = [f"refresh_interval_sec: {_format_seconds(self.config.refresh_interval_sec)}"]
        target_summaries: list[dict[str, object]] = []
        target_states = self._target_states(workflow_state)
        for target in self.config.targets:
            target_key = _target_key(target)
            raw_target_state = target_states.get(target_key)
            target_state = raw_target_state if isinstance(raw_target_state, dict) else {}
            target_summaries.append(dict(target_state))
            lines.extend(_target_lines(target=target, target_state=target_state))
        data = {
            "refresh_interval_sec": self.config.refresh_interval_sec,
            "run_count": workflow_state.get("run_count"),
            "targets": target_summaries,
        }
        if self._frame_block_index is None:
            self._frame_block_index = len(frame.blocks)
            frame.add_block(self.name, lines, data=data)
            return
        frame.replace_block(self._frame_block_index, title=self.name, lines=lines, data=data)


def build_monitor_workflows(configs: tuple[MonitorWorkflowConfig, ...]) -> tuple[MonitorWorkflow, ...]:
    workflows: list[MonitorWorkflow] = []
    for config in configs:
        if config.name == "limits-tracking":
            workflows.append(LimitsTrackingWorkflow(config))
            continue
        raise CliError(f"unknown monitor workflow {config.name!r}")
    return tuple(workflows)


def _target_key(target: MonitorTarget) -> str:
    return f"{target.provider}/{target.account}@{target.home}"


def _refresh_count(target_state: dict[str, object]) -> int:
    count = target_state.get("refresh_count", 0)
    if isinstance(count, int):
        return count
    return 0


def _target_lines(*, target: MonitorTarget, target_state: dict[str, object]) -> list[str]:
    lines = [
        f"{target.provider}/{target.account}",
        f"  home: {target.home}",
        f"  status: {target_state.get('status', 'pending')}",
    ]
    if target_state.get("status") == "error":
        lines.append(f"  error: {_error_message(target_state)}")
        return lines
    account_status = target_state.get("account_status")
    if isinstance(account_status, dict):
        lines.append(f"  check: {account_status.get('check_status', 'unknown')}")
        lines.append(f"  usage: {account_status.get('usage_status', 'unknown')}")
        lines.append(f"  limits: {_limits_summary(account_status)}")
    return lines


def _error_message(target_state: dict[str, object]) -> str:
    error = target_state.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str) and message:
            return message
    return "unknown error"


def _limits_summary(account_status: dict[str, Any]) -> str:
    usage_summary = account_status.get("usage_summary")
    if isinstance(usage_summary, str) and usage_summary:
        return usage_summary
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


def _format_seconds(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return str(value)
