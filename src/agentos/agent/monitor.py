from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from agentos._core.errors import CliError
from agentos._core.path_validation import validate_string_for_path
from agentos._core.project import agentos_home_dir
from agentos.agent.account_registry import load_account
from agentos.agent.config import AgentConfigSource, agent_config_entries_from_config, load_chat_config_documents


MONITOR_CONFIG_SOURCE = AgentConfigSource(
    object_path=("agent", "accounts", "monitor"),
    field_prefix="agent.accounts.monitor",
)


@dataclass(frozen=True)
class MonitorTarget:
    provider: str
    account: str
    home: Path

    def summary(self) -> dict[str, str]:
        return {
            "provider": self.provider,
            "account": self.account,
            "home": str(self.home),
        }


@dataclass(frozen=True)
class MonitorWorkflowConfig:
    name: str
    targets: tuple[MonitorTarget, ...]
    raw_config: dict[str, object]


@dataclass
class MonitorState:
    tick: int = 0
    workflow_run_counts: dict[str, int] = field(default_factory=dict)
    data: dict[str, object] = field(default_factory=dict)


@dataclass
class MonitorFrame:
    tick: int = 0
    blocks: list[dict[str, object]] = field(default_factory=list)
    status_lines: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def add_block(self, title: str, lines: list[str], data: dict[str, object] | None = None) -> None:
        block: dict[str, object] = {
            "title": title,
            "lines": lines,
        }
        if data is not None:
            block["data"] = data
        self.blocks.append(block)

    def add_error(self, message: str) -> None:
        self.errors.append(message)

    def replace_block(
        self,
        index: int,
        *,
        title: str,
        lines: list[str],
        data: dict[str, object] | None = None,
    ) -> None:
        block: dict[str, object] = {
            "title": title,
            "lines": lines,
        }
        if data is not None:
            block["data"] = data
        self.blocks[index] = block


class MonitorWorkflow(Protocol):
    name: str

    def run(self, state: MonitorState, frame: MonitorFrame) -> None:
        ...


class LimitsTrackingWorkflow:
    name = "limits-tracking"

    def __init__(self, config: MonitorWorkflowConfig) -> None:
        self.config = config
        self._frame_block_index: int | None = None

    def run(self, state: MonitorState, frame: MonitorFrame) -> None:
        run_count = state.workflow_run_counts.get(self.name, 0) + 1
        state.workflow_run_counts[self.name] = run_count
        state.data[self.name] = {
            "status": "under construction",
            "last_tick": frame.tick,
            "run_count": run_count,
            "target_count": len(self.config.targets),
        }
        self._write_frame_block(
            frame,
            run_count=run_count,
        )

    def _write_frame_block(self, frame: MonitorFrame, *, run_count: int) -> None:
        lines = [
            "status: under construction",
            f"tick: {frame.tick}",
            f"targets: {len(self.config.targets)}",
        ]
        data = {
            "status": "under construction",
            "run_count": run_count,
            "targets": [target.summary() for target in self.config.targets],
        }
        if self._frame_block_index is None:
            self._frame_block_index = len(frame.blocks)
            frame.add_block(self.name, lines, data=data)
            return
        frame.replace_block(self._frame_block_index, title=self.name, lines=lines, data=data)


class MonitorLoop:
    def __init__(
        self,
        *,
        workflows: tuple[MonitorWorkflow, ...],
        interval_sec: float,
        max_ticks: int | None,
    ) -> None:
        if max_ticks is not None and max_ticks < 1:
            raise CliError("--max-ticks must be greater than 0")
        if interval_sec < 0:
            raise CliError("--interval-sec must be greater than or equal to 0")
        self.workflows = workflows
        self.interval_sec = interval_sec
        self.max_ticks = max_ticks
        self.state = MonitorState()
        self.frame = MonitorFrame()

    def run(
        self,
        *,
        on_tick: Callable[[MonitorFrame, MonitorState], None] | None = None,
    ) -> tuple[MonitorFrame, MonitorState]:
        ticks_run = 0
        while self.max_ticks is None or ticks_run < self.max_ticks:
            started_at = time.monotonic()
            self.state.tick += 1
            self.frame.tick = self.state.tick
            self.frame.status_lines = [f"tick: {self.state.tick}"]

            for workflow in self.workflows:
                try:
                    workflow.run(self.state, self.frame)
                except Exception as exc:
                    self._record_unexpected_workflow_error(workflow=workflow, error=exc)

            if on_tick is not None:
                on_tick(self.frame, self.state)

            ticks_run += 1
            if self.max_ticks is None or ticks_run < self.max_ticks:
                elapsed = time.monotonic() - started_at
                sleep_for = max(0.0, self.interval_sec - elapsed)
                if sleep_for:
                    time.sleep(sleep_for)
        return self.frame, self.state

    def _record_unexpected_workflow_error(self, *, workflow: MonitorWorkflow, error: Exception) -> None:
        message = f"unexpected workflow error: {workflow.name}: {type(error).__name__}: {error}"
        self.frame.add_error(message)
        workflow_errors = self.state.data.setdefault("workflow_errors", [])
        if isinstance(workflow_errors, list):
            workflow_errors.append(
                {
                    "tick": self.frame.tick,
                    "workflow": workflow.name,
                    "error_type": type(error).__name__,
                    "message": str(error),
                }
            )


