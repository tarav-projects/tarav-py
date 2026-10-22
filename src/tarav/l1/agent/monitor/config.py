from __future__ import annotations

import datetime
import hashlib
import json
from pathlib import Path

from tarav.l0._core.errors import CliError
from tarav.l0._core.path_validation import validate_string_for_path
from tarav.l0._core.home import tarav_home_dir
from tarav.l1.agent import auth_registry
from tarav.l1.agent.config import (
    AgentConfigSource,
    agent_config_entries_from_config,
    load_chat_config_documents,
    load_agent_profile,
)
from tarav.l1.agent.profile_scope import (
    allowed_account_ids,
    allowed_home_paths,
    format_allowed_values,
)
from tarav.l1.agent.monitor.loop import MonitorLoop
from tarav.l1.agent.monitor.models import (
    ACCOUNT_ROTATION_WORKFLOW,
    AUTO_PRIME_DEFAULT_INTERVAL_SEC,
    AUTO_PRIME_DEFAULT_THRESHOLD_PERCENT,
    AUTO_PRIME_ZERO_LIMITS_WORKFLOW,
    LIMITS_TRACKING_WORKFLOW,
    MonitorTarget,
    MonitorWorkflowConfig,
)
from tarav.l1.agent.monitor.workflows import build_monitor_workflows

# tarav.breadcrumb 59253674199c
AUTO_PRIME_SUPPORTED_PROVIDERS = ("codex", "claude-code")

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
                ACCOUNT_ROTATION_WORKFLOW,
            }:
                raise CliError(
                    f"unknown monitor workflow {workflow_name!r} at {entry.field_name('workflow')}"
                )
            if workflow_name == ACCOUNT_ROTATION_WORKFLOW:
                configs.append(
                    _account_rotation_config(
                        raw_config,
                        entry=entry,
                        start_path=resolved_start_path,
                        loaded_at=loaded_at,
                        fingerprint=fingerprint,
                    )
                )
                continue
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
                        default=AUTO_PRIME_DEFAULT_INTERVAL_SEC
                        if workflow_name == AUTO_PRIME_ZERO_LIMITS_WORKFLOW
                        else 60,
                    ),
                    threshold_percent=_positive_number_config(
                        raw_config,
                        key="threshold_percent",
                        field_name=entry.field_name("threshold_percent"),
                        default=AUTO_PRIME_DEFAULT_THRESHOLD_PERCENT,
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


    return MonitorLoop(
        workflows=build_monitor_workflows(configs),
        interval_sec=interval_sec,
        max_ticks=max_ticks,
        config_fingerprint=(
            configs[0].config_fingerprint
            if configs
            else monitor_config_fingerprint(start_path=start_path)
        ),
        config_fingerprint_loader=lambda: monitor_config_fingerprint(
            start_path=start_path
        ),
    )


def _account_rotation_config(
    raw_config: dict[str, object],
    *,
    entry,
    start_path: Path,
    loaded_at: str,
    fingerprint: str,
) -> MonitorWorkflowConfig:
    """Decode an `account-rotation` entry.

    The workflow sweeps every provider with an auth method rather than a declared
    target list, so this entry carries no `targets` and never reaches
    `_load_targets`, which requires a non-empty array."""

    return MonitorWorkflowConfig(
        name=ACCOUNT_ROTATION_WORKFLOW,
        targets=(),
        refresh_interval_sec=_positive_number_config(
            raw_config,
            key="refresh_interval_sec",
            field_name=entry.field_name("refresh_interval_sec"),
        ),
        auto_materialize=_bool_config(
            raw_config,
            key="auto_materialize",
            field_name=entry.field_name("auto_materialize"),
            default=True,
        ),
        raw_config=dict(raw_config),
        start_path=start_path,
        loaded_at=loaded_at,
        config_fingerprint=fingerprint,
    )


def _bool_config(
    raw_config: dict[str, object], *, key: str, field_name: str, default: bool
) -> bool:
    value = raw_config.get(key, default)
    if not isinstance(value, bool):
        raise CliError(f"{field_name} must be true or false")
    return value


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
        raw_account = raw_target.get("account")
        if not isinstance(raw_account, str) or not raw_account.strip():
            raise CliError(f"{target_field}.account must be a non-empty string")


        account = validate_string_for_path(
            raw_account.split("/", 1)[0], field_name=f"{target_field}.account"
        )
        if not auth_registry.account_exists(provider, account):
            raise CliError(
                f"{target_field}.account references unknown account: {provider}/{account}"
            )
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
        return tarav_home_dir() / "agent" / "homes" / provider / account
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


def _validate_auto_prime_target_providers(
    targets: tuple[MonitorTarget, ...], *, field_name: str
) -> None:
    for index, target in enumerate(targets):
        if target.provider in AUTO_PRIME_SUPPORTED_PROVIDERS:
            continue
        raise CliError(
            f"{field_name}[{index}].provider is not supported by auto-prime-zero-limits"
        )
