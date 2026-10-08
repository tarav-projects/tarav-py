# $kw: --from Account.Management
"""Assembly of configured monitor workflows, including multi-config merging."""

from __future__ import annotations

from tarav.l0._core.errors import CliError
from tarav.l1.agent.monitor.loop import MonitorWorkflow
from tarav.l1.agent.monitor.models import (
    ACCOUNT_ROTATION_WORKFLOW,
    AUTO_PRIME_ZERO_LIMITS_WORKFLOW,
    LIMITS_TRACKING_WORKFLOW,
    MonitorTarget,
    MonitorWorkflowConfig,
)
from tarav.l1.agent.monitor.workflows.account_rotation import AccountRotationWorkflow
from tarav.l1.agent.monitor.workflows.auto_prime import AutoPrimeZeroLimitsWorkflow
from tarav.l1.agent.monitor.workflows.limits_tracking import LimitsTrackingWorkflow


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
        if config.name == ACCOUNT_ROTATION_WORKFLOW:
            continue
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


    workflows.append(_build_account_rotation_workflow(configs))
    return tuple(workflows)


def _build_account_rotation_workflow(
    configs: tuple[MonitorWorkflowConfig, ...],
) -> AccountRotationWorkflow:
    """Always build the rotation workflow; configure it only when an entry exists.

    Absent config means auto-materialize, so the workflow runs with no entry at
    all. Several entries carry only a boolean and an interval between them, so the
    first wins rather than earning a merge rule."""

    for config in configs:
        if config.name != ACCOUNT_ROTATION_WORKFLOW:
            continue
        return AccountRotationWorkflow(
            auto_materialize=(
                True if config.auto_materialize is None else config.auto_materialize
            ),
            refresh_interval_sec=config.refresh_interval_sec,
        )
    return AccountRotationWorkflow()


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
    """Union the targets; the shortest interval and highest threshold win."""

    if len(configs) == 1:
        return configs[0]
    targets: list[MonitorTarget] = []
    target_keys: set[tuple[str, str, str]] = set()
    raw_configs: list[dict[str, object]] = []
    interval_sec = min(config.refresh_interval_sec for config in configs)
    threshold_percent = max(
        config.threshold_percent
        for config in configs
        if config.threshold_percent is not None
    )
    for config in configs:
        for target in config.targets:
            target_key = (target.provider, target.account, str(target.home))
            if target_key in target_keys:
                continue
            target_keys.add(target_key)
            targets.append(target)
        raw_configs.append(config.raw_config)
    return MonitorWorkflowConfig(
        name=AUTO_PRIME_ZERO_LIMITS_WORKFLOW,
        targets=tuple(targets),
        refresh_interval_sec=interval_sec,
        start_path=configs[0].start_path,
        threshold_percent=threshold_percent,
        loaded_at=configs[0].loaded_at,
        config_fingerprint=configs[0].config_fingerprint,
        raw_config={
            "workflow": AUTO_PRIME_ZERO_LIMITS_WORKFLOW,
            "interval_sec": interval_sec,
            "threshold_percent": threshold_percent,
            "configs": raw_configs,
        },
    )
