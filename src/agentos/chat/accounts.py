from __future__ import annotations

import datetime
import json
import os
import pty
import re
import select
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from agentos._core.errors import CliError
from agentos._core.path_validation import validate_string_for_path
from agentos._core.project import (
    agentos_home_dir,
    find_agentos_project_root,
    global_config_path,
    load_global_config,
    load_project_config,
    project_config_path,
)
from agentos.tara_tapes.core import (
    append_tara_tape_stage_record,
    bootstrap_tara_tape,
    commit_tara_tape_stage,
)

DEFAULT_ACCOUNT_TIMEOUT_SEC = 15
_CLAUDE_USAGE_REFRESH_PROMPT = "Reply with OK."
_CLAUDE_USAGE_REFRESH_MODEL = "haiku"
CHAT_ACCOUNT_STATS_DIRNAME = "chat-account-stats"
CHAT_ACCOUNT_STATS_HISTORY_DIRNAME = "history"
CHAT_ACCOUNT_STATS_LATEST_FILENAME = "latest.json"
CHAT_ACCOUNT_STATS_TAPE_NAME = "chat-account-stats"
CHAT_ACCOUNT_STATS_TAPE_WRITER_ID = "agentos-chat-accounts-stats"
CHAT_ACCOUNT_STATS_RECORD_CLASS = "agentos.chat.account-stats.snapshot"
MAX_ACCOUNT_COLLECTION_WORKERS = 4
CLAUDE_REFRESH_WORKSPACE_DIRNAME = "claude-refresh-workspace"
CLAUDE_REFRESH_TRUST_CONFIRM_DELAY_SEC = 0.75
CLAUDE_REFRESH_TRUST_CONFIRM_RETRY_SEC = 0.75
CLAUDE_REFRESH_PROMPT_FALLBACK_DELAY_SEC = 2.5
CLAUDE_REFRESH_INTERRUPT_SETTLE_SEC = 0.05
CLAUDE_REFRESH_TERMINATE_WAIT_SEC = 0.5

_ANSI_CSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_ANSI_OSC_RE = re.compile(r"\x1b\].*?(?:\x07|\x1b\\)", re.DOTALL)
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


@dataclass(frozen=True)
class AccountProviderInstance:
    provider: str
    instance_id: str
    label: str
    cli_command: tuple[str, ...]
    env: tuple[tuple[str, str], ...]
    timeout_sec: int
    live_usage_refresh: bool

    def env_mapping(self) -> dict[str, str]:
        return dict(self.env)


@dataclass(frozen=True)
class AccountProviderFamily:
    family: str
    collect_stats: Callable[[AccountProviderInstance, bool], dict[str, Any]]


