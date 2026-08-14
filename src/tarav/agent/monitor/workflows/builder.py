# $kw: --from Account.Management
"""Assembly of configured monitor workflows, including multi-config merging."""

from __future__ import annotations

from tarav._core.errors import CliError
from tarav.agent.monitor.loop import MonitorWorkflow
from tarav.agent.monitor.models import (
    AUTO_PRIME_ZERO_LIMITS_WORKFLOW,
    LIMITS_TRACKING_WORKFLOW,
    MonitorTarget,
    MonitorWorkflowConfig,
)
from tarav.agent.monitor.workflows.account_rotation import AccountRotationWorkflow
from tarav.agent.monitor.workflows.auto_prime import AutoPrimeZeroLimitsWorkflow
from tarav.agent.monitor.workflows.limits_tracking import LimitsTrackingWorkflow


def build_monitor_workflows(
    configs: tuple[MonitorWorkflowConfig, ...],
) -> tuple[MonitorWorkflow, ...]:
    workflows: list[MonitorWorkflow] = []
    limits_tracking_configs = tuple(
        config for config in configs if config.name == LIMITS_TRACKING_WORKFLOW
    )
    auto_prime_configs = tuple(
        config for config in configs if config.name == AUTO_PRIME_ZERO_LIMITS_WORKFLOW
    )
    for config in configs:
        if config.name == LIMITS_TRACKING_WORKFLOW:
            if not any(
                workflow.name == LIMITS_TRACKING_WORKFLOW for workflow in workflows
            ):
                workflows.append(
                    LimitsTrackingWorkflow(
                        _merge_limits_tracking_configs(limits_tracking_configs)
                    )
                )
            continue
        if config.name == AUTO_PRIME_ZERO_LIMITS_WORKFLOW:
            if not any(
                workflow.name == AUTO_PRIME_ZERO_LIMITS_WORKFLOW
                for workflow in workflows
            ):
                workflows.append(
                    AutoPrimeZeroLimitsWorkflow(
                        _merge_auto_prime_configs(auto_prime_configs)
                    )
                )
            continue
        raise CliError(f"unknown monitor workflow {config.name!r}")


    workflows.append(AccountRotationWorkflow())
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
        name=LIMITS_TRACKING_WORKFLOW,
        targets=tuple(targets),
        refresh_interval_sec=refresh_interval_sec,
        start_path=configs[0].start_path,
        loaded_at=configs[0].loaded_at,
        config_fingerprint=configs[0].config_fingerprint,
        raw_config={
            "workflow": LIMITS_TRACKING_WORKFLOW,
            "refresh_interval_sec": refresh_interval_sec,
            "configs": raw_configs,
        },
    )


def _merge_auto_prime_configs(
    configs: tuple[MonitorWorkflowConfig, ...],
) -> MonitorWorkflowConfig:
    if len(configs) == 1:
        return configs[0]
    targets: list[MonitorTarget] = []
    target_keys: set[tuple[str, str, str]] = set()
    target_limit_ids: dict[str, tuple[str, ...]] = {}
    triggers: dict[str, tuple[str, ...]] = {}
    raw_configs: list[dict[str, object]] = []
    interval_sec = min(config.refresh_interval_sec for config in configs)
    retry_cooldown_sec = min(
        config.retry_cooldown_sec
        for config in configs
        if config.retry_cooldown_sec is not None
    )
    for config in configs:
        for target in config.targets:
            target_key = (target.provider, target.account, str(target.home))
            if target_key in target_keys:
                continue
            target_keys.add(target_key)
            targets.append(target)
        for provider, limit_ids in config.target_limit_ids.items():
            existing = target_limit_ids.get(provider, ())
            target_limit_ids[provider] = tuple(dict.fromkeys((*existing, *limit_ids)))
        for provider, trigger_names in config.triggers.items():
            existing = triggers.get(provider, ())
            triggers[provider] = tuple(dict.fromkeys((*existing, *trigger_names)))
        raw_configs.append(config.raw_config)
    return MonitorWorkflowConfig(
        name=AUTO_PRIME_ZERO_LIMITS_WORKFLOW,
        targets=tuple(targets),
        refresh_interval_sec=interval_sec,
        start_path=configs[0].start_path,
        retry_cooldown_sec=retry_cooldown_sec,
        target_limit_ids=target_limit_ids,
        triggers=triggers,
        loaded_at=configs[0].loaded_at,
        config_fingerprint=configs[0].config_fingerprint,
        raw_config={
            "workflow": AUTO_PRIME_ZERO_LIMITS_WORKFLOW,
            "interval_sec": interval_sec,
            "retry_cooldown_sec": retry_cooldown_sec,
            "target_limits": target_limit_ids,
            "triggers": triggers,
            "configs": raw_configs,
        },
    )
