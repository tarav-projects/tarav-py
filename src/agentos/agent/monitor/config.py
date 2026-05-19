from __future__ import annotations

from pathlib import Path

from agentos._core.errors import CliError
from agentos._core.path_validation import validate_string_for_path
from agentos._core.project import agentos_home_dir
from agentos.agent.account_registry import load_account
from agentos.agent.config import AgentConfigSource, agent_config_entries_from_config, load_chat_config_documents
from agentos.agent.monitor.loop import MonitorLoop
from agentos.agent.monitor.models import (
    AUTO_PRIME_ZERO_LIMITS_WORKFLOW,
    LIMITS_TRACKING_WORKFLOW,
    MonitorTarget,
    MonitorWorkflowConfig,
)
from agentos.agent.monitor.workflows import build_monitor_workflows

AUTO_PRIME_ZERO_LIMITS_DEFAULT_TARGET_LIMITS = {
    "codex": ("burst",),
    "claude-code": ("burst",),
}
AUTO_PRIME_ZERO_LIMITS_SUPPORTED_TARGET_LIMITS = {
    "codex": ("burst", "weekly"),
    "claude-code": ("burst", "weekly"),
}

MONITOR_CONFIG_SOURCE = AgentConfigSource(
    object_path=("agent", "accounts", "monitor"),
    field_prefix="agent.accounts.monitor",
)


def load_monitor_workflow_configs(*, start_path: Path | str = ".") -> tuple[MonitorWorkflowConfig, ...]:
    configs: list[MonitorWorkflowConfig] = []
    for config_document in load_chat_config_documents(start_path=start_path):
        for entry in agent_config_entries_from_config(config_document, source=MONITOR_CONFIG_SOURCE):
            raw_config = entry.raw_instance
            workflow_name = _required_string(raw_config, "workflow", field_name=entry.field_name("workflow"))
            if workflow_name not in {
                LIMITS_TRACKING_WORKFLOW,
                AUTO_PRIME_ZERO_LIMITS_WORKFLOW,
            }:
                raise CliError(f"unknown monitor workflow {workflow_name!r} at {entry.field_name('workflow')}")
            targets = _load_targets(raw_config, field_name=entry.field_name("targets"))
            if workflow_name == AUTO_PRIME_ZERO_LIMITS_WORKFLOW:
                _validate_auto_prime_target_providers(
                    targets,
                    field_name=entry.field_name("targets"),
                )
            configs.append(
                MonitorWorkflowConfig(
                    name=workflow_name,
                    targets=targets,
                    refresh_interval_sec=_positive_number_config(
                        raw_config,
                        key=_workflow_interval_key(workflow_name),
                        field_name=entry.field_name(_workflow_interval_key(workflow_name)),
                    ),
                    target_limit_ids=_target_limit_ids(
                        raw_config,
                        field_name=entry.field_name("target_limits"),
                    )
                    if workflow_name == AUTO_PRIME_ZERO_LIMITS_WORKFLOW
                    else {},
                    retry_cooldown_sec=_positive_number_config(
                        raw_config,
                        key="retry_cooldown_sec",
                        field_name=entry.field_name("retry_cooldown_sec"),
                        default=600,
                    )
                    if workflow_name == AUTO_PRIME_ZERO_LIMITS_WORKFLOW
                    else None,
                    raw_config=dict(raw_config),
                )
            )
    return tuple(configs)


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


def _workflow_interval_key(workflow_name: str) -> str:
    if workflow_name == AUTO_PRIME_ZERO_LIMITS_WORKFLOW:
        return "interval_sec"
    return "refresh_interval_sec"


def _positive_number_config(
    raw_config: dict[str, object], *, key: str, field_name: str, default: float = 60
) -> float:
    value = raw_config.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise CliError(f"{field_name} must be a positive number")
    if value <= 0:
        raise CliError(f"{field_name} must be a positive number")
    return float(value)


def _target_limit_ids(
    raw_config: dict[str, object], *, field_name: str
) -> dict[str, tuple[str, ...]]:
    raw_target_limits = raw_config.get("target_limits")
    if raw_target_limits is None:
        return dict(AUTO_PRIME_ZERO_LIMITS_DEFAULT_TARGET_LIMITS)
    if not isinstance(raw_target_limits, dict):
        raise CliError(f"{field_name} must be a JSON object")
    target_limits: dict[str, tuple[str, ...]] = {}
    for provider, raw_limit_ids in raw_target_limits.items():
        provider_field = f"{field_name}.{provider}"
        if not isinstance(provider, str) or not provider:
            raise CliError(f"{field_name} keys must be non-empty provider names")
        supported = AUTO_PRIME_ZERO_LIMITS_SUPPORTED_TARGET_LIMITS.get(provider)
        if supported is None:
            raise CliError(f"{provider_field} is not supported by auto-prime-zero-limits")
        if not isinstance(raw_limit_ids, list) or not raw_limit_ids:
            raise CliError(f"{provider_field} must be a non-empty JSON array")
        limit_ids: list[str] = []
        for index, raw_limit_id in enumerate(raw_limit_ids):
            limit_field = f"{provider_field}[{index}]"
            if not isinstance(raw_limit_id, str) or not raw_limit_id:
                raise CliError(f"{limit_field} must be a non-empty string")
            limit_id = validate_string_for_path(raw_limit_id, field_name=limit_field)
            if limit_id not in supported:
                raise CliError(
                    f"{limit_field} is not supported by auto-prime-zero-limits"
                )
            limit_ids.append(limit_id)
        target_limits[provider] = tuple(dict.fromkeys(limit_ids))
    return target_limits


def _validate_auto_prime_target_providers(
    targets: tuple[MonitorTarget, ...], *, field_name: str
) -> None:
    for index, target in enumerate(targets):
        if target.provider in AUTO_PRIME_ZERO_LIMITS_SUPPORTED_TARGET_LIMITS:
            continue
        raise CliError(
            f"{field_name}[{index}].provider is not supported by auto-prime-zero-limits"
        )