def load_monitor_workflow_configs(*, start_path: Path | str = ".") -> tuple[MonitorWorkflowConfig, ...]:
    configs: list[MonitorWorkflowConfig] = []
    for config_document in load_chat_config_documents(start_path=start_path):
        for entry in agent_config_entries_from_config(config_document, source=MONITOR_CONFIG_SOURCE):
            raw_config = entry.raw_instance
            workflow_name = _required_string(raw_config, "workflow", field_name=entry.field_name("workflow"))
            if workflow_name != "limits-tracking":
                raise CliError(f"unknown monitor workflow {workflow_name!r} at {entry.field_name('workflow')}")
            targets = _load_targets(raw_config, field_name=entry.field_name("targets"))
            configs.append(
                MonitorWorkflowConfig(
                    name=workflow_name,
                    targets=targets,
                    raw_config=dict(raw_config),
                )
            )
    return tuple(configs)


def build_monitor_workflows(configs: tuple[MonitorWorkflowConfig, ...]) -> tuple[MonitorWorkflow, ...]:
    workflows: list[MonitorWorkflow] = []
    for config in configs:
        if config.name == "limits-tracking":
            workflows.append(LimitsTrackingWorkflow(config))
            continue
        raise CliError(f"unknown monitor workflow {config.name!r}")
    return tuple(workflows)


def build_monitor_loop(
    *,
    start_path: Path | str = ".",
    interval_sec: float,
    max_ticks: int | None,
) -> MonitorLoop:
    configs = load_monitor_workflow_configs(start_path=start_path)
    if not configs:
        raise CliError("agent.accounts.monitor must configure at least one workflow")
    return MonitorLoop(
        workflows=build_monitor_workflows(configs),
        interval_sec=interval_sec,
        max_ticks=max_ticks,
    )


def monitor_result_payload(frame: MonitorFrame, state: MonitorState) -> dict[str, object]:
    return {
        "status": "ok",
        "command": "agent accounts monitor",
        "tick": frame.tick,
        "workflow_run_counts": state.workflow_run_counts,
        "state": state.data,
        "frame": {
            "tick": frame.tick,
            "blocks": frame.blocks,
            "status_lines": frame.status_lines,
            "warnings": frame.warnings,
            "errors": frame.errors,
        },
    }


def format_monitor_frame(frame: MonitorFrame) -> str:
    lines = ["Agent accounts monitor", f"Tick: {frame.tick}"]
    if frame.status_lines:
        lines.extend(f"Status: {line}" for line in frame.status_lines)
    if frame.errors:
        lines.extend(["", "Errors"])
        lines.extend(f"  {error}" for error in frame.errors)
    for block in frame.blocks:
        title = block.get("title")
        if isinstance(title, str):
            lines.extend(["", title])
        block_lines = block.get("lines")
        if isinstance(block_lines, list):
            lines.extend(f"  {line}" for line in block_lines if isinstance(line, str))
    return "\n".join(lines)


def dumps_monitor_json(frame: MonitorFrame, state: MonitorState) -> str:
    return json.dumps(monitor_result_payload(frame, state), indent=2, sort_keys=True)


class RichMonitorRenderer:
    def __init__(self) -> None:
        from rich.console import Console
        from rich.live import Live

        self.console = Console()
        self.live = Live(
            "",
            console=self.console,
            refresh_per_second=4,
            transient=False,
        )

    def __enter__(self) -> RichMonitorRenderer:
        self.live.__enter__()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.live.__exit__(exc_type, exc, traceback)

    def render(self, frame: MonitorFrame, state: MonitorState) -> None:
        from rich.text import Text

        self.live.update(Text(format_monitor_frame(frame)))


def _load_targets(raw_config: dict[str, object], *, field_name: str) -> tuple[MonitorTarget, ...]:
    raw_targets = raw_config.get("targets")
    if not isinstance(raw_targets, list):
        raise CliError(f"{field_name} must be a JSON array")
    if not raw_targets:
        raise CliError(f"{field_name} must not be empty")
    targets: list[MonitorTarget] = []
    for index, raw_target in enumerate(raw_targets):
        target_field = f"{field_name}[{index}]"
        if not isinstance(raw_target, dict):
            raise CliError(f"{target_field} must be a JSON object")
        provider = _required_string(raw_target, "provider", field_name=f"{target_field}.provider")
        account = _required_string(raw_target, "account", field_name=f"{target_field}.account")
        load_account(provider, account)
        targets.append(
            MonitorTarget(
                provider=provider,
                account=account,
                home=_target_home(raw_target, provider=provider, account=account, field_name=f"{target_field}.home"),
            )
        )
    return tuple(targets)


def _target_home(raw_target: dict[str, object], *, provider: str, account: str, field_name: str) -> Path:
    raw_home = raw_target.get("home")
    if raw_home is None:
        return agentos_home_dir() / "agent" / "homes" / provider / account
    if not isinstance(raw_home, str) or not raw_home.strip():
        raise CliError(f"{field_name} must be a non-empty string")
    return Path(raw_home).expanduser().resolve()


def _required_string(payload: dict[str, object], key: str, *, field_name: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise CliError(f"{field_name} must be a non-empty string")
    return validate_string_for_path(value, field_name=field_name)