class AccountCommandError(Exception):
    def __init__(
        self,
        *,
        error_type: str,
        message: str,
        exit_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.error_type = error_type
        self.message = message
        self.exit_code = exit_code


def supported_account_provider_families() -> tuple[AccountProviderFamily, ...]:
    return (
        AccountProviderFamily(
            family="codex",
            collect_stats=_collect_codex_account_stats,
        ),
        AccountProviderFamily(
            family="claude-code",
            collect_stats=_collect_claude_code_account_stats,
        ),
    )


def configured_account_provider_instances(
    *,
    start_path: Path | str = ".",
) -> tuple[AccountProviderInstance, ...]:
    configs: list[dict[str, object]] = []

    global_path = global_config_path(agentos_home_dir())
    if global_path.exists():
        configs.append(load_global_config(global_path))

    project_root = find_agentos_project_root(start_path)
    if project_root is not None:
        project_path = project_config_path(project_root)
        if project_path.exists():
            configs.append(load_project_config(project_path))

    provider_instances: list[AccountProviderInstance] = []
    for config in configs:
        provider_instances.extend(_account_provider_instances_from_config(config))

    _validate_unique_account_instance_ids(tuple(provider_instances))
    return tuple(provider_instances)


def chat_account_stats(
    *,
    instance_ids: tuple[str, ...] | None = None,
    providers: tuple[str, ...] | None = None,
    refresh_usage: bool = False,
    full_output: bool = False,
    start_path: Path | str = ".",
) -> dict[str, object]:
    provider_families = supported_account_provider_families()
    if providers is not None:
        allowed_providers = set(providers)
        provider_families = tuple(
            provider_family
            for provider_family in provider_families
            if provider_family.family in allowed_providers
        )

    configured_instances = configured_account_provider_instances(start_path=start_path)
    if providers is not None:
        configured_instances = tuple(
            instance
            for instance in configured_instances
            if instance.provider in allowed_providers
        )

    if instance_ids:
        requested_ids = set(instance_ids)
        configured_instances = tuple(
            instance
            for instance in configured_instances
            if instance.instance_id in requested_ids
        )
        matched_ids = {instance.instance_id for instance in configured_instances}
        missing_ids = [instance_id for instance_id in instance_ids if instance_id not in matched_ids]
        if missing_ids:
            suffix = "s" if len(missing_ids) != 1 else ""
            raise CliError(f"unknown account instance id{suffix}: {', '.join(missing_ids)}")

    provider_payloads: list[dict[str, Any]] = []
    account_count = 0
    ok_count = 0
    error_count = 0

    provider_families_by_name = {
        provider_family.family: provider_family for provider_family in provider_families
    }
    provider_accounts_by_name = {
        provider_family.family: [] for provider_family in provider_families
    }
    collected_account_results = _collect_account_results(
        configured_instances=configured_instances,
        provider_families_by_name=provider_families_by_name,
        refresh_usage=refresh_usage,
    )

    for provider_name, account_payload in collected_account_results:
        provider_accounts_by_name[provider_name].append(account_payload)

    for provider_family in provider_families:
        provider_accounts = provider_accounts_by_name[provider_family.family]
        provider_ok_count = sum(1 for account in provider_accounts if account.get("check_status") == "ok")
        provider_error_count = sum(
            1 for account in provider_accounts if account.get("check_status") == "error"
        )
        provider_payload = {
            "provider": provider_family.family,
            "account_count": len(provider_accounts),
            "ok_count": provider_ok_count,
            "error_count": provider_error_count,
            "accounts": provider_accounts,
        }
        provider_payloads.append(provider_payload)
        account_count += provider_payload["account_count"]
        ok_count += provider_ok_count
        error_count += provider_error_count

    output_providers = (
        provider_payloads
        if full_output
        else [payload for payload in provider_payloads if payload["account_count"] > 0]
    )
    payload: dict[str, object] = {
        "status": "ok",
        "command": "chat accounts stats",
        "recorded_at": _utc_now_iso(),
        "provider_count": len(output_providers),
        "account_count": account_count,
        "ok_count": ok_count,
        "error_count": error_count,
        "providers": output_providers,
    }
    payload["history"] = _persist_chat_account_stats_payload(payload)
    return payload


def default_chat_account_stats_root() -> Path:
    return agentos_home_dir() / CHAT_ACCOUNT_STATS_DIRNAME


def default_chat_account_stats_tape_root() -> Path:
    return default_chat_account_stats_root() / CHAT_ACCOUNT_STATS_HISTORY_DIRNAME


def _collect_account_results(
    *,
    configured_instances: tuple[AccountProviderInstance, ...],
    provider_families_by_name: dict[str, AccountProviderFamily],
    refresh_usage: bool,
) -> list[tuple[str, dict[str, Any]]]:
    if not configured_instances:
        return []

    if len(configured_instances) == 1:
        instance = configured_instances[0]
        provider_family = provider_families_by_name[instance.provider]
        return [(instance.provider, provider_family.collect_stats(instance, refresh_usage))]

    max_workers = min(MAX_ACCOUNT_COLLECTION_WORKERS, len(configured_instances))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures: list[tuple[str, object]] = []
        for instance in configured_instances:
            provider_family = provider_families_by_name[instance.provider]
            future = executor.submit(provider_family.collect_stats, instance, refresh_usage)
            futures.append((instance.provider, future))

        collected_results: list[tuple[str, dict[str, Any]]] = []
        for provider_name, future in futures:
            account_payload = future.result()
            if not isinstance(account_payload, dict):
                raise CliError("account provider collector must return a JSON object payload")
            collected_results.append((provider_name, account_payload))
        return collected_results


def format_chat_account_stats_markdown(payload: dict[str, object]) -> str:
    lines = [
        "# Chat Accounts Stats",
        "",
    ]

    recorded_at = _string_or_none(payload.get("recorded_at"))
    recorded_at_display = _format_display_datetime_local(recorded_at)
    if recorded_at_display is not None:
        lines.append(f"- Recorded at: {recorded_at_display}")

    lines.extend(
        [
        f"- Providers: {payload['provider_count']}",
        f"- Accounts: {payload['account_count']}",
        f"- OK: {payload['ok_count']}",
        f"- Errors: {payload['error_count']}",
        ]
    )

    history = payload.get("history")
    if isinstance(history, dict):
        history_status = _string_or_none(history.get("status"))
        if history_status is not None:
            lines.append(f"- History: {history_status}")
        history_tape_root = _string_or_none(history.get("tape_root"))
        if history_tape_root is not None:
            lines.append(f"- History tape: {history_tape_root}")
        history_segment_name = _string_or_none(history.get("segment_name"))
        if history_segment_name is not None:
            lines.append(f"- History segment: {history_segment_name}")
        history_latest_path = _string_or_none(history.get("latest_path"))
        if history_latest_path is not None:
            lines.append(f"- History latest: {history_latest_path}")
        history_error = _string_or_none(history.get("message"))
        if history_error is not None:
            lines.append(f"- History error: {history_error}")

    providers = payload.get("providers")
    if not isinstance(providers, list) or not providers:
        return "\n".join(lines)

    for provider_payload in providers:
        if not isinstance(provider_payload, dict):
            continue

        provider_name = provider_payload.get("provider", "unknown")
        lines.extend(
            [
                "",
                f"## {provider_name}",
                "",
                f"- Accounts: {provider_payload.get('account_count', 0)}",
                f"- OK: {provider_payload.get('ok_count', 0)}",
                f"- Errors: {provider_payload.get('error_count', 0)}",
            ]
        )

        raw_accounts = provider_payload.get("accounts")
        if not isinstance(raw_accounts, list):
            continue

        for account in raw_accounts:
            if not isinstance(account, dict):
                continue

            lines.extend(
                [
                    "",
                    f"### {account.get('id', 'unknown')}",
                    "",
                    f"- Label: {account.get('label', '-')}",
                    f"- Status: {account.get('check_status', '-')}",
                ]
            )

            summary = account.get("summary")
            if summary is not None:
                lines.append(f"- Summary: {summary}")

            usage_status = account.get("usage_status")
            if usage_status is not None:
                lines.append(f"- Usage status: {usage_status}")

            usage_summary = account.get("usage_summary")
            if usage_summary is not None:
                lines.append(f"- Usage: {usage_summary}")

            usage_message = account.get("usage_message")
            if usage_message is not None:
                lines.append(f"- Usage note: {usage_message}")

            usage_error = account.get("usage_error")
            if isinstance(usage_error, dict):
                usage_error_type = usage_error.get("type")
                usage_error_message = usage_error.get("message")
                if usage_error_type is not None:
                    lines.append(f"- Usage error type: {usage_error_type}")
                if usage_error_message is not None:
                    lines.append(f"- Usage error: {usage_error_message}")

            usage_source = account.get("usage_source")
            if usage_source is not None:
                lines.append(f"- Usage source: {usage_source}")

            usage_refresh_cost_usd = account.get("usage_refresh_cost_usd")
            if usage_refresh_cost_usd is not None:
                lines.append(f"- Usage refresh cost: ${usage_refresh_cost_usd:.6f}")

            error = account.get("error")
            if isinstance(error, dict):
                error_type = error.get("type")
                error_message = error.get("message")
                if error_type is not None:
                    lines.append(f"- Error type: {error_type}")
                if error_message is not None:
                    lines.append(f"- Error: {error_message}")

            logged_in = account.get("logged_in")
            if logged_in is not None:
                lines.append(f"- Logged in: {'yes' if logged_in else 'no'}")

            auth_method = account.get("auth_method")
            if auth_method is not None:
                lines.append(f"- Auth method: {auth_method}")

            plan = account.get("plan")
            if plan is not None:
                lines.append(f"- Plan: {plan}")

            account_email = account.get("account_email")
            if account_email is not None:
                lines.append(f"- Email: {account_email}")

            organization_name = account.get("organization_name")
            if organization_name is not None:
                lines.append(f"- Organization: {organization_name}")

    return "\n".join(lines)


def format_chat_account_stats_usage(payload: dict[str, object]) -> str:
    lines = [
        "# Chat Accounts Usage",
        "",
    ]

    recorded_at = _string_or_none(payload.get("recorded_at"))
    recorded_at_display = _format_display_datetime_local(recorded_at)
    if recorded_at_display is not None:
        lines.append(f"- Recorded at: {recorded_at_display}")
    recorded_at_dt = _parse_iso_datetime_or_none(recorded_at)

    raw_providers = payload.get("providers")
    if not isinstance(raw_providers, list):
        return "\n".join(lines)

    account_blocks: list[list[str]] = []
    for provider_payload in raw_providers:
        if not isinstance(provider_payload, dict):
            continue
        raw_accounts = provider_payload.get("accounts")
        if not isinstance(raw_accounts, list):
            continue
        for account in raw_accounts:
            if not isinstance(account, dict):
                continue
            account_blocks.append(_format_chat_account_usage_block(account, recorded_at=recorded_at_dt))

    if not account_blocks:
        lines.append("- No account instances matched.")
        return "\n".join(lines)

    for index, account_block in enumerate(account_blocks):
        if index > 0:
            lines.append("")
        lines.extend(account_block)
    return "\n".join(lines)


def _account_provider_instances_from_config(config: dict[str, object]) -> tuple[AccountProviderInstance, ...]:
    chat_config = config.get("chat")
    if chat_config is None:
        return ()
    if not isinstance(chat_config, dict):
        raise CliError("config field chat must be a JSON object")

    accounts_config = chat_config.get("accounts")
    if accounts_config is None:
        return ()
    if not isinstance(accounts_config, dict):
        raise CliError("config field chat.accounts must be a JSON object")

    raw_instances = accounts_config.get("provider_instances")
    if raw_instances is None:
        return ()
    if not isinstance(raw_instances, list):
        raise CliError("config field chat.accounts.provider_instances must be a JSON array")

    provider_instances: list[AccountProviderInstance] = []
    for index, raw_instance in enumerate(raw_instances):
        if not isinstance(raw_instance, dict):
            raise CliError(f"chat.accounts.provider_instances[{index}] must be a JSON object")
        provider_instances.append(_account_provider_instance_from_config(raw_instance, index=index))
    return tuple(provider_instances)


def _format_chat_account_usage_block(
    account: dict[str, Any],
    *,
    recorded_at: datetime.datetime | None,
) -> list[str]:
    instance_id = _string_or_none(account.get("id")) or "unknown"
    label = _string_or_none(account.get("label"))
    if label is not None and label != instance_id:
        display_name = f"{instance_id} ({label})"
    else:
        display_name = instance_id

    lines = [f"{display_name}:"]
    usage = account.get("usage")
    if isinstance(usage, dict):
        raw_limits = usage.get("limits")
        if isinstance(raw_limits, list):
            formatted_limits = [
                _format_usage_limit_detailed(limit_payload, recorded_at=recorded_at)
                for limit_payload in raw_limits
                if isinstance(limit_payload, dict)
            ]
            formatted_limits = [item for item in formatted_limits if item is not None]
            if formatted_limits:
                lines.extend(f"  {item}" for item in formatted_limits)
                return lines

    lines.append(f"  {_format_chat_account_usage_summary(account)}")
    return lines


def _format_chat_account_usage_summary(account: dict[str, Any]) -> str:
    usage = account.get("usage")
    if isinstance(usage, dict):
        raw_limits = usage.get("limits")
        if isinstance(raw_limits, list):
            formatted_limits = [
                _format_usage_limit_compact(limit_payload)
                for limit_payload in raw_limits
                if isinstance(limit_payload, dict)
            ]
            formatted_limits = [item for item in formatted_limits if item is not None]
            if formatted_limits:
                return "Usage: " + ", ".join(formatted_limits)

    usage_status = _string_or_none(account.get("usage_status"))
    usage_message = _string_or_none(account.get("usage_message"))
    usage_error = account.get("usage_error")
    if usage_status == "unavailable":
        if usage_message is not None:
            return f"Usage unavailable: {usage_message}"
        return "Usage unavailable"
    if usage_status == "error":
        if isinstance(usage_error, dict):
            error_message = _string_or_none(usage_error.get("message"))
            if error_message is not None:
                return f"Usage error: {error_message}"
        return "Usage error"

    usage_summary = _string_or_none(account.get("usage_summary"))
    if usage_summary is not None:
        return f"Usage: {usage_summary}"

    summary = _string_or_none(account.get("summary"))
    if summary is not None:
        return summary
    return "No usage data"


def _format_usage_limit_compact(limit_payload: dict[str, Any]) -> str | None:
    label = _string_or_none(limit_payload.get("window_label")) or _string_or_none(limit_payload.get("limit_label"))
    used_percent = limit_payload.get("used_percent")
    if label is None and not isinstance(used_percent, int):
        return None
    if isinstance(used_percent, int):
        return f"{label or 'usage'} [{_usage_progress_bar(used_percent)}] {used_percent}%"
    return label


def _format_usage_limit_detailed(
    limit_payload: dict[str, Any],
    *,
    recorded_at: datetime.datetime | None,
) -> str | None:
    compact = _format_usage_limit_compact(limit_payload)
    if compact is None:
        return None

    reset_at = _format_usage_limit_reset_at(limit_payload)
    if reset_at is None:
        return compact
    remaining = _format_usage_limit_remaining(limit_payload, recorded_at=recorded_at)
    if remaining is None:
        return f"{compact} | resets {reset_at}"
    return f"{compact} | resets {reset_at} | in {remaining}"


def _format_usage_limit_reset_at(limit_payload: dict[str, Any]) -> str | None:
    raw_reset_at = _string_or_none(limit_payload.get("resets_at")) or _string_or_none(
        limit_payload.get("period_ends_at")
    )
    if raw_reset_at is None:
        return None

    return _format_display_datetime_local(raw_reset_at)


def _format_usage_limit_remaining(
    limit_payload: dict[str, Any],
    *,
    recorded_at: datetime.datetime | None,
) -> str | None:
    if recorded_at is None:
        return None

    raw_reset_at = _string_or_none(limit_payload.get("resets_at")) or _string_or_none(
        limit_payload.get("period_ends_at")
    )
    reset_at = _parse_iso_datetime_or_none(raw_reset_at)
    if reset_at is None:
        return None

    diff_seconds = int((reset_at - recorded_at).total_seconds())
    return _format_remaining_duration(diff_seconds)


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
    if not parts:
        parts.append("0m")
    return " ".join(parts)


def _usage_progress_bar(used_percent: int, *, width: int = 10) -> str:
    clamped_percent = max(0, min(100, used_percent))
    filled = min(width, (clamped_percent + 5) // 10)
    return ("#" * filled) + ("-" * (width - filled))


def _account_provider_instance_from_config(
    raw_instance: dict[str, object],
    *,
    index: int,
) -> AccountProviderInstance:
    family_name = raw_instance.get("provider")
    if not isinstance(family_name, str) or not family_name:
        raise CliError(f"chat.accounts.provider_instances[{index}].provider is required")

    if _account_provider_family_for_name(family_name) is None:
        supported_providers = ", ".join(
            sorted(provider_family.family for provider_family in supported_account_provider_families())
        )
        raise CliError(
            f"chat.accounts.provider_instances[{index}].provider must be one of: {supported_providers}"
        )

    raw_instance_id = raw_instance.get("id")
    if not isinstance(raw_instance_id, str) or not raw_instance_id.strip():
        raise CliError(f"chat.accounts.provider_instances[{index}].id is required")
    instance_id = validate_string_for_path(
        raw_instance_id.strip(),
        field_name=f"chat.accounts.provider_instances[{index}].id",
    )

    raw_label = raw_instance.get("label")
    if raw_label is None:
        label = instance_id
    elif not isinstance(raw_label, str) or not raw_label.strip():
        raise CliError(f"chat.accounts.provider_instances[{index}].label must be a non-empty string")
    else:
        label = raw_label.strip()

    raw_cli_command = raw_instance.get("cli_command")
    cli_command = _load_string_argv(
        raw_cli_command,
        field_name=f"chat.accounts.provider_instances[{index}].cli_command",
    )
    if not cli_command:
        raise CliError(f"chat.accounts.provider_instances[{index}].cli_command must not be empty")

    raw_env = raw_instance.get("env")
    env = _load_string_mapping(
        raw_env,
        field_name=f"chat.accounts.provider_instances[{index}].env",
    )

    raw_timeout_sec = raw_instance.get("timeout_sec")
    if raw_timeout_sec is None:
        timeout_sec = DEFAULT_ACCOUNT_TIMEOUT_SEC
    elif isinstance(raw_timeout_sec, bool) or not isinstance(raw_timeout_sec, int) or raw_timeout_sec < 1:
        raise CliError(
            f"chat.accounts.provider_instances[{index}].timeout_sec must be an integer greater than 0"
        )
    else:
        timeout_sec = raw_timeout_sec

    raw_live_usage_refresh = raw_instance.get("live_usage_refresh")
    if raw_live_usage_refresh is None:
        live_usage_refresh = False
    elif not isinstance(raw_live_usage_refresh, bool):
        raise CliError(
            f"chat.accounts.provider_instances[{index}].live_usage_refresh must be a boolean"
        )
    else:
        live_usage_refresh = raw_live_usage_refresh

    return AccountProviderInstance(
        provider=family_name,
        instance_id=instance_id,
        label=label,
        cli_command=cli_command,
        env=env,
        timeout_sec=timeout_sec,
        live_usage_refresh=live_usage_refresh,
    )


def _validate_unique_account_instance_ids(
    provider_instances: tuple[AccountProviderInstance, ...],
) -> None:
    seen_instances: dict[str, AccountProviderInstance] = {}
    for provider_instance in provider_instances:
        existing = seen_instances.get(provider_instance.instance_id)
        if existing is None:
            seen_instances[provider_instance.instance_id] = provider_instance
            continue
        raise CliError(
            "chat.accounts.provider_instances ids must be unique; "
            f"duplicate id {provider_instance.instance_id} for providers "
            f"{existing.provider} and {provider_instance.provider}"
        )


def _account_provider_family_for_name(family_name: str) -> AccountProviderFamily | None:
    for family in supported_account_provider_families():
        if family.family == family_name:
            return family
    return None


def _collect_codex_account_stats(
    instance: AccountProviderInstance,
    refresh_usage: bool,
) -> dict[str, Any]:
    del refresh_usage

    with ThreadPoolExecutor(max_workers=2) as executor:
        auth_future = executor.submit(
            _collect_parsed_command_payload,
            instance,
            extra_args=("login", "status"),
            parser=_parse_codex_login_status,
        )
        usage_future = executor.submit(_collect_codex_usage_payload, instance)

    try:
        auth_payload = auth_future.result()
    except AccountCommandError as exc:
        return _error_account_result(
            instance,
            error_type=exc.error_type,
            message=exc.message,
            exit_code=exc.exit_code,
        )

    usage_payload: dict[str, Any]
    try:
        usage_payload = usage_future.result()
    except AccountCommandError as exc:
        usage_payload = _usage_error_payload(
            error_type=exc.error_type,
            message=exc.message,
            exit_code=exc.exit_code,
        )
    except (CliError, json.JSONDecodeError, TypeError, ValueError) as exc:
        usage_payload = _usage_error_payload(
            error_type="invalid_output",
            message=str(exc),
        )

    return _ok_account_result(
        instance,
        _merge_account_payloads(auth_payload, usage_payload),
    )


def _collect_codex_usage_payload(instance: AccountProviderInstance) -> dict[str, Any]:
    return _parse_codex_rate_limits(_read_codex_account_rate_limits(instance))


def _collect_claude_code_account_stats(
    instance: AccountProviderInstance,
    refresh_usage: bool,
) -> dict[str, Any]:
    should_refresh_usage = refresh_usage or instance.live_usage_refresh

    if should_refresh_usage:
        with ThreadPoolExecutor(max_workers=2) as executor:
            auth_future = executor.submit(
                _collect_parsed_command_payload,
                instance,
                extra_args=("auth", "status", "--json"),
                parser=_parse_claude_code_auth_status,
            )
            usage_future = executor.submit(_collect_claude_code_live_usage, instance)

            try:
                auth_payload = auth_future.result()
            except AccountCommandError as exc:
                return _error_account_result(
                    instance,
                    error_type=exc.error_type,
                    message=exc.message,
                    exit_code=exc.exit_code,
                )

            try:
                usage_payload = usage_future.result()
            except AccountCommandError as exc:
                usage_payload = _usage_error_payload(
                    error_type=exc.error_type,
                    message=exc.message,
                    exit_code=exc.exit_code,
                )
            except (CliError, json.JSONDecodeError, TypeError, ValueError) as exc:
                usage_payload = _usage_error_payload(
                    error_type="invalid_output",
                    message=str(exc),
                )
    else:
        try:
            auth_payload = _collect_parsed_command_payload(
                instance,
                extra_args=("auth", "status", "--json"),
                parser=_parse_claude_code_auth_status,
            )
        except AccountCommandError as exc:
            return _error_account_result(
                instance,
                error_type=exc.error_type,
                message=exc.message,
                exit_code=exc.exit_code,
            )

        usage_payload = _usage_unavailable_payload(
            "live usage refresh disabled; pass --refresh-usage or set live_usage_refresh=true",
        )

    return _ok_account_result(
        instance,
        _merge_account_payloads(auth_payload, usage_payload),
    )


def _collect_parsed_command_payload(
    instance: AccountProviderInstance,
    *,
    extra_args: tuple[str, ...],
    parser: Callable[[str], dict[str, Any]],
    cwd: str | None = None,
    extra_env: dict[str, str] | None = None,
) -> dict[str, Any]:
    result = _run_account_command(
        instance,
        extra_args=extra_args,
        cwd=cwd,
        extra_env=extra_env,
    )

    success_output = _successful_command_output(result)
    try:
        return parser(success_output)
    except (CliError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise AccountCommandError(
            error_type="invalid_output",
            message=str(exc),
        ) from exc


def _run_account_command(
    instance: AccountProviderInstance,
    *,
    extra_args: tuple[str, ...],
    cwd: str | None = None,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    command = [*instance.cli_command, *extra_args]
    env = os.environ.copy()
    env.update(instance.env_mapping())
    if extra_env is not None:
        env.update(extra_env)

    run_kwargs: dict[str, Any] = {
        "capture_output": True,
        "text": True,
        "check": False,
        "env": env,
        "timeout": instance.timeout_sec,
    }
    if cwd is not None:
        run_kwargs["cwd"] = cwd

    try:
        result = subprocess.run(command, **run_kwargs)
    except FileNotFoundError as exc:
        raise AccountCommandError(
            error_type="command_not_found",
            message=str(exc),
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise AccountCommandError(
            error_type="timeout",
            message=f"provider command timed out after {instance.timeout_sec} seconds",
        ) from exc
    except OSError as exc:
        raise AccountCommandError(
            error_type="command_failed",
            message=str(exc),
        ) from exc

    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    if result.returncode != 0:
        raise AccountCommandError(
            error_type="command_failed",
            message=stderr or stdout or f"provider command exited with code {result.returncode}",
            exit_code=result.returncode,
        )
    return result


def _successful_command_output(result: subprocess.CompletedProcess[str]) -> str:
    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    success_output = stdout or stderr
    if not success_output:
        raise AccountCommandError(
            error_type="invalid_output",
            message="provider command returned no output",
        )
    return success_output


def _read_codex_account_rate_limits(instance: AccountProviderInstance) -> dict[str, Any]:
    command = [*instance.cli_command, "app-server"]
    env = os.environ.copy()
    env.update(instance.env_mapping())

    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
    except FileNotFoundError as exc:
        raise AccountCommandError(
            error_type="command_not_found",
            message=str(exc),
        ) from exc
    except OSError as exc:
        raise AccountCommandError(
            error_type="command_failed",
            message=str(exc),
        ) from exc

    init_request = {
        "id": 1,
        "method": "initialize",
        "params": {
            "clientInfo": {
                "name": "agentos",
                "version": "1",
            }
        },
    }
    rate_limits_request = {
        "id": 2,
        "method": "account/rateLimits/read",
    }

    try:
        _write_json_line(process, init_request)
        init_response = _read_process_json_line(process, timeout_sec=instance.timeout_sec)
        if init_response.get("id") != 1:
            raise CliError("codex app-server initialize returned an unexpected response id")
        if "result" not in init_response:
            raise CliError("codex app-server initialize response is missing result")

        _write_json_line(process, rate_limits_request)
        rate_limits_response = _read_process_json_line(process, timeout_sec=instance.timeout_sec)
        if rate_limits_response.get("id") != 2:
            raise CliError("codex app-server rate-limit request returned an unexpected response id")

        error_payload = rate_limits_response.get("error")
        if error_payload is not None:
            if isinstance(error_payload, dict):
                message = _string_or_none(error_payload.get("message"))
                code = error_payload.get("code")
                suffix = f" (code {code})" if code is not None else ""
                raise AccountCommandError(
                    error_type="command_failed",
                    message=message or f"codex app-server returned an error{suffix}",
                )
            raise CliError("codex app-server returned an invalid error payload")

        payload = rate_limits_response.get("result")
        if not isinstance(payload, dict):
            raise CliError("codex app-server rate-limit response must be a JSON object")
        return payload
    except subprocess.TimeoutExpired as exc:
        raise AccountCommandError(
            error_type="timeout",
            message=f"provider command timed out after {instance.timeout_sec} seconds",
        ) from exc
    except BrokenPipeError as exc:
        stderr = _read_process_stderr(process)
        raise AccountCommandError(
            error_type="command_failed",
            message=stderr or str(exc),
        ) from exc
    finally:
        if process.stdin is not None and not process.stdin.closed:
            process.stdin.close()
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=1)

    if process.returncode not in (0, None):
        raise AccountCommandError(
            error_type="command_failed",
            message=_read_process_stderr(process)
            or f"provider command exited with code {process.returncode}",
            exit_code=process.returncode,
        )
    raise CliError("codex app-server rate-limit response was not returned")


def _write_json_line(process: subprocess.Popen[str], payload: dict[str, Any]) -> None:
    if process.stdin is None:
        raise CliError("provider process stdin is not available")
    process.stdin.write(json.dumps(payload) + "\n")
    process.stdin.flush()


def _read_process_json_line(
    process: subprocess.Popen[str],
    *,
    timeout_sec: int,
) -> dict[str, Any]:
    if process.stdout is None:
        raise CliError("provider process stdout is not available")

    ready, _, _ = select.select([process.stdout], [], [], timeout_sec)
    if not ready:
        raise subprocess.TimeoutExpired(process.args, timeout_sec)

    line = process.stdout.readline()
    if not line:
        stderr = _read_process_stderr(process)
        raise AccountCommandError(
            error_type="command_failed",
            message=stderr or "provider command returned no response",
            exit_code=process.poll(),
        )

    try:
        payload = json.loads(line)
    except json.JSONDecodeError as exc:
        raise CliError("provider command returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise CliError("provider command must return a JSON object")
    return payload


def _read_process_stderr(process: subprocess.Popen[str]) -> str:
    if process.stderr is None:
        return ""
    return process.stderr.read().strip()


def _parse_codex_login_status(stdout: str) -> dict[str, Any]:
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if not lines:
        raise CliError("provider command returned no output")

    summary = lines[0]
    logged_in: bool | None = None
    auth_method = None
    lowered = summary.lower()
    if lowered.startswith("logged in using "):
        logged_in = True
        auth_method = summary[len("Logged in using "):].strip()
    elif "not logged in" in lowered:
        logged_in = False

    provider_status: dict[str, object] = {"raw_output": "\n".join(lines)}
    if auth_method is not None:
        provider_status["auth_method"] = auth_method

    return {
        "auth_summary": summary,
        "logged_in": logged_in,
        "auth_method": auth_method,
        "provider_status": provider_status,
    }


def _parse_claude_code_auth_status(stdout: str) -> dict[str, Any]:
    payload = json.loads(stdout)
    if not isinstance(payload, dict):
        raise CliError("provider command must return a JSON object")

    logged_in = payload.get("loggedIn")
    if logged_in is not None and not isinstance(logged_in, bool):
        raise CliError("provider status field loggedIn must be a boolean when present")

    auth_method = _string_or_none(payload.get("authMethod"))
    subscription_type = _string_or_none(payload.get("subscriptionType"))
    email = _string_or_none(payload.get("email"))
    organization_id = _string_or_none(payload.get("orgId"))
    organization_name = _string_or_none(payload.get("orgName"))

    if logged_in is False:
        summary = "Not logged in"
    elif auth_method and subscription_type:
        summary = f"Logged in via {auth_method} ({subscription_type})"
    elif auth_method:
        summary = f"Logged in via {auth_method}"
    elif logged_in:
        summary = "Logged in"
    else:
        summary = "Authentication status unavailable"

    return {
        "auth_summary": summary,
        "logged_in": logged_in,
        "auth_method": auth_method,
        "plan": subscription_type,
        "account_email": email,
        "organization_id": organization_id,
        "organization_name": organization_name,
        "provider_status": {
            "auth_status": payload,
        },
    }


def _parse_codex_rate_limits(payload: dict[str, Any]) -> dict[str, Any]:
    rate_limits_by_id = payload.get("rateLimitsByLimitId")
    snapshots: list[tuple[str | None, dict[str, Any]]] = []
    if isinstance(rate_limits_by_id, dict) and rate_limits_by_id:
        for limit_id, snapshot in rate_limits_by_id.items():
            if not isinstance(limit_id, str):
                raise CliError("codex rate limit id must be a string")
            if not isinstance(snapshot, dict):
                raise CliError("codex rate limit snapshot must be an object")
            snapshots.append((limit_id, snapshot))
    else:
        raw_rate_limits = payload.get("rateLimits")
        if not isinstance(raw_rate_limits, dict):
            raise CliError("codex rate limit response is missing rateLimits")
        snapshots.append((_string_or_none(raw_rate_limits.get("limitId")), raw_rate_limits))

    plan: str | None = None
    credits_payload: dict[str, Any] | None = None
    limits: list[dict[str, Any]] = []
    for limit_id, snapshot in snapshots:
        snapshot_plan = _string_or_none(snapshot.get("planType"))
        if snapshot_plan is not None and plan is None:
            plan = snapshot_plan

        raw_credits = snapshot.get("credits")
        if credits_payload is None and isinstance(raw_credits, dict):
            credits_payload = _parse_codex_credits(raw_credits)

        limits.extend(_parse_codex_snapshot_windows(snapshot, limit_id=limit_id))

    usage_summary = ", ".join(_format_limit_summary(limit_payload) for limit_payload in limits) or None

    payload_data: dict[str, Any] = {
        "usage_status": "ok",
        "usage_source": "app-server",
        "usage_summary": usage_summary,
        "usage": {
            "kind": "rate_limits",
            "limits": limits,
            "credits": credits_payload,
        },
        "provider_status": {
            "rate_limits": payload,
        },
    }
    if plan is not None:
        payload_data["plan"] = plan
    return payload_data


def _parse_codex_credits(payload: dict[str, Any]) -> dict[str, Any]:
    has_credits = payload.get("hasCredits")
    unlimited = payload.get("unlimited")
    if not isinstance(has_credits, bool):
        raise CliError("codex credits.hasCredits must be a boolean")
    if not isinstance(unlimited, bool):
        raise CliError("codex credits.unlimited must be a boolean")
    return {
        "balance": _string_or_none(payload.get("balance")),
        "has_credits": has_credits,
        "unlimited": unlimited,
    }


def _parse_codex_snapshot_windows(
    snapshot: dict[str, Any],
    *,
    limit_id: str | None,
) -> list[dict[str, Any]]:
    limits: list[dict[str, Any]] = []
    for window_key in ("primary", "secondary"):
        raw_window = snapshot.get(window_key)
        if raw_window is None:
            continue
        if not isinstance(raw_window, dict):
            raise CliError(f"codex {window_key} rate-limit window must be an object")

        used_percent = _required_int(
            raw_window.get("usedPercent"),
            field_name=f"codex {window_key} usedPercent",
        )
        window_duration_mins = _optional_int(
            raw_window.get("windowDurationMins"),
            field_name=f"codex {window_key} windowDurationMins",
        )
        resets_at_epoch = _optional_int(
            raw_window.get("resetsAt"),
            field_name=f"codex {window_key} resetsAt",
        )
        period_started_at, period_ends_at = _period_bounds_from_reset(
            resets_at_epoch=resets_at_epoch,
            period_duration_mins=window_duration_mins,
        )
        limits.append(
            {
                "limit_id": limit_id,
                "window_key": window_key,
                "window_label": _codex_window_label(window_duration_mins, window_key=window_key),
                "used_percent": used_percent,
                "resets_at": _iso_from_epoch_seconds(resets_at_epoch),
                "window_duration_mins": window_duration_mins,
                "period_duration_mins": window_duration_mins,
                "period_started_at": period_started_at,
                "period_ends_at": period_ends_at,
            }
        )
    return limits


def _codex_window_label(window_duration_mins: int | None, *, window_key: str) -> str:
    if window_duration_mins == 300:
        return "5h"
    if window_duration_mins == 1_440:
        return "24h"
    if window_duration_mins == 10_080:
        return "7d"
    if window_duration_mins is not None:
        return f"{window_duration_mins}m"
    return window_key


def _collect_claude_code_live_usage(instance: AccountProviderInstance) -> dict[str, Any]:
    try:
        return _collect_claude_code_live_usage_from_statusline(instance)
    except (AccountCommandError, CliError, json.JSONDecodeError, TypeError, ValueError):
        return _collect_claude_code_live_usage_from_stream_json(instance)


def _collect_claude_code_live_usage_from_statusline(
    instance: AccountProviderInstance,
) -> dict[str, Any]:
    timeout_sec = max(instance.timeout_sec, 45)
    workspace_root = _claude_code_refresh_workspace_root(instance)
    workspace_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="agentos-claude-usage-") as temp_dir:
        temp_root = Path(temp_dir)
        capture_path = temp_root / "statusline.json"
        settings_path = temp_root / "settings.json"
        script_path = temp_root / "capture-statusline.sh"

        script_path.write_text(
            "#!/bin/sh\n"
            f"cat > {json.dumps(str(capture_path))}\n"
            "exit 0\n",
            encoding="utf-8",
        )
        script_path.chmod(0o700)
        settings_path.write_text(
            json.dumps(
                {
                    "statusLine": {
                        "type": "command",
                        "command": str(script_path),
                    }
                }
            ),
            encoding="utf-8",
        )

        statusline_payload = _run_claude_code_statusline_refresh_session(
            instance,
            cwd=workspace_root,
            capture_path=capture_path,
            settings_path=settings_path,
            timeout_sec=timeout_sec,
        )

    _cleanup_claude_code_refresh_transcript(statusline_payload)
    return _parse_claude_code_statusline_usage_output(statusline_payload)


def _collect_claude_code_live_usage_from_stream_json(
    instance: AccountProviderInstance,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="agentos-claude-usage-") as temp_dir:
        result = _run_account_command(
            instance,
            extra_args=(
                "-p",
                _CLAUDE_USAGE_REFRESH_PROMPT,
                "--output-format",
                "stream-json",
                "--verbose",
                "--model",
                _CLAUDE_USAGE_REFRESH_MODEL,
                "--disable-slash-commands",
                "--setting-sources",
                "local",
                "--no-session-persistence",
            ),
            cwd=temp_dir,
            extra_env={
                "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
                "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
            },
        )
    return _parse_claude_code_live_usage_output(result.stdout)


def _run_claude_code_statusline_refresh_session(
    instance: AccountProviderInstance,
    *,
    cwd: Path,
    capture_path: Path,
    settings_path: Path,
    timeout_sec: int,
) -> dict[str, Any]:
    command = [
        *instance.cli_command,
        "--model",
        _CLAUDE_USAGE_REFRESH_MODEL,
        "--disable-slash-commands",
        "--setting-sources",
        "local",
        "--settings",
        str(settings_path),
    ]
    env = os.environ.copy()
    env.update(instance.env_mapping())
    env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] = "1"
    env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"

    try:
        master_fd, slave_fd = pty.openpty()
        process = subprocess.Popen(
            command,
            cwd=str(cwd),
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            env=env,
            text=False,
            close_fds=True,
        )
    except FileNotFoundError as exc:
        raise AccountCommandError(
            error_type="command_not_found",
            message=str(exc),
        ) from exc
    except OSError as exc:
        raise AccountCommandError(
            error_type="command_failed",
            message=str(exc),
        ) from exc
    finally:
        if "slave_fd" in locals():
            os.close(slave_fd)

    os.set_blocking(master_fd, False)
    start = time.monotonic()
    next_trust_confirm_at = start + CLAUDE_REFRESH_TRUST_CONFIRM_DELAY_SEC
    prompt_fallback_at = start + CLAUDE_REFRESH_PROMPT_FALLBACK_DELAY_SEC
    prompt_sent = False
    trust_prompt_seen = False
    trust_confirm_sent = False
    transcript_chunks: list[bytes] = []
    statusline_payload: dict[str, Any] | None = None

    try:
        while True:
            now = time.monotonic()
            if now - start >= timeout_sec:
                raise AccountCommandError(
                    error_type="timeout",
                    message=f"provider command timed out after {timeout_sec} seconds",
                )

            transcript_chunks.extend(_read_pty_chunks(master_fd, timeout_sec=0.25))
            transcript_text = _normalize_terminal_output(transcript_chunks)

            if not prompt_sent and _claude_refresh_trust_prompt_visible(transcript_text):
                trust_prompt_seen = True
                if now >= next_trust_confirm_at:
                    _write_pty(master_fd, b"\r")
                    trust_confirm_sent = True
                    next_trust_confirm_at = now + CLAUDE_REFRESH_TRUST_CONFIRM_RETRY_SEC

            if not prompt_sent and _claude_refresh_main_prompt_visible(transcript_text):
                _write_pty(master_fd, (_CLAUDE_USAGE_REFRESH_PROMPT + "\r").encode("utf-8"))
                prompt_sent = True

            if (
                not prompt_sent
                and not _claude_refresh_trust_prompt_visible(transcript_text)
                and ((not trust_prompt_seen and now >= prompt_fallback_at) or trust_confirm_sent)
            ):
                _write_pty(master_fd, (_CLAUDE_USAGE_REFRESH_PROMPT + "\r").encode("utf-8"))
                prompt_sent = True

            statusline_payload = _load_claude_code_statusline_capture(capture_path)
            if statusline_payload is not None:
                break

            if process.poll() is not None:
                break
    finally:
        _terminate_pty_process(process, master_fd)

    if statusline_payload is not None:
        return statusline_payload

    transcript = b"".join(transcript_chunks).decode("utf-8", errors="ignore").strip()
    if process.returncode not in (0, None):
        raise AccountCommandError(
            error_type="command_failed",
            message=transcript or f"provider command exited with code {process.returncode}",
            exit_code=process.returncode,
        )
    raise AccountCommandError(
        error_type="invalid_output",
        message="provider command did not emit a status line payload with rate limits",
    )


def _read_pty_chunks(master_fd: int, *, timeout_sec: float) -> list[bytes]:
    chunks: list[bytes] = []
    deadline = time.monotonic() + timeout_sec
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return chunks
        ready, _, _ = select.select([master_fd], [], [], remaining)
        if not ready:
            return chunks
        try:
            chunk = os.read(master_fd, 65_536)
        except BlockingIOError:
            return chunks
        except OSError:
            return chunks
        if not chunk:
            return chunks
        chunks.append(chunk)


def _normalize_terminal_output(chunks: list[bytes], *, tail_bytes: int = 32_768) -> str:
    if not chunks:
        return ""

    tail = b"".join(chunks)[-tail_bytes:]
    text = tail.decode("utf-8", errors="ignore")
    text = _ANSI_OSC_RE.sub(" ", text)
    text = _ANSI_CSI_RE.sub(" ", text)
    text = _CONTROL_CHARS_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def _claude_refresh_trust_prompt_visible(text: str) -> bool:
    return "quick safety check" in text or "yes, i trust this folder" in text


def _claude_refresh_main_prompt_visible(text: str) -> bool:
    return (
        "welcome back" in text
        or "claude code v" in text
        or "no recent activity" in text
        or "haiku 4.5" in text
    )


def _write_pty(master_fd: int, payload: bytes) -> None:
    try:
        os.write(master_fd, payload)
    except OSError:
        return


def _terminate_pty_process(process: subprocess.Popen[bytes], master_fd: int) -> None:
    try:
        _write_pty(master_fd, b"\x03")
        time.sleep(CLAUDE_REFRESH_INTERRUPT_SETTLE_SEC)
        _write_pty(master_fd, b"\x03")
        if process.poll() is None:
            process.terminate()
    finally:
        try:
            process.wait(timeout=CLAUDE_REFRESH_TERMINATE_WAIT_SEC)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=CLAUDE_REFRESH_TERMINATE_WAIT_SEC)
        try:
            os.close(master_fd)
        except OSError:
            pass


def _load_claude_code_statusline_capture(capture_path: Path) -> dict[str, Any] | None:
    if not capture_path.exists():
        return None
    try:
        payload = json.loads(capture_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    rate_limits = payload.get("rate_limits")
    if not isinstance(rate_limits, dict) or not rate_limits:
        return None
    return payload


def _claude_code_refresh_workspace_root(instance: AccountProviderInstance) -> Path:
    return default_chat_account_stats_root() / CLAUDE_REFRESH_WORKSPACE_DIRNAME / instance.instance_id


def _cleanup_claude_code_refresh_transcript(statusline_payload: dict[str, Any]) -> None:
    transcript_path_value = _string_or_none(statusline_payload.get("transcript_path"))
    if transcript_path_value is None:
        return
    transcript_path = Path(transcript_path_value)
    claude_projects_root = Path.home() / ".claude" / "projects"
    try:
        transcript_path.relative_to(claude_projects_root)
    except ValueError:
        return

    try:
        transcript_path.unlink(missing_ok=True)
        parent = transcript_path.parent
        while parent != claude_projects_root:
            parent.rmdir()
            parent = parent.parent
    except OSError:
        return


def _parse_claude_code_statusline_usage_output(statusline_payload: dict[str, Any]) -> dict[str, Any]:
    raw_rate_limits = statusline_payload.get("rate_limits")
    if not isinstance(raw_rate_limits, dict):
        raise CliError("claude status line payload is missing rate_limits")

    limit_order = {
        "five_hour": 0,
        "seven_day": 1,
        "seven_day_opus": 2,
        "seven_day_sonnet": 3,
        "overage": 4,
    }
    limits: list[dict[str, Any]] = []
    for limit_type, raw_limit_payload in sorted(
        raw_rate_limits.items(),
        key=lambda item: (limit_order.get(item[0], 100), item[0]),
    ):
        if not isinstance(limit_type, str):
            raise CliError("claude status line rate limit key must be a string")
        if not isinstance(raw_limit_payload, dict):
            raise CliError("claude status line rate limit payload must be an object")

        used_percentage = _optional_float(
            raw_limit_payload.get("used_percentage"),
            field_name=f"claude {limit_type} used_percentage",
        )
        used_percent = round(used_percentage) if used_percentage is not None else None
        resets_at_epoch = _optional_int(
            raw_limit_payload.get("resets_at"),
            field_name=f"claude {limit_type} resets_at",
        )
        period_duration_mins = _claude_rate_limit_duration_mins(limit_type)
        period_started_at, period_ends_at = _period_bounds_from_reset(
            resets_at_epoch=resets_at_epoch,
            period_duration_mins=period_duration_mins,
        )
        limits.append(
            {
                "limit_type": limit_type,
                "limit_label": _claude_rate_limit_label(limit_type),
                "used_percent": used_percent,
                "resets_at": _iso_from_epoch_seconds(resets_at_epoch),
                "period_duration_mins": period_duration_mins,
                "period_started_at": period_started_at,
                "period_ends_at": period_ends_at,
            }
        )

    usage_payload: dict[str, Any] = {
        "usage_status": "ok",
        "usage_source": "interactive-statusline",
        "usage_summary": ", ".join(_format_limit_summary(limit_payload) for limit_payload in limits) or None,
        "usage": {
            "kind": "subscription_rate_limit",
            "limits": limits,
        },
        "provider_status": {
            "live_usage_refresh": {
                "statusline": statusline_payload,
            }
        },
    }

    raw_cost = statusline_payload.get("cost")
    if isinstance(raw_cost, dict):
        refresh_cost = _optional_float(raw_cost.get("total_cost_usd"), field_name="claude total_cost_usd")
        if refresh_cost is not None:
            usage_payload["usage_refresh_cost_usd"] = refresh_cost
            usage_payload["usage"]["refresh_cost_usd"] = refresh_cost

    raw_model = statusline_payload.get("model")
    if isinstance(raw_model, dict):
        refresh_model = _string_or_none(raw_model.get("id")) or _string_or_none(raw_model.get("display_name"))
        if refresh_model is not None:
            usage_payload["usage"]["refresh_model"] = refresh_model

    session_id = _string_or_none(statusline_payload.get("session_id"))
    if session_id is not None:
        usage_payload["usage"]["refresh_session_id"] = session_id

    return usage_payload


def _parse_claude_code_live_usage_output(stdout: str) -> dict[str, Any]:
    event_payload: dict[str, Any] | None = None
    result_payload: dict[str, Any] | None = None
    for line in stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parsed = json.loads(stripped)
        if not isinstance(parsed, dict):
            raise CliError("provider command must return JSON objects")
        if parsed.get("type") == "rate_limit_event":
            event_payload = parsed
        elif parsed.get("type") == "result":
            result_payload = parsed

    if event_payload is None:
        return _usage_unavailable_payload("provider did not emit a rate_limit_event")

    rate_limit_info = event_payload.get("rate_limit_info")
    if not isinstance(rate_limit_info, dict):
        raise CliError("claude live usage payload is missing rate_limit_info")

    rate_limit_type = _string_or_none(rate_limit_info.get("rateLimitType"))
    utilization = _optional_float(rate_limit_info.get("utilization"), field_name="claude utilization")
    used_percent = round(utilization * 100) if utilization is not None else None
    period_duration_mins = _claude_rate_limit_duration_mins(rate_limit_type)
    resets_at_epoch = _optional_int(rate_limit_info.get("resetsAt"), field_name="claude resetsAt")
    period_started_at, period_ends_at = _period_bounds_from_reset(
        resets_at_epoch=resets_at_epoch,
        period_duration_mins=period_duration_mins,
    )
    limit_payload = {
        "limit_type": rate_limit_type,
        "limit_label": _claude_rate_limit_label(rate_limit_type),
        "used_percent": used_percent,
        "resets_at": _iso_from_epoch_seconds(resets_at_epoch),
        "period_duration_mins": period_duration_mins,
        "period_started_at": period_started_at,
        "period_ends_at": period_ends_at,
        "status": _string_or_none(rate_limit_info.get("status")),
        "is_using_overage": _optional_bool(
            rate_limit_info.get("isUsingOverage"),
            field_name="claude isUsingOverage",
        ),
        "surpassed_threshold": _optional_float(
            rate_limit_info.get("surpassedThreshold"),
            field_name="claude surpassedThreshold",
        ),
    }

    usage_payload: dict[str, Any] = {
        "usage_status": "ok",
        "usage_source": "live-refresh",
        "usage_summary": _format_limit_summary(limit_payload),
        "usage": {
            "kind": "subscription_rate_limit",
            "limits": [limit_payload],
        },
        "provider_status": {
            "live_usage_refresh": {
                "rate_limit_event": event_payload,
            }
        },
    }

    if isinstance(result_payload, dict):
        usage_payload["provider_status"]["live_usage_refresh"]["result"] = result_payload
        refresh_cost = _optional_float(result_payload.get("total_cost_usd"), field_name="claude total_cost_usd")
        if refresh_cost is not None:
            usage_payload["usage_refresh_cost_usd"] = refresh_cost
            usage_payload["usage"]["refresh_cost_usd"] = refresh_cost
        refresh_model = _claude_refresh_result_model(result_payload)
        if refresh_model is not None:
            usage_payload["usage"]["refresh_model"] = refresh_model
        session_id = _string_or_none(result_payload.get("session_id"))
        if session_id is not None:
            usage_payload["usage"]["refresh_session_id"] = session_id

    return usage_payload


def _claude_refresh_result_model(result_payload: dict[str, Any]) -> str | None:
    model_usage = result_payload.get("modelUsage")
    if isinstance(model_usage, dict) and model_usage:
        for model_name in model_usage:
            if isinstance(model_name, str):
                return model_name
    return None


def _claude_rate_limit_label(rate_limit_type: str | None) -> str:
    if rate_limit_type == "five_hour":
        return "5h"
    if rate_limit_type == "seven_day":
        return "7d"
    if rate_limit_type == "seven_day_opus":
        return "7d Opus"
    if rate_limit_type == "seven_day_sonnet":
        return "7d Sonnet"
    if rate_limit_type == "overage":
        return "extra"
    return rate_limit_type or "usage"


def _claude_rate_limit_duration_mins(rate_limit_type: str | None) -> int | None:
    if rate_limit_type == "five_hour":
        return 300
    if rate_limit_type in {"seven_day", "seven_day_opus", "seven_day_sonnet"}:
        return 10_080
    return None


def _format_limit_summary(limit_payload: dict[str, Any]) -> str:
    label = _string_or_none(limit_payload.get("window_label")) or _string_or_none(limit_payload.get("limit_label"))
    used_percent = limit_payload.get("used_percent")
    if label is not None and isinstance(used_percent, int):
        return f"{label} {used_percent}%"
    if isinstance(used_percent, int):
        return f"{used_percent}% used"
    return label or "usage available"


def _merge_account_payloads(*payloads: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    provider_status: dict[str, Any] = {}
    for payload in payloads:
        raw_provider_status = payload.get("provider_status")
        if isinstance(raw_provider_status, dict):
            provider_status.update(raw_provider_status)
        for key, value in payload.items():
            if key == "provider_status":
                continue
            merged[key] = value

    if provider_status:
        merged["provider_status"] = provider_status

    auth_summary = _string_or_none(merged.get("auth_summary"))
    usage_summary = _string_or_none(merged.get("usage_summary"))
    summary_parts = [part for part in (auth_summary, usage_summary) if part is not None]
    if summary_parts:
        merged["summary"] = "; ".join(summary_parts)
    return merged


def _usage_unavailable_payload(message: str) -> dict[str, Any]:
    return {
        "usage_status": "unavailable",
        "usage_message": message,
    }


def _usage_error_payload(
    *,
    error_type: str,
    message: str,
    exit_code: int | None = None,
) -> dict[str, Any]:
    error_payload: dict[str, object] = {
        "type": error_type,
        "message": message,
    }
    if exit_code is not None:
        error_payload["exit_code"] = exit_code
    return {
        "usage_status": "error",
        "usage_error": error_payload,
    }


def _persist_chat_account_stats_payload(payload: dict[str, object]) -> dict[str, object]:
    history_root = default_chat_account_stats_root()
    tape_root = default_chat_account_stats_tape_root()
    recorded_at = _string_or_none(payload.get("recorded_at")) or _utc_now_iso()
    segment_name = _chat_account_stats_segment_name(recorded_at)
    latest_path = history_root / CHAT_ACCOUNT_STATS_LATEST_FILENAME

    try:
        history_root.mkdir(parents=True, exist_ok=True)
        manifest, tape_created = bootstrap_tara_tape(
            tape_root,
            tape_name=CHAT_ACCOUNT_STATS_TAPE_NAME,
            manifest_extra={
                "record_class": CHAT_ACCOUNT_STATS_RECORD_CLASS,
                "segment_scheme": "YYYYMM",
                "command": "chat accounts stats",
            },
        )
        history_payload = {
            "status": "ok",
            "root": str(history_root),
            "tape_root": str(tape_root),
            "segment_name": segment_name,
            "writer_id": CHAT_ACCOUNT_STATS_TAPE_WRITER_ID,
            "latest_path": str(latest_path),
            "manifest_path": str(tape_root / "tape.json"),
            "tape_created": tape_created,
            "tape_name": _string_or_none(manifest.get("tape_name")),
        }
        persisted_payload = {
            **payload,
            "history": history_payload,
        }
        append_tara_tape_stage_record(
            tape_root,
            writer_id=CHAT_ACCOUNT_STATS_TAPE_WRITER_ID,
            segment_name=segment_name,
            record=persisted_payload,
        )
        commit_tara_tape_stage(tape_root)
        serialized = json.dumps(persisted_payload, indent=2) + "\n"
        latest_path.write_text(serialized, encoding="utf-8")
    except (CliError, OSError) as exc:
        return {
            "status": "error",
            "root": str(history_root),
            "tape_root": str(tape_root),
            "message": str(exc),
        }

    return history_payload


def _chat_account_stats_segment_name(recorded_at: str) -> str:
    try:
        recorded_at_dt = datetime.datetime.fromisoformat(recorded_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CliError(f"recorded_at must be a valid ISO 8601 string: {recorded_at}") from exc
    return recorded_at_dt.strftime("%Y%m") + ".jsonl"


def _ok_account_result(instance: AccountProviderInstance, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": instance.instance_id,
        "label": instance.label,
        "provider": instance.provider,
        "check_status": "ok",
        "cli_command": list(instance.cli_command),
        "timeout_sec": instance.timeout_sec,
        **payload,
    }


def _error_account_result(
    instance: AccountProviderInstance,
    *,
    error_type: str,
    message: str,
    exit_code: int | None = None,
) -> dict[str, Any]:
    error_payload: dict[str, object] = {
        "type": error_type,
        "message": message,
    }
    if exit_code is not None:
        error_payload["exit_code"] = exit_code

    return {
        "id": instance.instance_id,
        "label": instance.label,
        "provider": instance.provider,
        "check_status": "error",
        "cli_command": list(instance.cli_command),
        "timeout_sec": instance.timeout_sec,
        "error": error_payload,
    }


def _load_string_argv(value: object, *, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise CliError(f"{field_name} must be a JSON array")

    argv: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise CliError(f"{field_name}[{index}] must be a non-empty string")
        argv.append(_expand_user_home(item.strip()))
    return tuple(argv)


def _load_string_mapping(value: object, *, field_name: str) -> tuple[tuple[str, str], ...]:
    if value is None:
        return ()
    if not isinstance(value, dict):
        raise CliError(f"{field_name} must be a JSON object")

    items: list[tuple[str, str]] = []
    for key, item in value.items():
        if not isinstance(key, str) or not key:
            raise CliError(f"{field_name} keys must be non-empty strings")
        if not isinstance(item, str):
            raise CliError(f"{field_name}.{key} must be a string")
        items.append((key, _expand_user_home(item)))
    return tuple(items)


def _expand_user_home(value: str) -> str:
    if value.startswith("~"):
        return str(Path(value).expanduser())
    return value


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise CliError("provider status field must be a string when present")
    stripped = value.strip()
    return stripped or None


def _required_int(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CliError(f"{field_name} must be an integer")
    return value


def _optional_int(value: object, *, field_name: str) -> int | None:
    if value is None:
        return None
    return _required_int(value, field_name=field_name)


def _optional_float(value: object, *, field_name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CliError(f"{field_name} must be a number")
    return float(value)


def _optional_bool(value: object, *, field_name: str) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise CliError(f"{field_name} must be a boolean")
    return value


def _parse_iso_datetime_or_none(value: str | None) -> datetime.datetime | None:
    if value is None:
        return None
    try:
        return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _format_display_datetime_local(
    value: str | None,
    *,
    tzinfo: datetime.tzinfo | None = None,
) -> str | None:
    if value is None:
        return None

    parsed = _parse_iso_datetime_or_none(value)
    if parsed is None or parsed.tzinfo is None:
        return value

    local_dt = parsed.astimezone(tz=tzinfo)
    tz_name = local_dt.tzname()
    if tz_name:
        return local_dt.strftime("%Y-%m-%d %H:%M:%S ") + tz_name
    return local_dt.isoformat(timespec="seconds")


def _iso_from_epoch_seconds(epoch_seconds: int | None) -> str | None:
    if epoch_seconds is None:
        return None
    return datetime.datetime.fromtimestamp(epoch_seconds, tz=datetime.timezone.utc).isoformat().replace(
        "+00:00",
        "Z",
    )


def _period_bounds_from_reset(
    *,
    resets_at_epoch: int | None,
    period_duration_mins: int | None,
) -> tuple[str | None, str | None]:
    if resets_at_epoch is None or period_duration_mins is None:
        return (None, None)
    period_started_at_epoch = resets_at_epoch - (period_duration_mins * 60)
    return (
        _iso_from_epoch_seconds(period_started_at_epoch),
        _iso_from_epoch_seconds(resets_at_epoch),
    )


def _utc_now_iso() -> str:
    return datetime.datetime.now(tz=datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _optional_epoch_timestamp(value: object, *, field_name: str) -> str | None:
    epoch_seconds = _optional_int(value, field_name=field_name)
    return _iso_from_epoch_seconds(epoch_seconds)


__all__ = [
    "chat_account_stats",
    "configured_account_provider_instances",
    "format_chat_account_stats_markdown",
    "format_chat_account_stats_usage",
    "supported_account_provider_families",
]
