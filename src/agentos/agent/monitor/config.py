from __future__ import annotations

import datetime
import hashlib
import json
from pathlib import Path

from agentos._core.errors import CliError
from agentos._core.path_validation import validate_string_for_path
from agentos._core.project import agentos_home_dir
from agentos.agent.account_registry import load_account
from agentos.agent.config import (
    AgentConfigSource,
    agent_config_entries_from_config,
    load_chat_config_documents,
    load_agent_profile,
)
from agentos.agent.profile_scope import (
    allowed_account_ids,
    allowed_home_paths,
    format_allowed_values,
)
from agentos.agent.monitor.loop import MonitorLoop
from agentos.agent.monitor.models import (
    AUTO_PRIME_SUPPORTED_TRIGGERS,
    AUTO_PRIME_TRIGGER_NEAR_ZERO_FULL_WINDOW,
    AUTO_PRIME_TRIGGER_PERIOD_KEY_CHURN,
    AUTO_PRIME_TRIGGER_SLIDING_RESET,
    AUTO_PRIME_TRIGGER_ZERO_USAGE,
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
AUTO_PRIME_ZERO_LIMITS_DEFAULT_TRIGGERS = {
    "codex": (
        AUTO_PRIME_TRIGGER_ZERO_USAGE,
        AUTO_PRIME_TRIGGER_NEAR_ZERO_FULL_WINDOW,
        AUTO_PRIME_TRIGGER_SLIDING_RESET,
        AUTO_PRIME_TRIGGER_PERIOD_KEY_CHURN,
    ),
    "claude-code": (AUTO_PRIME_TRIGGER_ZERO_USAGE,),
}

MONITOR_CONFIG_SOURCE = AgentConfigSource(
    object_path=("agent", "accounts", "monitor"),
    field_prefix="agent.accounts.monitor",
)


def load_monitor_workflow_configs(
    *, start_path: Path | str = "."
) -> tuple[MonitorWorkflowConfig, ...]:
    configs: list[MonitorWorkflowConfig] = []
    resolved_start_path = Path(start_path).expanduser().resolve()
    loaded_at = datetime.datetime.now(tz=datetime.UTC).isoformat()
    config_documents = load_chat_config_documents(start_path=resolved_start_path)
    fingerprint = _config_documents_fingerprint(config_documents)
    for config_document in config_documents:
        for entry in agent_config_entries_from_config(
            config_document, source=MONITOR_CONFIG_SOURCE
        ):
            raw_config = entry.raw_profile
            workflow_name = _required_string(
                raw_config, "workflow", field_name=entry.field_name("workflow")
            )
            if workflow_name not in {
                LIMITS_TRACKING_WORKFLOW,
                AUTO_PRIME_ZERO_LIMITS_WORKFLOW,
            }:
                raise CliError(
                    f"unknown monitor workflow {workflow_name!r} at {entry.field_name('workflow')}"
                )
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
                        field_name=entry.field_name(
                            _workflow_interval_key(workflow_name)
                        ),
                    ),
                    target_limit_ids=_target_limit_ids(
                        raw_config,
                        field_name=entry.field_name("target_limits"),
                    )
                    if workflow_name == AUTO_PRIME_ZERO_LIMITS_WORKFLOW
                    else {},
                    triggers=_auto_prime_triggers(
                        raw_config,
                        field_name=entry.field_name("triggers"),
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
                    start_path=resolved_start_path,
                    loaded_at=loaded_at,
                    config_fingerprint=fingerprint,
                )
            )
    return tuple(configs)


def monitor_config_fingerprint(*, start_path: Path | str = ".") -> str:
    documents = load_chat_config_documents(start_path=start_path)
    return _config_documents_fingerprint(documents)


def _config_documents_fingerprint(documents: tuple[dict[str, object], ...]) -> str:
    payload = json.dumps(documents, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


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
        config_fingerprint=configs[0].config_fingerprint,
        config_fingerprint_loader=lambda: monitor_config_fingerprint(
            start_path=start_path
        ),
    )


def _load_targets(
    raw_config: dict[str, object], *, field_name: str
) -> tuple[MonitorTarget, ...]:
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
        provider = _required_string(
            raw_target, "provider", field_name=f"{target_field}.provider"
        )
        account = _required_string(
            raw_target, "account", field_name=f"{target_field}.account"
        )
        load_account(provider, account)
        profile = _optional_string(
            raw_target, "profile", field_name=f"{target_field}.profile"
        )
        home = _target_home(
            raw_target,
            provider=provider,
            account=account,
            profile=profile,
            field_name=f"{target_field}.home",
        )
        if profile is not None:
            _validate_profile_target(
                profile=profile,
                provider=provider,
                account=account,
                home=home,
                field_name=target_field,
            )
        targets.append(
            MonitorTarget(
                provider=provider,
                account=account,
                home=home,
                profile=profile,
            )
        )
    return tuple(targets)


def _target_home(
    raw_target: dict[str, object],
    *,
    provider: str,
    account: str,
    profile: str | None,
    field_name: str,
) -> Path:
    raw_home = raw_target.get("home")
    if profile is not None and raw_home is None:
        raise CliError(f"{field_name} is required when profile is set")
    if raw_home is None:
        return agentos_home_dir() / "agent" / "homes" / provider / account
    if not isinstance(raw_home, str) or not raw_home.strip():
        raise CliError(f"{field_name} must be a non-empty string")
    return Path(raw_home).expanduser().resolve()


def _validate_profile_target(
    *,
    profile: str,
    provider: str,
    account: str,
    home: Path,
    field_name: str,
) -> None:
    config = load_agent_profile(profile)
    if config.provider != provider:
        raise CliError(
            f"{field_name}.profile uses provider {config.provider}, not {provider}"
        )
    allowed_accounts = set(allowed_account_ids(config.accounts))
    if allowed_accounts and account not in allowed_accounts:
        raise CliError(
            f"{field_name}.account must be allowed by profile {profile}; "
            f"allowed accounts: {format_allowed_values(allowed_accounts)}"
        )
    allowed_homes = set(allowed_home_paths(config.homes))
    if str(home) not in allowed_homes:
        raise CliError(
            f"{field_name}.home must be allowed by profile {profile}; "
            f"allowed homes: {format_allowed_values(allowed_homes)}"
        )


def _required_string(payload: dict[str, object], key: str, *, field_name: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise CliError(f"{field_name} must be a non-empty string")
    return validate_string_for_path(value, field_name=field_name)


def _optional_string(
    payload: dict[str, object], key: str, *, field_name: str
) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
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
    target_limits: dict[str, tuple[str, ...]] = dict(
        AUTO_PRIME_ZERO_LIMITS_DEFAULT_TARGET_LIMITS
    )
    for provider, raw_limit_ids in raw_target_limits.items():
        provider_field = f"{field_name}.{provider}"
        if not isinstance(provider, str) or not provider:
            raise CliError(f"{field_name} keys must be non-empty provider names")
        supported = AUTO_PRIME_ZERO_LIMITS_SUPPORTED_TARGET_LIMITS.get(provider)
        if supported is None:
            raise CliError(
                f"{provider_field} is not supported by auto-prime-zero-limits"
            )
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


def _auto_prime_triggers(
    raw_config: dict[str, object], *, field_name: str
) -> dict[str, tuple[str, ...]]:
    raw_triggers = raw_config.get("triggers")
    if raw_triggers is None:
        return dict(AUTO_PRIME_ZERO_LIMITS_DEFAULT_TRIGGERS)
    if not isinstance(raw_triggers, dict):
        raise CliError(f"{field_name} must be a JSON object")
    triggers: dict[str, tuple[str, ...]] = dict(AUTO_PRIME_ZERO_LIMITS_DEFAULT_TRIGGERS)
    for provider, raw_trigger_names in raw_triggers.items():
        provider_field = f"{field_name}.{provider}"
        if not isinstance(provider, str) or not provider:
            raise CliError(f"{field_name} keys must be non-empty provider names")
        if provider not in AUTO_PRIME_ZERO_LIMITS_SUPPORTED_TARGET_LIMITS:
            raise CliError(
                f"{provider_field} is not supported by auto-prime-zero-limits"
            )
        if not isinstance(raw_trigger_names, list) or not raw_trigger_names:
            raise CliError(f"{provider_field} must be a non-empty JSON array")
        trigger_names: list[str] = []
        for index, raw_trigger_name in enumerate(raw_trigger_names):
            trigger_field = f"{provider_field}[{index}]"
            if not isinstance(raw_trigger_name, str) or not raw_trigger_name:
                raise CliError(f"{trigger_field} must be a non-empty string")
            trigger_name = validate_string_for_path(
                raw_trigger_name,
                field_name=trigger_field,
            )
            if trigger_name not in AUTO_PRIME_SUPPORTED_TRIGGERS:
                raise CliError(
                    f"{trigger_field} is not supported by auto-prime-zero-limits"
                )
            trigger_names.append(trigger_name)
        triggers[provider] = tuple(dict.fromkeys(trigger_names))
    return triggers


def _validate_auto_prime_target_providers(
    targets: tuple[MonitorTarget, ...], *, field_name: str
) -> None:
    for index, target in enumerate(targets):
        if target.provider in AUTO_PRIME_ZERO_LIMITS_SUPPORTED_TARGET_LIMITS:
            continue
        raise CliError(
            f"{field_name}[{index}].provider is not supported by auto-prime-zero-limits"
        )
