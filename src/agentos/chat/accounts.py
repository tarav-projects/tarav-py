from __future__ import annotations

import datetime
from http import HTTPStatus
import json
import os
import pty
import re
import select
import subprocess
import tempfile
import textwrap
import time
import urllib.error
import urllib.request
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from agentos._core.errors import CliError
from agentos._core.project import agentos_home_dir
from agentos.chat.providers import (
    ProviderFamily,
    ProviderInstance,
    load_chat_config_documents,
    load_configured_provider_instances,
    require_canonical_provider_family,
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
COPILOT_CLI_PROBE_MODEL = "gpt-4.1"
COPILOT_CLI_PROBE_PROMPT = "Reply with OK only."
COPILOT_USAGE_API_URL = "https://api.github.com/copilot_internal/user"
COPILOT_EDITOR_VERSION = "vscode/1.96.2"
COPILOT_EDITOR_PLUGIN_VERSION = "copilot-chat/0.26.7"
COPILOT_USER_AGENT = "GitHubCopilotChat/0.26.7"
COPILOT_GITHUB_API_VERSION = "2025-04-01"
CHAT_USAGE_BURST_LABEL = "Burst"
CHAT_USAGE_WEEKLY_LABEL = "Weekly"
CHAT_ACCOUNT_USAGE_ERROR_DETAIL_WIDTH = 78
ACCOUNT_STATS_COMMAND_NAME = "agent accounts stats"

_ANSI_CSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_ANSI_OSC_RE = re.compile(r"\x1b\].*?(?:\x07|\x1b\\)", re.DOTALL)
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


@dataclass(frozen=True)
class AccountProviderHandler:
    provider_family: ProviderFamily
    collect_stats: Callable[[AccountProviderContext, bool], dict[str, Any]]

    @property
    def family(self) -> str:
        return self.provider_family.family


@dataclass(frozen=True)
class AccountProviderContext:
    provider_handler: AccountProviderHandler
    provider_instance: ProviderInstance
    cli_command: tuple[str, ...]
    env: tuple[tuple[str, str], ...]
    timeout_sec: int
    live_usage_refresh: bool
    usage_progression_limit: str | None

    @property
    def provider(self) -> str:
        return self.provider_instance.family

    @property
    def instance_id(self) -> str:
        instance_id = self.provider_instance.instance_id
        if instance_id is None:
            raise CliError("account provider instance is missing instance_id")
        return instance_id

    @property
    def label(self) -> str:
        return self.provider_instance.label or self.instance_id

    def env_mapping(self) -> dict[str, str]:
        return dict(self.env)


@dataclass(frozen=True)
class AccountCollectionResult:
    index: int
    provider_name: str
    account_payload: dict[str, Any]


@dataclass(frozen=True)
class AccountUsageTotalConfig:
    label: str
    instance_ids: tuple[str, ...]
    limit_class: str
    limit_name: str


@dataclass(frozen=True)
class UsageOverTimeLimitData:
    used_percent: int | None
    period_started_at: str | None
    period_ends_at: str | None
    period_duration_mins: int | None = None
    resets_at: str | None = None


@dataclass(frozen=True)
class AccountLimit:
    limit_class: str
    limit_name: str
    limit_label: str | None
    usage_over_time: UsageOverTimeLimitData | None = None
    provider_limit: dict[str, Any] | None = None


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


def supported_account_provider_families() -> tuple[AccountProviderHandler, ...]:
    return (
        AccountProviderHandler(
            provider_family=require_canonical_provider_family("codex"),
            collect_stats=_collect_codex_account_stats,
        ),
        AccountProviderHandler(
            provider_family=require_canonical_provider_family("claude-code"),
            collect_stats=_collect_claude_code_account_stats,
        ),
        AccountProviderHandler(
            provider_family=require_canonical_provider_family("copilot-cli"),
            collect_stats=_collect_copilot_account_stats,
        ),
    )


def configured_account_provider_instances(
    *,
    start_path: Path | str = ".",
) -> tuple[ProviderInstance, ...]:
    supported_families = {provider_handler.family for provider_handler in supported_account_provider_families()}
    all_provider_instances = load_configured_provider_instances(start_path=start_path)
    selected_instance_ids = load_agent_accounts_instance_ids(start_path=start_path)
    if selected_instance_ids is None:
        provider_instances = tuple(
            provider_instance
            for provider_instance in all_provider_instances
            if provider_instance.family in supported_families
        )
    else:
        instances_by_id = {
            provider_instance.instance_id: provider_instance
            for provider_instance in all_provider_instances
            if provider_instance.instance_id is not None
        }
        missing_ids = [
            instance_id for instance_id in selected_instance_ids if instance_id not in instances_by_id
        ]
        if missing_ids:
            suffix = "s" if len(missing_ids) != 1 else ""
            raise CliError(
                f"agent.accounts.instance_ids references unknown configured instance id{suffix}: "
                f"{', '.join(missing_ids)}"
            )
        unsupported_ids = [
            instance_id
            for instance_id in selected_instance_ids
            if instances_by_id[instance_id].family not in supported_families
        ]
        if unsupported_ids:
            suffix = "s" if len(unsupported_ids) != 1 else ""
            raise CliError(
                f"agent.accounts.instance_ids references unsupported account instance id{suffix}: "
                f"{', '.join(unsupported_ids)}"
            )
        provider_instances = tuple(instances_by_id[instance_id] for instance_id in selected_instance_ids)
    for provider_instance in provider_instances:
        if _account_provider_requires_cli_command(provider_instance.family) and not provider_instance.cli_command:
            raise CliError(
                f"agent.instances entry {provider_instance.instance_id!r} for provider "
                f"{provider_instance.family} must define cli_command"
            )
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
    payloads = list(
        iter_chat_account_stats_refresh_payloads(
            instance_ids=instance_ids,
            providers=providers,
            refresh_usage=refresh_usage,
            full_output=full_output,
            start_path=start_path,
        )
    )
    if not payloads:
        raise CliError("chat account stats refresh did not produce a payload")
    return payloads[-1]


def iter_chat_account_stats_refresh_payloads(
    *,
    instance_ids: tuple[str, ...] | None = None,
    providers: tuple[str, ...] | None = None,
    refresh_usage: bool = False,
    full_output: bool = False,
    start_path: Path | str = ".",
) -> tuple[dict[str, object], ...]:
    provider_handlers, configured_contexts, provider_handlers_by_name, usage_total_config = _resolve_chat_account_stats_request(
        instance_ids=instance_ids,
        providers=providers,
        start_path=start_path,
    )
    ordered_results: list[AccountCollectionResult | None] = [None] * len(configured_contexts)

    if configured_contexts:
        yield _build_chat_account_stats_payload(
            provider_handlers=provider_handlers,
            configured_contexts=configured_contexts,
            collected_results=ordered_results,
            usage_total_config=usage_total_config,
            refresh_usage=refresh_usage,
            full_output=full_output,
            include_pending=True,
            persist_history=False,
        )

    completed_count = 0
    for collected_result in _iter_account_collection_results(
        configured_contexts=configured_contexts,
        provider_handlers_by_name=provider_handlers_by_name,
        refresh_usage=refresh_usage,
    ):
        ordered_results[collected_result.index] = collected_result
        completed_count += 1
        is_final = completed_count == len(configured_contexts)
        yield _build_chat_account_stats_payload(
            provider_handlers=provider_handlers,
            configured_contexts=configured_contexts,
            collected_results=ordered_results,
            usage_total_config=usage_total_config,
            refresh_usage=refresh_usage,
            full_output=full_output,
            include_pending=not is_final,
            persist_history=is_final,
        )

    if not configured_contexts:
        yield _build_chat_account_stats_payload(
            provider_handlers=provider_handlers,
            configured_contexts=configured_contexts,
            collected_results=ordered_results,
            usage_total_config=usage_total_config,
            refresh_usage=refresh_usage,
            full_output=full_output,
            include_pending=False,
            persist_history=True,
        )


def _resolve_chat_account_stats_request(
    *,
    instance_ids: tuple[str, ...] | None,
    providers: tuple[str, ...] | None,
    start_path: Path | str,
) -> tuple[
    tuple[AccountProviderHandler, ...],
    tuple[AccountProviderContext, ...],
    dict[str, AccountProviderHandler],
    AccountUsageTotalConfig | None,
]:
    provider_handlers = supported_account_provider_families()
    if providers is not None:
        allowed_providers = set(providers)
        provider_handlers = tuple(
            provider_handler
            for provider_handler in provider_handlers
            if provider_handler.family in allowed_providers
        )

    all_configured_contexts = tuple(
        _build_account_provider_context(instance)
        for instance in configured_account_provider_instances(start_path=start_path)
    )
    usage_total_config = load_chat_accounts_usage_total_config(start_path=start_path)
    if usage_total_config is not None:
        available_instance_ids = {context.instance_id for context in all_configured_contexts}
        missing_ids = [
            instance_id for instance_id in usage_total_config.instance_ids if instance_id not in available_instance_ids
        ]
        if missing_ids:
            suffix = "s" if len(missing_ids) != 1 else ""
            raise CliError(
                f"agent.accounts.usage_total.instance_ids references unknown account instance id{suffix}: "
                f"{', '.join(missing_ids)}"
            )

    configured_contexts = all_configured_contexts
    if providers is not None:
        configured_contexts = tuple(
            context
            for context in configured_contexts
            if context.provider in allowed_providers
        )

    if instance_ids:
        requested_ids = set(instance_ids)
        configured_contexts = tuple(
            context
            for context in configured_contexts
            if context.instance_id in requested_ids
        )
        matched_ids = {context.instance_id for context in configured_contexts}
        missing_ids = [instance_id for instance_id in instance_ids if instance_id not in matched_ids]
        if missing_ids:
            suffix = "s" if len(missing_ids) != 1 else ""
            raise CliError(f"unknown account instance id{suffix}: {', '.join(missing_ids)}")

    provider_handlers_by_name = {
        provider_handler.family: provider_handler for provider_handler in provider_handlers
    }
    return provider_handlers, configured_contexts, provider_handlers_by_name, usage_total_config


def _build_chat_account_stats_payload(
    *,
    provider_handlers: tuple[AccountProviderHandler, ...],
    configured_contexts: tuple[AccountProviderContext, ...],
    collected_results: list[AccountCollectionResult | None],
    usage_total_config: AccountUsageTotalConfig | None,
    refresh_usage: bool,
    full_output: bool,
    include_pending: bool,
    persist_history: bool,
) -> dict[str, object]:
    del refresh_usage
    recorded_at = _utc_now_iso()

    provider_payloads: list[dict[str, Any]] = []
    provider_accounts_by_name = {
        provider_handler.family: [] for provider_handler in provider_handlers
    }

    ok_count = 0
    error_count = 0
    pending_count = 0
    account_count = 0

    for index, context in enumerate(configured_contexts):
        collected_result = collected_results[index]
        if collected_result is None:
            if not include_pending:
                continue
            account_payload = _pending_account_result(context)
            provider_name = context.provider
            pending_count += 1
        else:
            account_payload = collected_result.account_payload
            provider_name = collected_result.provider_name
            check_status = _string_or_none(account_payload.get("check_status"))
            if check_status == "ok":
                ok_count += 1
            elif check_status == "error":
                error_count += 1
        provider_accounts_by_name[provider_name].append(account_payload)
        account_count += 1

    for provider_handler in provider_handlers:
        provider_accounts = provider_accounts_by_name[provider_handler.family]
        provider_ok_count = sum(1 for account in provider_accounts if account.get("check_status") == "ok")
        provider_error_count = sum(
            1 for account in provider_accounts if account.get("check_status") == "error"
        )
        provider_payloads.append(
            {
                "provider": provider_handler.family,
                "account_count": len(provider_accounts),
                "ok_count": provider_ok_count,
                "error_count": provider_error_count,
                "accounts": provider_accounts,
            }
        )

    output_providers = (
        provider_payloads
        if full_output
        else [payload for payload in provider_payloads if payload["account_count"] > 0]
    )
    payload: dict[str, object] = {
        "status": "ok",
        "command": ACCOUNT_STATS_COMMAND_NAME,
        "recorded_at": recorded_at,
        "provider_count": len(output_providers),
        "account_count": account_count,
        "ok_count": ok_count,
        "error_count": error_count,
        "providers": output_providers,
    }
    usage_total_payload = _build_chat_accounts_usage_total_payload(
        usage_total_config=usage_total_config,
        configured_contexts=configured_contexts,
        collected_results=collected_results,
        recorded_at=recorded_at,
    )
    if usage_total_payload is not None:
        payload["accounts_usage_total"] = usage_total_payload
    if pending_count > 0:
        payload["pending_count"] = pending_count
        payload["completed_count"] = ok_count + error_count
    if persist_history:
        payload["history"] = _persist_chat_account_stats_payload(payload)
    return payload


def default_chat_account_stats_root() -> Path:
    return agentos_home_dir() / CHAT_ACCOUNT_STATS_DIRNAME


def default_chat_account_stats_tape_root() -> Path:
    return default_chat_account_stats_root() / CHAT_ACCOUNT_STATS_HISTORY_DIRNAME


def _collect_account_results(
    *,
    configured_contexts: tuple[AccountProviderContext, ...],
    provider_handlers_by_name: dict[str, AccountProviderHandler],
    refresh_usage: bool,
) -> list[tuple[str, dict[str, Any]]]:
    ordered_results: list[tuple[str, dict[str, Any]] | None] = [None] * len(configured_contexts)
    for collected_result in _iter_account_collection_results(
        configured_contexts=configured_contexts,
        provider_handlers_by_name=provider_handlers_by_name,
        refresh_usage=refresh_usage,
    ):
        ordered_results[collected_result.index] = (
            collected_result.provider_name,
            collected_result.account_payload,
        )
    return [result for result in ordered_results if result is not None]


def _iter_account_collection_results(
    *,
    configured_contexts: tuple[AccountProviderContext, ...],
    provider_handlers_by_name: dict[str, AccountProviderHandler],
    refresh_usage: bool,
) -> tuple[AccountCollectionResult, ...]:
    if not configured_contexts:
        return

    if len(configured_contexts) == 1:
        context = configured_contexts[0]
        provider_handler = provider_handlers_by_name[context.provider]
        account_payload = provider_handler.collect_stats(context, refresh_usage)
        if not isinstance(account_payload, dict):
            raise CliError("account provider collector must return a JSON object payload")
        yield AccountCollectionResult(
            index=0,
            provider_name=context.provider,
            account_payload=account_payload,
        )
        return

    max_workers = min(MAX_ACCOUNT_COLLECTION_WORKERS, len(configured_contexts))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_lookup: dict[Future[dict[str, Any]], tuple[int, str]] = {}
        for index, context in enumerate(configured_contexts):
            provider_handler = provider_handlers_by_name[context.provider]
            future = executor.submit(provider_handler.collect_stats, context, refresh_usage)
            future_lookup[future] = (index, context.provider)

        for future in as_completed(future_lookup):
            index, provider_name = future_lookup[future]
            account_payload = future.result()
            if not isinstance(account_payload, dict):
                raise CliError("account provider collector must return a JSON object payload")
            yield AccountCollectionResult(
                index=index,
                provider_name=provider_name,
                account_payload=account_payload,
            )


def format_chat_account_stats_markdown(payload: dict[str, object]) -> str:
    lines = [
        "# Agent Accounts Stats",
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
        "# Agent Accounts Usage",
        "",
    ]

    recorded_at = _string_or_none(payload.get("recorded_at"))
    recorded_at_display = _format_display_datetime_local(recorded_at)
    if recorded_at_display is not None:
        lines.append(f"- Recorded at: {recorded_at_display}")
    recorded_at_dt = _parse_iso_datetime_or_none(recorded_at)

    usage_total_payload = payload.get("accounts_usage_total")
    if isinstance(usage_total_payload, dict):
        if len(lines) > 2:
            lines.append("")
        lines.extend(_format_chat_accounts_usage_total_block(usage_total_payload))

    raw_providers = payload.get("providers")
    if not isinstance(raw_providers, list):
        return "\n".join(lines)

    accounts: list[dict[str, Any]] = []
    for provider_payload in raw_providers:
        if not isinstance(provider_payload, dict):
            continue
        raw_accounts = provider_payload.get("accounts")
        if not isinstance(raw_accounts, list):
            continue
        for account in raw_accounts:
            if not isinstance(account, dict):
                continue
            accounts.append(account)

    if accounts:
        accounts.sort(
            key=lambda account: _chat_account_usage_sort_ratio(account, recorded_at=recorded_at_dt),
            reverse=True,
        )

    if not accounts:
        lines.append("- No account instances matched.")
        return "\n".join(lines)

    account_blocks = [_format_chat_account_usage_block(account, recorded_at=recorded_at_dt) for account in accounts]
    if isinstance(usage_total_payload, dict):
        lines.append("")
        lines.append("--------------------------")
    for index, account_block in enumerate(account_blocks):
        if index > 0 or isinstance(usage_total_payload, dict):
            lines.append("")
        lines.extend(account_block)
    return "\n".join(lines)


def load_chat_accounts_usage_total_config(
    *,
    start_path: Path | str = ".",
) -> AccountUsageTotalConfig | None:
    result: AccountUsageTotalConfig | None = None
    accounts_config = _load_agent_accounts_config(start_path=start_path)
    if accounts_config is None:
        return None
    raw_total = accounts_config.get("usage_total")
    if raw_total is None:
        return None
    if not isinstance(raw_total, dict):
        raise CliError("config field agent.accounts.usage_total must be a JSON object")
    result = _account_usage_total_config_from_raw(raw_total)
    return result


def load_agent_accounts_instance_ids(
    *,
    start_path: Path | str = ".",
) -> tuple[str, ...] | None:
    accounts_config = _load_agent_accounts_config(start_path=start_path)
    if accounts_config is None:
        return None
    raw_instance_ids = accounts_config.get("instance_ids")
    if raw_instance_ids is None:
        return None
    if not isinstance(raw_instance_ids, list) or not raw_instance_ids:
        raise CliError("agent.accounts.instance_ids must be a non-empty JSON array")

    instance_ids: list[str] = []
    seen_ids: set[str] = set()
    for index, raw_instance_id in enumerate(raw_instance_ids):
        if not isinstance(raw_instance_id, str) or not raw_instance_id.strip():
            raise CliError(f"agent.accounts.instance_ids[{index}] must be a non-empty string")
        instance_id = raw_instance_id.strip()
        if instance_id in seen_ids:
            raise CliError(
                "agent.accounts.instance_ids must be unique; "
                f"duplicate id {instance_id}"
            )
        seen_ids.add(instance_id)
        instance_ids.append(instance_id)
    return tuple(instance_ids)


def _load_agent_accounts_config(*, start_path: Path | str = ".") -> dict[str, object] | None:
    result: dict[str, object] | None = None
    for config in load_chat_config_documents(start_path=start_path):
        agent_config = config.get("agent")
        if agent_config is None:
            continue
        if not isinstance(agent_config, dict):
            raise CliError("config field agent must be a JSON object")
        raw_accounts = agent_config.get("accounts")
        if raw_accounts is None:
            continue
        if not isinstance(raw_accounts, dict):
            raise CliError("config field agent.accounts must be a JSON object")
        result = raw_accounts
    return result


def _account_usage_total_config_from_raw(raw_total: dict[str, object]) -> AccountUsageTotalConfig:
    raw_label = raw_total.get("label")
    if raw_label is None:
        label = "Selected accounts aggregate"
    elif not isinstance(raw_label, str) or not raw_label.strip():
        raise CliError("agent.accounts.usage_total.label must be a non-empty string")
    else:
        label = raw_label.strip()

    raw_limit_class = raw_total.get("limit_class")
    if not isinstance(raw_limit_class, str) or not raw_limit_class.strip():
        raise CliError("agent.accounts.usage_total.limit_class must be a non-empty string")
    limit_class = raw_limit_class.strip()

    raw_limit_name = raw_total.get("limit_name")
    if not isinstance(raw_limit_name, str) or not raw_limit_name.strip():
        raise CliError("agent.accounts.usage_total.limit_name must be a non-empty string")
    limit_name = raw_limit_name.strip()

    raw_instance_ids = raw_total.get("instance_ids")
    if not isinstance(raw_instance_ids, list) or not raw_instance_ids:
        raise CliError("agent.accounts.usage_total.instance_ids must be a non-empty JSON array")

    instance_ids: list[str] = []
    seen_ids: set[str] = set()
    for index, raw_instance_id in enumerate(raw_instance_ids):
        if not isinstance(raw_instance_id, str) or not raw_instance_id.strip():
            raise CliError(f"agent.accounts.usage_total.instance_ids[{index}] must be a non-empty string")
        instance_id = raw_instance_id.strip()
        if instance_id in seen_ids:
            raise CliError(
                "agent.accounts.usage_total.instance_ids must be unique; "
                f"duplicate id {instance_id}"
            )
        seen_ids.add(instance_id)
        instance_ids.append(instance_id)

    return AccountUsageTotalConfig(
        label=label,
        instance_ids=tuple(instance_ids),
        limit_class=limit_class,
        limit_name=limit_name,
    )


def _account_limit_payload(limit: AccountLimit) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "limit_class": limit.limit_class,
        "limit_name": limit.limit_name,
        "limit_label": limit.limit_label,
    }
    if limit.usage_over_time is not None:
        usage_payload: dict[str, Any] = {
            "used_percent": limit.usage_over_time.used_percent,
            "period_started_at": limit.usage_over_time.period_started_at,
            "period_ends_at": limit.usage_over_time.period_ends_at,
        }
        if limit.usage_over_time.period_duration_mins is not None:
            usage_payload["period_duration_mins"] = limit.usage_over_time.period_duration_mins
        if limit.usage_over_time.resets_at is not None:
            usage_payload["resets_at"] = limit.usage_over_time.resets_at
        payload["usage_over_time"] = usage_payload
    if limit.provider_limit:
        payload["provider_limit"] = limit.provider_limit
    return payload


def _usage_over_time_limit(
    *,
    limit_name: str,
    limit_label: str,
    used_percent: int | None,
    period_started_at: str | None,
    period_ends_at: str | None,
    period_duration_mins: int | None = None,
    resets_at: str | None = None,
    provider_limit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _account_limit_payload(
        AccountLimit(
            limit_class="usage_over_time",
            limit_name=limit_name,
            limit_label=limit_label,
            usage_over_time=UsageOverTimeLimitData(
                used_percent=used_percent,
                period_started_at=period_started_at,
                period_ends_at=period_ends_at,
                period_duration_mins=period_duration_mins,
                resets_at=resets_at,
            ),
            provider_limit=provider_limit,
        )
    )


def _build_chat_accounts_usage_total_payload(
    *,
    usage_total_config: AccountUsageTotalConfig | None,
    configured_contexts: tuple[AccountProviderContext, ...],
    collected_results: list[AccountCollectionResult | None],
    recorded_at: str,
) -> dict[str, Any] | None:
    if usage_total_config is None:
        return None

    accounts_by_id: dict[str, dict[str, Any]] = {}
    for index, context in enumerate(configured_contexts):
        collected_result = collected_results[index]
        if collected_result is None:
            continue
        accounts_by_id[context.instance_id] = collected_result.account_payload

    selected_instance_ids = [
        instance_id for instance_id in usage_total_config.instance_ids if instance_id in accounts_by_id
    ]
    included_instance_ids: list[str] = []
    used_percents: list[int] = []
    elapsed_percents: list[int] = []

    recorded_at_dt = _parse_iso_datetime_or_none(recorded_at)
    for instance_id in selected_instance_ids:
        account_payload = accounts_by_id[instance_id]
        limit_payload = _find_account_limit_payload(
            account_payload,
            limit_class=usage_total_config.limit_class,
            limit_name=usage_total_config.limit_name,
        )
        if limit_payload is None:
            continue
        used_percent = _usage_limit_used_percent(limit_payload)
        elapsed_percent = _format_usage_limit_elapsed_percent(limit_payload, recorded_at=recorded_at_dt)
        if not isinstance(used_percent, int) or elapsed_percent is None:
            continue
        included_instance_ids.append(instance_id)
        used_percents.append(used_percent)
        elapsed_percents.append(elapsed_percent)

    selected_count = len(selected_instance_ids)
    included_count = len(included_instance_ids)
    payload: dict[str, Any] = {
        "label": usage_total_config.label,
        "limit_class": usage_total_config.limit_class,
        "limit_name": usage_total_config.limit_name,
        "configured_instance_ids": list(usage_total_config.instance_ids),
        "selected_instance_ids": selected_instance_ids,
        "selected_count": selected_count,
        "included_instance_ids": included_instance_ids,
        "included_count": included_count,
    }

    if included_count == 0:
        payload["usage_status"] = "unavailable"
        payload["usage_message"] = (
            f"No selected accounts had usable {usage_total_config.limit_name} data."
        )
        return payload

    avg_used_percent = _rounded_percent(sum(used_percents) / included_count)
    avg_elapsed_percent = _rounded_percent(sum(elapsed_percents) / included_count)
    aggregate_payload: dict[str, Any] = {
        "used_percent": avg_used_percent,
        "elapsed_percent": avg_elapsed_percent,
    }
    if avg_elapsed_percent > 0:
        aggregate_payload["ratio"] = _usage_time_ratio_value(avg_used_percent, avg_elapsed_percent)
    payload["usage_status"] = "ok"
    payload["aggregate"] = aggregate_payload
    if included_instance_ids:
        first_limit_payload = _find_account_limit_payload(
            accounts_by_id[included_instance_ids[0]],
            limit_class=usage_total_config.limit_class,
            limit_name=usage_total_config.limit_name,
        )
        if first_limit_payload is not None:
            limit_label = _usage_limit_label(first_limit_payload)
            if limit_label is not None:
                payload["limit_label"] = limit_label
    return payload


def _find_account_limit_payload(
    account_payload: dict[str, Any],
    *,
    limit_class: str,
    limit_name: str,
) -> dict[str, Any] | None:
    usage = account_payload.get("usage")
    if not isinstance(usage, dict):
        return None
    raw_limits = usage.get("limits")
    if not isinstance(raw_limits, list):
        return None
    for raw_limit in raw_limits:
        if not isinstance(raw_limit, dict):
            continue
        if _usage_limit_class(raw_limit) == limit_class and _usage_limit_name(raw_limit) == limit_name:
            return raw_limit
    return None


def _format_chat_accounts_usage_total_block(usage_total_payload: dict[str, Any]) -> list[str]:
    label = _string_or_none(usage_total_payload.get("label")) or "Selected accounts aggregate"
    lines = [f"{label}:"]

    usage_status = _string_or_none(usage_total_payload.get("usage_status"))
    aggregate = usage_total_payload.get("aggregate")
    limit_label = _string_or_none(usage_total_payload.get("limit_label"))
    if usage_status == "ok" and isinstance(aggregate, dict):
        used_percent = _optional_int(aggregate.get("used_percent"), field_name="used_percent")
        elapsed_percent = _optional_int(aggregate.get("elapsed_percent"), field_name="elapsed_percent")
        if used_percent is not None and elapsed_percent is not None:
            line = (
                "usage/time"
                f" | {_format_usage_percent_plain(used_percent)} / {_format_usage_percent_plain(elapsed_percent)}"
                f" = {_format_usage_time_ratio(used_percent, elapsed_percent)}"
            )
            if limit_label is not None:
                line = f"{line} | {limit_label}"
            markers: list[str] = []
            ratio_value = _usage_time_ratio_value(used_percent, elapsed_percent) if elapsed_percent > 0 else None
            ratio_marker = _usage_peak_ratio_marker(ratio_value)
            if ratio_marker is not None:
                markers.append(ratio_marker)
            progression_marker = _usage_progression_marker(used_percent)
            if progression_marker is not None:
                markers.append(progression_marker)
            time_marker = _usage_time_progression_marker(elapsed_percent)
            if time_marker is not None:
                markers.append(time_marker)
            if markers:
                line = f"{line} {' '.join(markers)}"
            lines.append(f"  {line}")
    else:
        lines.append("  usage | unavailable")
        usage_message = _string_or_none(usage_total_payload.get("usage_message"))
        if usage_message is not None:
            lines.append(f"     | {usage_message}")

    included_count = _optional_int(usage_total_payload.get("included_count"), field_name="included_count")
    selected_count = _optional_int(usage_total_payload.get("selected_count"), field_name="selected_count")
    if included_count is not None and selected_count is not None:
        lines.append(f"  coverage | {included_count}/{selected_count} accounts")
    return lines


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

    provider_icon = _chat_account_provider_icon(_string_or_none(account.get("provider")))
    title = f"{display_name}:"
    if provider_icon is not None:
        title = f"{provider_icon} {title}"

    lines = [title]
    usage = account.get("usage")
    if isinstance(usage, dict):
        raw_limits = usage.get("limits")
        if isinstance(raw_limits, list):
            limit_payloads = [limit_payload for limit_payload in raw_limits if isinstance(limit_payload, dict)]
            highlighted_indexes = _chat_account_highlighted_limit_indexes(limit_payloads, recorded_at=recorded_at)
            progression_indexes = _chat_account_progression_limit_indexes(
                account,
                limit_payloads,
                recorded_at=recorded_at,
            )
            formatted_limits = [
                _format_usage_limit_detailed_lines(
                    limit_payload,
                    recorded_at=recorded_at,
                    highlight_peak_ratio=index in highlighted_indexes,
                    show_progression_marker=index in progression_indexes,
                )
                for index, limit_payload in enumerate(limit_payloads)
            ]
            formatted_limits = [item for item in formatted_limits if item is not None]
            if formatted_limits:
                for limit_lines in formatted_limits:
                    lines.extend(f"  {item}" for item in limit_lines)
                return lines

    fallback_lines = _format_chat_account_usage_fallback_lines(account)
    if fallback_lines is not None:
        lines.extend(f"  {item}" for item in fallback_lines)
        return lines

    lines.append(f"  {_format_chat_account_usage_summary(account)}")
    return lines


def _chat_account_provider_icon(provider: str | None) -> str | None:
    if provider == "codex":
        return "⬢"
    if provider == "claude-code":
        return "✺"
    if provider == "copilot-cli":
        return "🤖"
    return None


def _chat_account_usage_sort_ratio(
    account: dict[str, Any],
    *,
    recorded_at: datetime.datetime | None,
) -> float:
    usage = account.get("usage")
    if not isinstance(usage, dict):
        return float("-inf")

    raw_limits = usage.get("limits")
    if not isinstance(raw_limits, list):
        return float("-inf")

    ratios = [
        _usage_limit_time_ratio_value(limit_payload, recorded_at=recorded_at)
        for limit_payload in raw_limits
        if isinstance(limit_payload, dict)
    ]
    ratios = [ratio for ratio in ratios if ratio is not None]
    if not ratios:
        return float("-inf")
    return max(ratios)


def _chat_account_highlighted_limit_indexes(
    limit_payloads: list[dict[str, Any]],
    *,
    recorded_at: datetime.datetime | None,
) -> set[int]:
    indexed_ratios = {
        index: _usage_limit_display_ratio_value(limit_payload, recorded_at=recorded_at)
        for index, limit_payload in enumerate(limit_payloads)
    }
    indexed_ratios = {index: ratio for index, ratio in indexed_ratios.items() if ratio is not None}
    if not indexed_ratios:
        return set()

    max_ratio = max(indexed_ratios.values())
    return {index for index, ratio in indexed_ratios.items() if ratio == max_ratio}


def _chat_account_progression_limit_indexes(
    account: dict[str, Any],
    limit_payloads: list[dict[str, Any]],
    *,
    recorded_at: datetime.datetime | None,
) -> set[int]:
    progression_limit = _string_or_none(account.get("usage_progression_limit"))
    if progression_limit is None:
        return _chat_account_highlighted_limit_indexes(limit_payloads, recorded_at=recorded_at)

    return {
        index
        for index, limit_payload in enumerate(limit_payloads)
        if _usage_limit_label(limit_payload) == progression_limit
    }


def _format_chat_account_usage_fallback_lines(account: dict[str, Any]) -> list[str] | None:
    check_status = _string_or_none(account.get("check_status"))
    account_error = account.get("error")
    usage_status = _string_or_none(account.get("usage_status"))
    usage_message = _string_or_none(account.get("usage_message"))
    usage_error = account.get("usage_error")

    if check_status == "error":
        lines = ["check | error"]
        detail_lines = _format_chat_account_usage_error_detail_lines(account_error)
        if detail_lines is not None:
            lines.extend(f"   | {detail}" for detail in detail_lines)
        return lines

    if check_status == "pending" or usage_status == "pending":
        lines = ["refresh | pending"]
        pending_detail = usage_message or _string_or_none(account.get("summary"))
        if pending_detail is not None:
            lines.extend(f"   | {detail}" for detail in _wrap_chat_account_usage_error_text(pending_detail))
        return lines

    if usage_status == "unavailable":
        lines = ["usage | unavailable"]
        if usage_message is not None:
            lines.append(f"   | {usage_message}")
        return lines

    if usage_status == "error":
        lines = ["usage | error"]
        detail_lines = _format_chat_account_usage_error_detail_lines(usage_error)
        if detail_lines is not None:
            lines.extend(f"   | {detail}" for detail in detail_lines)
        return lines

    return None


def _format_chat_account_usage_error_detail(usage_error: object) -> str | None:
    detail_lines = _format_chat_account_usage_error_detail_lines(usage_error)
    if detail_lines:
        return detail_lines[0]
    return None


def _format_chat_account_usage_error_detail_lines(usage_error: object) -> list[str] | None:
    if not isinstance(usage_error, dict):
        return None

    error_type = _string_or_none(usage_error.get("type"))
    error_message = _string_or_none(usage_error.get("message"))
    detail_lines: list[str] = []
    if error_type is not None and error_message is not None:
        detail_lines.extend(_wrap_chat_account_usage_error_text(f"{error_type}: {error_message}"))
    elif error_message is not None or error_type is not None:
        detail_lines.extend(_wrap_chat_account_usage_error_text(error_message or error_type or ""))

    raw_detail_lines = usage_error.get("detail_lines")
    if isinstance(raw_detail_lines, list):
        for raw_detail in raw_detail_lines:
            if not isinstance(raw_detail, str):
                continue
            detail_lines.extend(_wrap_chat_account_usage_error_text(raw_detail))

    return detail_lines or None


def _wrap_chat_account_usage_error_text(text: str) -> list[str]:
    normalized = " ".join(text.split())
    if not normalized:
        return []
    return textwrap.wrap(
        normalized,
        width=CHAT_ACCOUNT_USAGE_ERROR_DETAIL_WIDTH,
        break_long_words=False,
        break_on_hyphens=False,
    )


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

    check_status = _string_or_none(account.get("check_status"))
    account_error = account.get("error")
    if check_status == "error":
        detail = _format_chat_account_usage_error_detail(account_error)
        if detail is not None:
            return f"Check error: {detail}"
        return "Check error"

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
    label = _usage_limit_label(limit_payload)
    used_percent = _usage_limit_used_percent(limit_payload)
    if label is None and not isinstance(used_percent, int):
        return None
    if isinstance(used_percent, int):
        return f"{label or 'usage'} [{_usage_progress_bar(used_percent)}] {used_percent}%"
    return label


def _usage_limit_class(limit_payload: dict[str, Any]) -> str | None:
    return _string_or_none(limit_payload.get("limit_class"))


def _usage_limit_name(limit_payload: dict[str, Any]) -> str | None:
    return _string_or_none(limit_payload.get("limit_name"))


def _usage_limit_label(limit_payload: dict[str, Any]) -> str | None:
    return _string_or_none(limit_payload.get("limit_label"))


def _usage_limit_usage_over_time_data(limit_payload: dict[str, Any]) -> UsageOverTimeLimitData | None:
    raw_payload = limit_payload.get("usage_over_time")
    if raw_payload is None:
        return None
    if not isinstance(raw_payload, dict):
        raise CliError("usage_over_time limit payload must be an object")
    return UsageOverTimeLimitData(
        used_percent=_optional_int(raw_payload.get("used_percent"), field_name="used_percent"),
        period_started_at=_string_or_none(raw_payload.get("period_started_at")),
        period_ends_at=_string_or_none(raw_payload.get("period_ends_at")),
        period_duration_mins=_optional_int(
            raw_payload.get("period_duration_mins"),
            field_name="period_duration_mins",
        ),
        resets_at=_string_or_none(raw_payload.get("resets_at")),
    )


def _usage_limit_used_percent(limit_payload: dict[str, Any]) -> int | None:
    usage_over_time = _usage_limit_usage_over_time_data(limit_payload)
    if usage_over_time is None:
        return None
    return usage_over_time.used_percent


def _format_usage_limit_used_line(limit_payload: dict[str, Any]) -> str | None:
    label = _usage_limit_label(limit_payload)
    used_percent = _usage_limit_used_percent(limit_payload)
    if label is None and not isinstance(used_percent, int):
        return None
    if isinstance(used_percent, int):
        line = f"used [{_usage_progress_bar(used_percent)}] {_format_usage_percent(used_percent)}"
        if label is not None:
            return f"{line} | {label}"
        return line
    return label


def _format_usage_limit_detailed_lines(
    limit_payload: dict[str, Any],
    *,
    recorded_at: datetime.datetime | None,
    highlight_peak_ratio: bool = False,
    show_progression_marker: bool = False,
) -> list[str] | None:
    usage_time_line = _format_usage_limit_usage_time_line(
        limit_payload,
        recorded_at=recorded_at,
        highlight_peak_ratio=highlight_peak_ratio,
        show_progression_marker=show_progression_marker,
    )
    if usage_time_line is not None:
        lines = [usage_time_line]
    else:
        used_line = _format_usage_limit_used_line(limit_payload)
        if used_line is None:
            return None

        lines = [used_line]
        time_summary = _format_usage_limit_time_summary(limit_payload, recorded_at=recorded_at)
        if time_summary is not None:
            label = _usage_limit_label(limit_payload)
            if label is not None and lines[0].endswith(f" | {label}"):
                lines[0] = f"{lines[0][: -len(f' | {label}')]} | {time_summary} | {label}"
            else:
                lines[0] = f"{lines[0]} | {time_summary}"

    time_meta = _format_usage_limit_time_meta_line(limit_payload, recorded_at=recorded_at)
    if time_meta is not None:
        lines.append(time_meta)
    return lines


def _format_usage_limit_usage_time_line(
    limit_payload: dict[str, Any],
    *,
    recorded_at: datetime.datetime | None,
    highlight_peak_ratio: bool = False,
    show_progression_marker: bool = False,
) -> str | None:
    label = _usage_limit_label(limit_payload)
    used_percent = _usage_limit_used_percent(limit_payload)
    elapsed_percent = _format_usage_limit_elapsed_percent(limit_payload, recorded_at=recorded_at)
    if not isinstance(used_percent, int) or elapsed_percent is None:
        return None

    line = (
        "usage/time"
        f" | {_format_usage_percent_plain(used_percent)} / {_format_usage_percent_plain(elapsed_percent)}"
        f" = {_format_usage_time_ratio(used_percent, elapsed_percent)}"
    )
    if label is not None:
        line = f"{line} | {label}"

    markers: list[str] = []
    ratio_value = _usage_limit_display_ratio_value(limit_payload, recorded_at=recorded_at)
    if highlight_peak_ratio:
        peak_ratio_marker = _usage_peak_ratio_marker(ratio_value)
        if peak_ratio_marker is not None:
            markers.append(peak_ratio_marker)
    progression_marker = _usage_progression_marker(used_percent)
    if progression_marker is not None:
        markers.append(progression_marker)
    time_progression_marker = _usage_time_progression_marker(elapsed_percent)
    if time_progression_marker is not None:
        markers.append(time_progression_marker)
    if markers:
        return f"{line} {' '.join(markers)}"
    return line


def _usage_progression_marker(used_percent: int) -> str | None:
    if used_percent >= 100:
        return "☠️"
    return None


def _usage_peak_ratio_marker(ratio_value: float | None) -> str | None:
    if ratio_value is None or ratio_value <= 0:
        return None
    if ratio_value >= 1.5:
        return "🔥🔥"
    if ratio_value > 1.05:
        return "🔥"
    if ratio_value >= 0.95:
        return None
    if ratio_value >= 0.5:
        return "❄️"
    return "❄️❄️"


def _usage_time_progression_marker(elapsed_percent: int) -> str | None:
    if elapsed_percent > 90:
        return "🕒"
    return None


def _format_usage_limit_time_summary(
    limit_payload: dict[str, Any],
    *,
    recorded_at: datetime.datetime | None,
) -> str | None:
    reset_at = _format_usage_limit_reset_at(limit_payload)
    remaining = _format_usage_limit_remaining(limit_payload, recorded_at=recorded_at)
    elapsed_percent = _format_usage_limit_elapsed_percent(limit_payload, recorded_at=recorded_at)

    if elapsed_percent is not None:
        return f"time [{_usage_progress_bar(elapsed_percent)}] {_format_usage_percent(elapsed_percent)}"
    if reset_at is not None or remaining is not None:
        return "time unavailable"
    return None


def _format_usage_limit_time_meta_line(
    limit_payload: dict[str, Any],
    *,
    recorded_at: datetime.datetime | None,
) -> str | None:
    reset_at = _format_usage_limit_reset_at(limit_payload)
    remaining = _format_usage_limit_remaining(limit_payload, recorded_at=recorded_at)

    if reset_at is None and remaining is None:
        return None

    if reset_at is None:
        return f"    resets | {remaining}"
    if remaining is None:
        return f"    resets | {reset_at}"
    return f"    resets | {reset_at} | {remaining}"


def _format_usage_limit_reset_at(limit_payload: dict[str, Any]) -> str | None:
    usage_over_time = _usage_limit_usage_over_time_data(limit_payload)
    if usage_over_time is None:
        return None

    raw_reset_at = _usage_over_time_reset_at(usage_over_time)
    if raw_reset_at is None:
        return None

    return _format_display_datetime_local_compact(raw_reset_at)


def _format_usage_limit_remaining(
    limit_payload: dict[str, Any],
    *,
    recorded_at: datetime.datetime | None,
) -> str | None:
    if recorded_at is None:
        return None

    usage_over_time = _usage_limit_usage_over_time_data(limit_payload)
    if usage_over_time is None:
        return None

    reset_at = _parse_iso_datetime_or_none(_usage_over_time_reset_at(usage_over_time))
    if reset_at is None:
        return None

    diff_seconds = int((reset_at - recorded_at).total_seconds())
    return _format_remaining_duration(diff_seconds)


def _format_usage_limit_elapsed_percent(
    limit_payload: dict[str, Any],
    *,
    recorded_at: datetime.datetime | None,
) -> int | None:
    if recorded_at is None:
        return None

    period_started_at = _usage_limit_period_started_at(limit_payload)
    period_ends_at = _usage_limit_period_ends_at(limit_payload)
    if period_started_at is None or period_ends_at is None or period_ends_at <= period_started_at:
        return None

    duration_seconds = (period_ends_at - period_started_at).total_seconds()
    if duration_seconds <= 0:
        return None

    elapsed_seconds = (recorded_at - period_started_at).total_seconds()
    elapsed_ratio = max(0.0, min(1.0, elapsed_seconds / duration_seconds))
    return round(elapsed_ratio * 100)


def _usage_limit_period_started_at(limit_payload: dict[str, Any]) -> datetime.datetime | None:
    usage_over_time = _usage_limit_usage_over_time_data(limit_payload)
    if usage_over_time is None:
        return None
    return _usage_over_time_period_started_at(usage_over_time)


def _usage_limit_period_ends_at(limit_payload: dict[str, Any]) -> datetime.datetime | None:
    usage_over_time = _usage_limit_usage_over_time_data(limit_payload)
    if usage_over_time is None:
        return None
    return _usage_over_time_period_ends_at(usage_over_time)


def _usage_over_time_reset_at(usage_over_time: UsageOverTimeLimitData) -> str | None:
    return usage_over_time.resets_at or usage_over_time.period_ends_at


def _usage_over_time_period_started_at(
    usage_over_time: UsageOverTimeLimitData,
) -> datetime.datetime | None:
    period_started_at = _parse_iso_datetime_or_none(usage_over_time.period_started_at)
    if period_started_at is not None:
        return period_started_at
    if usage_over_time.period_duration_mins is None:
        return None
    period_ends_at = _usage_over_time_period_ends_at(usage_over_time)
    if period_ends_at is None:
        return None
    return period_ends_at - datetime.timedelta(minutes=usage_over_time.period_duration_mins)


def _usage_over_time_period_ends_at(
    usage_over_time: UsageOverTimeLimitData,
) -> datetime.datetime | None:
    return _parse_iso_datetime_or_none(usage_over_time.period_ends_at or usage_over_time.resets_at)


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


def _format_usage_percent(value: int) -> str:
    clamped_percent = max(0, min(100, value))
    if clamped_percent < 100:
        return f"{clamped_percent:02d}%"
    return "100%"


def _format_usage_percent_plain(value: int) -> str:
    clamped_percent = max(0, min(100, value))
    return f"{clamped_percent}%".rjust(3)


def _usage_limit_time_ratio_value(
    limit_payload: dict[str, Any],
    *,
    recorded_at: datetime.datetime | None,
) -> float | None:
    used_percent = _usage_limit_used_percent(limit_payload)
    elapsed_percent = _format_usage_limit_elapsed_percent(limit_payload, recorded_at=recorded_at)
    if not isinstance(used_percent, int) or elapsed_percent is None:
        return None
    return _usage_time_ratio_value(used_percent, elapsed_percent)


def _usage_limit_display_ratio_value(
    limit_payload: dict[str, Any],
    *,
    recorded_at: datetime.datetime | None,
) -> float | None:
    used_percent = _usage_limit_used_percent(limit_payload)
    elapsed_percent = _format_usage_limit_elapsed_percent(limit_payload, recorded_at=recorded_at)
    if not isinstance(used_percent, int) or elapsed_percent is None or elapsed_percent <= 0:
        return None
    return _usage_time_ratio_value(used_percent, elapsed_percent)


def _format_usage_time_ratio(used_percent: int, elapsed_percent: int) -> str:
    clamped_elapsed_percent = max(0, min(100, elapsed_percent))
    if clamped_elapsed_percent == 0:
        return "n/a"
    return f"{_usage_time_ratio_value(used_percent, elapsed_percent):.1f}"


def _usage_time_ratio_value(used_percent: int, elapsed_percent: int) -> float:
    clamped_used_percent = max(0, min(100, used_percent))
    clamped_elapsed_percent = max(0, min(100, elapsed_percent))
    if clamped_elapsed_percent == 0:
        if clamped_used_percent == 0:
            return 0.0
        return float("inf")
    return clamped_used_percent / clamped_elapsed_percent


def _validate_unique_account_instance_ids(
    provider_instances: tuple[ProviderInstance, ...],
) -> None:
    seen_instances: dict[str, ProviderInstance] = {}
    for provider_instance in provider_instances:
        if provider_instance.instance_id is None:
            raise CliError("agent.instances ids must not be empty")
        existing = seen_instances.get(provider_instance.instance_id)
        if existing is None:
            seen_instances[provider_instance.instance_id] = provider_instance
            continue
        raise CliError(
            "agent.instances ids must be unique; "
            f"duplicate id {provider_instance.instance_id} for providers "
            f"{existing.family} and {provider_instance.family}"
        )


def _account_provider_requires_cli_command(family_name: str) -> bool:
    return family_name in {"codex", "claude-code"}


def _account_provider_handler_for_name(family_name: str) -> AccountProviderHandler | None:
    for provider_handler in supported_account_provider_families():
        if provider_handler.family == family_name:
            return provider_handler
    return None


def _build_account_provider_context(provider_instance: ProviderInstance) -> AccountProviderContext:
    provider_handler = _account_provider_handler_for_name(provider_instance.family)
    if provider_handler is None:
        raise CliError(f"unsupported account provider family {provider_instance.family}")
    if provider_instance.instance_id is None:
        raise CliError("account provider instance is missing instance_id")

    return AccountProviderContext(
        provider_handler=provider_handler,
        provider_instance=provider_instance,
        cli_command=provider_instance.cli_command,
        env=provider_instance.env,
        timeout_sec=provider_instance.timeout_sec or DEFAULT_ACCOUNT_TIMEOUT_SEC,
        live_usage_refresh=bool(provider_instance.live_usage_refresh),
        usage_progression_limit=provider_instance.usage_progression_limit,
    )


def _collect_copilot_account_stats(
    instance: AccountProviderContext,
    refresh_usage: bool,
) -> dict[str, Any]:
    del refresh_usage

    try:
        auth_payload = _collect_copilot_cli_auth_payload(instance)
    except AccountCommandError as exc:
        return _error_account_result(
            instance,
            error_type=exc.error_type,
            message=exc.message,
            exit_code=exc.exit_code,
        )

    try:
        usage_payload = _collect_copilot_usage_payload(instance)
    except AccountCommandError as exc:
        usage_payload = _usage_error_payload(
            provider=instance.provider,
            error_type=exc.error_type,
            message=exc.message,
            exit_code=exc.exit_code,
        )
    except (CliError, json.JSONDecodeError, TypeError, ValueError) as exc:
        usage_payload = _usage_error_payload(
            provider=instance.provider,
            error_type="invalid_output",
            message=str(exc),
        )

    return _ok_account_result(
        instance,
        _merge_account_payloads(
            auth_payload,
            usage_payload,
        ),
    )


def _collect_copilot_cli_auth_payload(instance: AccountProviderContext) -> dict[str, Any]:
    return _collect_parsed_command_payload(
        instance,
        extra_args=(
            "--model",
            COPILOT_CLI_PROBE_MODEL,
            "-p",
            COPILOT_CLI_PROBE_PROMPT,
            "--allow-all-tools",
            "--no-ask-user",
            "--no-custom-instructions",
            "--no-auto-update",
            "--output-format",
            "json",
            "--stream",
            "off",
        ),
        parser=_parse_copilot_cli_probe_output,
    )


def _collect_copilot_usage_payload(
    instance: AccountProviderContext,
) -> dict[str, Any]:
    return _parse_copilot_usage_response(_read_copilot_account_usage(instance))


def _parse_copilot_cli_probe_output(stdout: str) -> dict[str, Any]:
    model_name: str | None = None
    assistant_message: str | None = None
    result_payload: dict[str, Any] | None = None

    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CliError("copilot CLI probe output must be JSONL") from exc
        if not isinstance(payload, dict):
            raise CliError("copilot CLI probe output lines must be JSON objects")

        event_type = payload.get("type")
        if event_type in {"session.model_change", "session.tools_updated"}:
            data = payload.get("data")
            if isinstance(data, dict):
                model_name = _string_or_none(data.get("newModel")) or _string_or_none(data.get("model"))
            continue

        if event_type == "assistant.message":
            data = payload.get("data")
            if isinstance(data, dict):
                assistant_message = _string_or_none(data.get("content"))
            continue

        if event_type == "result":
            result_payload = payload

    if result_payload is None:
        raise CliError("copilot CLI probe output did not include a result event")

    exit_code = _required_int(result_payload.get("exitCode"), field_name="copilot probe exitCode")
    if exit_code != 0:
        raise CliError(f"copilot CLI probe exited with code {exit_code}")

    session_id = _string_or_none(result_payload.get("sessionId"))
    auth_summary = "Copilot CLI ready"
    if model_name is not None:
        auth_summary = f"{auth_summary} ({model_name})"

    probe_payload: dict[str, Any] = {
        "result": result_payload,
    }
    if session_id is not None:
        probe_payload["session_id"] = session_id
    if model_name is not None:
        probe_payload["model"] = model_name
    if assistant_message is not None:
        probe_payload["assistant_message"] = assistant_message

    return {
        "auth_summary": auth_summary,
        "auth_method": "copilot-cli",
        "logged_in": True,
        "provider_status": {
            "copilot_cli_probe": probe_payload,
        },
    }


def _read_copilot_account_usage(
    instance: AccountProviderContext,
) -> dict[str, Any]:
    token = _read_github_cli_auth_token(instance)
    request = urllib.request.Request(
        COPILOT_USAGE_API_URL,
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/json",
            "Editor-Version": COPILOT_EDITOR_VERSION,
            "Editor-Plugin-Version": COPILOT_EDITOR_PLUGIN_VERSION,
            "User-Agent": COPILOT_USER_AGENT,
            "X-Github-Api-Version": COPILOT_GITHUB_API_VERSION,
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(request, timeout=instance.timeout_sec) as response:
            payload_bytes = response.read()
    except urllib.error.HTTPError as exc:
        raise AccountCommandError(
            error_type="http_error",
            message=_copilot_http_error_message(exc),
            exit_code=exc.code,
        ) from exc
    except urllib.error.URLError as exc:
        reason = exc.reason
        raise AccountCommandError(
            error_type="network_error",
            message=str(reason) if reason is not None else str(exc),
        ) from exc
    except OSError as exc:
        raise AccountCommandError(
            error_type="network_error",
            message=str(exc),
        ) from exc

    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AccountCommandError(
            error_type="invalid_output",
            message=f"copilot usage response was not valid JSON: {exc}",
        ) from exc

    if not isinstance(payload, dict):
        raise CliError("copilot usage response must be a JSON object")
    return payload


def _read_github_cli_auth_token(instance: AccountProviderContext) -> str:
    result = _run_captured_command(
        ["gh", "auth", "token"],
        env=_account_provider_environment(instance),
        timeout_sec=instance.timeout_sec,
    )
    token = _successful_command_output(result).strip()
    if not token:
        raise AccountCommandError(
            error_type="invalid_output",
            message="gh auth token returned no token",
        )
    return token


def _copilot_http_error_message(exc: urllib.error.HTTPError) -> str:
    body = ""
    try:
        body = exc.read().decode("utf-8", errors="replace").strip()
    except OSError:
        body = ""

    if exc.code in {401, 403}:
        return "GitHub token was rejected by the Copilot API"

    if body:
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            message = _string_or_none(payload.get("message"))
            if message is not None:
                return message
        return body

    return f"Copilot API request failed with HTTP {exc.code}"


def _parse_copilot_usage_response(payload: dict[str, Any]) -> dict[str, Any]:
    direct_snapshots = _parse_copilot_quota_snapshots(payload.get("quota_snapshots"))
    monthly_snapshots = _copilot_monthly_quota_snapshots(payload)
    period_started_at, period_ends_at, period_duration_mins = _copilot_monthly_period_bounds(payload)

    premium_snapshot = _usable_copilot_quota_snapshot(direct_snapshots["premium_interactions"]) or (
        _usable_copilot_quota_snapshot(monthly_snapshots["premium_interactions"])
    )
    chat_snapshot = _usable_copilot_quota_snapshot(direct_snapshots["chat"]) or (
        _usable_copilot_quota_snapshot(monthly_snapshots["chat"])
    )

    limits: list[dict[str, Any]] = []
    chat_limit = _copilot_limit_from_snapshot(
        chat_snapshot,
        name="chat",
        label="Chat",
        period_started_at=period_started_at,
        period_ends_at=period_ends_at,
        period_duration_mins=period_duration_mins,
    )
    if chat_limit is not None:
        limits.append(chat_limit)
    premium_limit = _copilot_limit_from_snapshot(
        premium_snapshot,
        name="premium",
        label="Premium",
        period_started_at=period_started_at,
        period_ends_at=period_ends_at,
        period_duration_mins=period_duration_mins,
    )
    if premium_limit is not None:
        limits.append(premium_limit)

    if not limits:
        raise CliError("copilot usage response did not contain any usable quota snapshots")

    payload_data: dict[str, Any] = {
        "usage_status": "ok",
        "usage_source": "copilot-api",
        "usage_summary": ", ".join(_format_limit_summary(limit_payload) for limit_payload in limits) or None,
        "usage": {
            "kind": "copilot_quota",
            "limits": limits,
        },
        "provider_status": {
            "copilot_usage": payload,
        },
    }
    plan = _string_or_none(payload.get("copilot_plan"))
    if plan is not None:
        payload_data["plan"] = plan
    login = _string_or_none(payload.get("login"))
    if login is not None:
        payload_data["account_login"] = login
    return payload_data


def _parse_copilot_quota_snapshots(value: object) -> dict[str, dict[str, Any] | None]:
    if value is None:
        return {
            "premium_interactions": None,
            "chat": None,
        }
    if not isinstance(value, dict):
        raise CliError("copilot quota_snapshots must be an object")

    premium = _parse_copilot_quota_snapshot(
        value.get("premium_interactions"),
        field_name="copilot quota_snapshots.premium_interactions",
    )
    chat = _parse_copilot_quota_snapshot(
        value.get("chat"),
        field_name="copilot quota_snapshots.chat",
    )

    if premium is None or chat is None:
        fallback_premium: dict[str, Any] | None = None
        fallback_chat: dict[str, Any] | None = None
        first_usable: dict[str, Any] | None = None

        for key, item in value.items():
            if not isinstance(key, str):
                continue
            snapshot = _parse_copilot_quota_snapshot(
                item,
                field_name=f"copilot quota_snapshots.{key}",
            )
            if snapshot is None:
                continue

            if first_usable is None:
                first_usable = snapshot

            normalized_key = key.lower()
            if fallback_chat is None and "chat" in normalized_key:
                fallback_chat = snapshot
                continue
            if fallback_premium is None and (
                "premium" in normalized_key or "completion" in normalized_key or "code" in normalized_key
            ):
                fallback_premium = snapshot

        if premium is None:
            premium = fallback_premium
        if chat is None:
            chat = fallback_chat
        if premium is None and chat is None:
            chat = first_usable

    return {
        "premium_interactions": premium,
        "chat": chat,
    }


def _parse_copilot_quota_snapshot(
    value: object,
    *,
    field_name: str,
) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise CliError(f"{field_name} must be an object")

    entitlement = _optional_number_like(value.get("entitlement"), field_name=f"{field_name}.entitlement")
    remaining = _optional_number_like(value.get("remaining"), field_name=f"{field_name}.remaining")
    raw_percent_remaining = _optional_number_like(
        value.get("percent_remaining"),
        field_name=f"{field_name}.percent_remaining",
    )

    has_percent_remaining = False
    percent_remaining = 0.0
    if raw_percent_remaining is not None:
        has_percent_remaining = True
        percent_remaining = max(0.0, min(100.0, raw_percent_remaining))
    elif entitlement is not None and entitlement > 0 and remaining is not None:
        has_percent_remaining = True
        percent_remaining = max(0.0, min(100.0, (remaining / entitlement) * 100))

    snapshot = {
        "entitlement": entitlement if entitlement is not None else 0.0,
        "remaining": remaining if remaining is not None else 0.0,
        "percent_remaining": percent_remaining,
        "quota_id": _string_or_none(value.get("quota_id")) or "",
        "has_percent_remaining": has_percent_remaining,
    }
    if _copilot_quota_snapshot_is_placeholder(snapshot):
        return None
    return snapshot


def _copilot_monthly_quota_snapshots(payload: dict[str, Any]) -> dict[str, dict[str, Any] | None]:
    monthly_quotas = _parse_copilot_quota_counts(payload.get("monthly_quotas"), field_name="copilot monthly_quotas")
    limited_user_quotas = _parse_copilot_quota_counts(
        payload.get("limited_user_quotas"),
        field_name="copilot limited_user_quotas",
    )
    return {
        "premium_interactions": _copilot_quota_snapshot_from_monthly(
            monthly=monthly_quotas["completions"],
            limited=limited_user_quotas["completions"],
            quota_id="completions",
        ),
        "chat": _copilot_quota_snapshot_from_monthly(
            monthly=monthly_quotas["chat"],
            limited=limited_user_quotas["chat"],
            quota_id="chat",
        ),
    }


def _parse_copilot_quota_counts(
    value: object,
    *,
    field_name: str,
) -> dict[str, float | None]:
    if value is None:
        return {
            "chat": None,
            "completions": None,
        }
    if not isinstance(value, dict):
        raise CliError(f"{field_name} must be an object")

    return {
        "chat": _optional_number_like(value.get("chat"), field_name=f"{field_name}.chat"),
        "completions": _optional_number_like(value.get("completions"), field_name=f"{field_name}.completions"),
    }


def _copilot_quota_snapshot_from_monthly(
    *,
    monthly: float | None,
    limited: float | None,
    quota_id: str,
) -> dict[str, Any] | None:
    if monthly is None and limited is None:
        return None
    if monthly is None or limited is None:
        return None

    entitlement = max(0.0, monthly)
    if entitlement <= 0:
        return None

    remaining = max(0.0, limited)
    return {
        "entitlement": entitlement,
        "remaining": remaining,
        "percent_remaining": max(0.0, min(100.0, (remaining / entitlement) * 100)),
        "quota_id": quota_id,
        "has_percent_remaining": True,
    }


def _usable_copilot_quota_snapshot(snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
    if snapshot is None:
        return None
    if not snapshot.get("has_percent_remaining"):
        return None
    if _copilot_quota_snapshot_is_placeholder(snapshot):
        return None
    return snapshot


def _copilot_quota_snapshot_is_placeholder(snapshot: dict[str, Any]) -> bool:
    return (
        snapshot.get("entitlement") == 0
        and snapshot.get("remaining") == 0
        and snapshot.get("percent_remaining") == 0
        and snapshot.get("quota_id") == ""
    )


def _copilot_limit_from_snapshot(
    snapshot: dict[str, Any] | None,
    *,
    name: str,
    label: str,
    period_started_at: str | None = None,
    period_ends_at: str | None = None,
    period_duration_mins: int | None = None,
) -> dict[str, Any] | None:
    if snapshot is None:
        return None

    percent_remaining = _optional_float(
        snapshot.get("percent_remaining"),
        field_name="copilot percent_remaining",
    )
    if percent_remaining is None:
        return None

    return _usage_over_time_limit(
        limit_name=name,
        limit_label=label,
        used_percent=_rounded_percent(100 - percent_remaining),
        period_started_at=period_started_at,
        period_ends_at=period_ends_at,
        period_duration_mins=period_duration_mins,
    )


def _copilot_monthly_period_bounds(payload: dict[str, Any]) -> tuple[str | None, str | None, int | None]:
    period_ends_at = _copilot_quota_reset_at(payload)
    if period_ends_at is None:
        return (None, None, None)

    period_ends_at_dt = _parse_iso_datetime_or_none(period_ends_at)
    if period_ends_at_dt is None or period_ends_at_dt.tzinfo is None:
        return (None, period_ends_at, None)

    period_started_at_dt = _previous_month_same_instant(period_ends_at_dt)
    period_duration_mins = int((period_ends_at_dt - period_started_at_dt).total_seconds() // 60)
    return (
        _iso_from_datetime(period_started_at_dt),
        _iso_from_datetime(period_ends_at_dt),
        period_duration_mins,
    )


def _copilot_quota_reset_at(payload: dict[str, Any]) -> str | None:
    raw_reset_at = _string_or_none(payload.get("quota_reset_date_utc"))
    if raw_reset_at is not None:
        reset_at = _parse_iso_datetime_or_none(raw_reset_at)
        if reset_at is None:
            return raw_reset_at
        return _iso_from_datetime(reset_at)

    raw_reset_date = _string_or_none(payload.get("quota_reset_date"))
    if raw_reset_date is None:
        return None
    try:
        reset_date = datetime.date.fromisoformat(raw_reset_date)
    except ValueError:
        return raw_reset_date
    reset_at = datetime.datetime.combine(reset_date, datetime.time.min, tzinfo=datetime.timezone.utc)
    return _iso_from_datetime(reset_at)


def _previous_month_same_instant(value: datetime.datetime) -> datetime.datetime:
    year = value.year
    month = value.month - 1
    if month == 0:
        year -= 1
        month = 12

    if month == 12:
        next_month_year = year + 1
        next_month = 1
    else:
        next_month_year = year
        next_month = month + 1
    last_day = (datetime.date(next_month_year, next_month, 1) - datetime.timedelta(days=1)).day
    day = min(value.day, last_day)
    return value.replace(year=year, month=month, day=day)


def _collect_codex_account_stats(
    instance: AccountProviderContext,
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
            provider=instance.provider,
            error_type=exc.error_type,
            message=exc.message,
            exit_code=exc.exit_code,
        )
    except (CliError, json.JSONDecodeError, TypeError, ValueError) as exc:
        usage_payload = _usage_error_payload(
            provider=instance.provider,
            error_type="invalid_output",
            message=str(exc),
        )

    return _ok_account_result(
        instance,
        _merge_account_payloads(auth_payload, usage_payload),
    )


def _collect_codex_usage_payload(instance: AccountProviderContext) -> dict[str, Any]:
    return _parse_codex_rate_limits(_read_codex_account_rate_limits(instance))


def _collect_claude_code_account_stats(
    instance: AccountProviderContext,
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
                    provider=instance.provider,
                    error_type=exc.error_type,
                    message=exc.message,
                    exit_code=exc.exit_code,
                )
            except (CliError, json.JSONDecodeError, TypeError, ValueError) as exc:
                usage_payload = _usage_error_payload(
                    provider=instance.provider,
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
    instance: AccountProviderContext,
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
    instance: AccountProviderContext,
    *,
    extra_args: tuple[str, ...],
    cwd: str | None = None,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    command = [*instance.cli_command, *extra_args]
    env = _account_provider_environment(instance)
    if extra_env is not None:
        env.update(extra_env)

    return _run_captured_command(
        command,
        env=env,
        timeout_sec=instance.timeout_sec,
        cwd=cwd,
    )


def _run_captured_command(
    command: list[str],
    *,
    env: dict[str, str],
    timeout_sec: int,
    cwd: str | None = None,
) -> subprocess.CompletedProcess[str]:
    run_kwargs: dict[str, Any] = {
        "capture_output": True,
        "text": True,
        "check": False,
        "env": env,
        "timeout": timeout_sec,
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
            message=f"provider command timed out after {timeout_sec} seconds",
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


def _read_codex_account_rate_limits(instance: AccountProviderContext) -> dict[str, Any]:
    command = [*instance.cli_command, "app-server"]
    env = _account_provider_environment(instance)

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
            _usage_over_time_limit(
                limit_name=_codex_window_name(window_duration_mins, window_key=window_key),
                limit_label=_codex_window_label(window_duration_mins, window_key=window_key),
                used_percent=used_percent,
                period_started_at=period_started_at,
                period_ends_at=period_ends_at,
                period_duration_mins=window_duration_mins,
                resets_at=_iso_from_epoch_seconds(resets_at_epoch),
                provider_limit={
                    "limit_id": limit_id,
                    "window_key": window_key,
                    "window_duration_mins": window_duration_mins,
                },
            )
        )
    return limits


def _codex_window_name(window_duration_mins: int | None, *, window_key: str) -> str:
    if window_duration_mins == 300:
        return "burst"
    if window_duration_mins == 1_440:
        return "daily"
    if window_duration_mins == 10_080:
        return "weekly"
    if window_duration_mins is not None:
        return f"{window_duration_mins}m"
    return window_key


def _codex_window_label(window_duration_mins: int | None, *, window_key: str) -> str:
    if window_duration_mins == 300:
        return CHAT_USAGE_BURST_LABEL
    if window_duration_mins == 1_440:
        return "24h"
    if window_duration_mins == 10_080:
        return CHAT_USAGE_WEEKLY_LABEL
    if window_duration_mins is not None:
        return f"{window_duration_mins}m"
    return window_key


def _collect_claude_code_live_usage(instance: AccountProviderContext) -> dict[str, Any]:
    try:
        return _collect_claude_code_live_usage_from_statusline(instance)
    except (AccountCommandError, CliError, json.JSONDecodeError, TypeError, ValueError):
        return _collect_claude_code_live_usage_from_stream_json(instance)


def _collect_claude_code_live_usage_from_statusline(
    instance: AccountProviderContext,
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
    instance: AccountProviderContext,
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
    instance: AccountProviderContext,
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
    env = _account_provider_environment(instance)
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
            if process.poll() is None:
                try:
                    process.kill()
                except OSError:
                    pass
            try:
                process.wait(timeout=CLAUDE_REFRESH_TERMINATE_WAIT_SEC)
            except subprocess.TimeoutExpired:
                pass
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


def _claude_code_refresh_workspace_root(instance: AccountProviderContext) -> Path:
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
            _usage_over_time_limit(
                limit_name=_claude_rate_limit_name(limit_type),
                limit_label=_claude_rate_limit_label(limit_type),
                used_percent=used_percent,
                period_started_at=period_started_at,
                period_ends_at=period_ends_at,
                period_duration_mins=period_duration_mins,
                resets_at=_iso_from_epoch_seconds(resets_at_epoch),
                provider_limit={
                    "limit_type": limit_type,
                },
            )
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
    limit_payload = _usage_over_time_limit(
        limit_name=_claude_rate_limit_name(rate_limit_type),
        limit_label=_claude_rate_limit_label(rate_limit_type),
        used_percent=used_percent,
        period_started_at=period_started_at,
        period_ends_at=period_ends_at,
        period_duration_mins=period_duration_mins,
        resets_at=_iso_from_epoch_seconds(resets_at_epoch),
        provider_limit={
            "limit_type": rate_limit_type,
            "status": _string_or_none(rate_limit_info.get("status")),
            "is_using_overage": _optional_bool(
                rate_limit_info.get("isUsingOverage"),
                field_name="claude isUsingOverage",
            ),
            "surpassed_threshold": _optional_float(
                rate_limit_info.get("surpassedThreshold"),
                field_name="claude surpassedThreshold",
            ),
        },
    )

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
        return CHAT_USAGE_BURST_LABEL
    if rate_limit_type == "seven_day":
        return CHAT_USAGE_WEEKLY_LABEL
    if rate_limit_type == "seven_day_opus":
        return f"{CHAT_USAGE_WEEKLY_LABEL} Opus"
    if rate_limit_type == "seven_day_sonnet":
        return f"{CHAT_USAGE_WEEKLY_LABEL} Sonnet"
    if rate_limit_type == "overage":
        return "extra"
    return rate_limit_type or "usage"


def _claude_rate_limit_name(rate_limit_type: str | None) -> str:
    if rate_limit_type == "five_hour":
        return "burst"
    if rate_limit_type == "seven_day":
        return "weekly"
    if rate_limit_type == "seven_day_opus":
        return "weekly_opus"
    if rate_limit_type == "seven_day_sonnet":
        return "weekly_sonnet"
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
    label = _usage_limit_label(limit_payload)
    used_percent = _usage_limit_used_percent(limit_payload)
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
    provider: str | None,
    error_type: str,
    message: str,
    exit_code: int | None = None,
) -> dict[str, Any]:
    return {
        "usage_status": "error",
        "usage_error": _build_account_error_payload(
            provider=provider,
            error_type=error_type,
            message=message,
            exit_code=exit_code,
        ),
    }


def _build_account_error_payload(
    *,
    provider: str | None,
    error_type: str,
    message: str,
    exit_code: int | None = None,
) -> dict[str, object]:
    normalized_message = message
    extra_payload: dict[str, object] = {}

    if provider == "codex":
        normalized_codex_error = _normalize_codex_usage_error_message(message)
        if normalized_codex_error is not None:
            normalized_message = normalized_codex_error["message"]
            extra_payload.update(
                {
                    key: value
                    for key, value in normalized_codex_error.items()
                    if key != "message"
                }
            )
    if provider == "claude-code":
        normalized_claude_error = _normalize_claude_usage_error_message(message)
        if normalized_claude_error is not None:
            normalized_message = normalized_claude_error["message"]
            extra_payload.update(
                {
                    key: value
                    for key, value in normalized_claude_error.items()
                    if key != "message"
                }
            )

    error_payload: dict[str, object] = {
        "type": error_type,
        "message": normalized_message,
    }
    if exit_code is not None:
        error_payload["exit_code"] = exit_code
    error_payload.update(extra_payload)
    return error_payload


def _normalize_codex_usage_error_message(message: str) -> dict[str, object] | None:
    if "failed to fetch codex rate limits" not in message:
        return None

    http_status, http_reason = _parse_http_status_from_message(message)
    body_payload = _parse_json_object_suffix(message, marker="body=")
    api_error = body_payload.get("error") if isinstance(body_payload, dict) else None

    api_message = None
    api_code = None
    if isinstance(api_error, dict):
        api_message = _string_or_none(api_error.get("message"))
        api_code = _string_or_none(api_error.get("code"))

    if http_status is None and isinstance(body_payload, dict):
        raw_status = body_payload.get("status")
        if isinstance(raw_status, int):
            http_status = raw_status

    status_summary = _format_http_status_summary(http_status, http_reason)
    detail_lines: list[str] = []
    if status_summary is not None or api_code is not None:
        status_parts = [part for part in (status_summary, api_code) if part]
        if status_parts:
            detail_lines.append(" | ".join(status_parts))

    if http_status == 401 and api_code == "token_expired":
        if api_message is not None:
            detail_lines.append(api_message)
        detail_lines.append("Sign in again with the configured Codex CLI and refresh.")
        return {
            "message": "Codex authentication token expired",
            "raw_message": message,
            "detail_lines": detail_lines,
            "http_status": http_status,
            "code": api_code,
        }

    if api_message is None and status_summary is None:
        return None

    if api_message is not None and api_message != message:
        return {
            "message": api_message,
            "raw_message": message,
            "detail_lines": detail_lines,
            "http_status": http_status,
            "code": api_code,
        }

    if status_summary is not None:
        return {
            "message": f"Codex rate-limit request failed with {status_summary}",
            "raw_message": message,
            "detail_lines": detail_lines,
            "http_status": http_status,
            "code": api_code,
        }

    return None


def _normalize_claude_usage_error_message(message: str) -> dict[str, object] | None:
    parsed_events = _parse_json_object_lines(message)
    top_level_error: str | None = None
    candidate_texts: list[str] = []

    for event in parsed_events:
        event_error = _string_or_none(event.get("error"))
        if top_level_error is None and event_error is not None:
            top_level_error = event_error
        candidate_texts.extend(_claude_error_text_candidates_from_event(event))

    raw_text = next((text for text in reversed(candidate_texts) if text.strip()), None) or message
    normalized_text = " ".join(raw_text.split())
    http_status, api_code, api_message = _parse_claude_api_error_text(raw_text)
    auth_failed = (
        (top_level_error == "authentication_failed")
        or ("failed to authenticate" in raw_text.lower())
    )

    detail_lines: list[str] = []
    status_summary = _format_http_status_summary(http_status, _http_status_reason_phrase(http_status))
    status_parts = [part for part in (status_summary, top_level_error, api_code) if part]
    if status_parts:
        detail_lines.append(" | ".join(status_parts))
    if api_message is not None:
        detail_lines.append(api_message)

    if auth_failed:
        detail_lines.append("Sign in again with the configured Claude Code CLI and refresh.")
        return {
            "message": "Claude Code authentication failed",
            "raw_message": message,
            "detail_lines": detail_lines,
            "http_status": http_status,
            "code": top_level_error or api_code,
            "api_code": api_code,
        }

    compact_text = _compact_claude_error_text(normalized_text)
    if compact_text is not None and compact_text != message:
        return {
            "message": compact_text,
            "raw_message": message,
            "detail_lines": detail_lines,
            "http_status": http_status,
            "code": top_level_error or api_code,
            "api_code": api_code,
        }

    return None


def _parse_json_object_lines(text: str) -> list[dict[str, Any]]:
    parsed_objects: list[dict[str, Any]] = []
    saw_content = False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        saw_content = True
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return []
        if not isinstance(parsed, dict):
            return []
        parsed_objects.append(parsed)
    if not saw_content:
        return []
    return parsed_objects


def _claude_error_text_candidates_from_event(event: dict[str, Any]) -> list[str]:
    candidates: list[str] = []

    result_text = _string_or_none(event.get("result"))
    if result_text is not None:
        candidates.append(result_text)

    message_payload = event.get("message")
    if isinstance(message_payload, dict):
        content_payload = message_payload.get("content")
        if isinstance(content_payload, list):
            for item in content_payload:
                if not isinstance(item, dict):
                    continue
                text = _string_or_none(item.get("text"))
                if text is not None:
                    candidates.append(text)

    return candidates


def _parse_claude_api_error_text(text: str) -> tuple[int | None, str | None, str | None]:
    status_match = re.search(r"\bapi error:\s*(?P<status>\d{3})\b", text, re.IGNORECASE)
    http_status = int(status_match.group("status")) if status_match is not None else None

    payload = _parse_json_object_from_text(text)
    api_code = None
    api_message = None
    if isinstance(payload, dict):
        api_error = payload.get("error")
        if isinstance(api_error, dict):
            api_code = _string_or_none(api_error.get("type"))
            api_message = _string_or_none(api_error.get("message"))

    return http_status, api_code, api_message


def _compact_claude_error_text(text: str) -> str | None:
    normalized = text.strip()
    if not normalized:
        return None

    api_error_index = normalized.lower().find("api error:")
    if api_error_index > 0:
        normalized = normalized[:api_error_index].strip()

    if "\n" in normalized:
        normalized = normalized.splitlines()[0].strip()
    if not normalized:
        return None
    return normalized


def _parse_http_status_from_message(message: str) -> tuple[int | None, str | None]:
    match = re.search(r"\bfailed:\s*(?P<status>\d{3}) (?P<reason>[^;]+)", message)
    if match is None:
        return None, None
    status = int(match.group("status"))
    reason = match.group("reason").strip()
    return status, reason or None


def _format_http_status_summary(status: int | None, reason: str | None) -> str | None:
    if status is None and reason is None:
        return None
    if status is None:
        return reason
    if reason is None:
        return f"HTTP {status}"
    return f"{status} {reason}"


def _http_status_reason_phrase(status: int | None) -> str | None:
    if status is None:
        return None
    try:
        return HTTPStatus(status).phrase
    except ValueError:
        return None


def _parse_json_object_suffix(message: str, *, marker: str) -> dict[str, Any] | None:
    marker_index = message.find(marker)
    if marker_index < 0:
        return None

    suffix = message[marker_index + len(marker):].strip()
    if not suffix.startswith("{"):
        return None

    try:
        payload = json.loads(suffix)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _parse_json_object_from_text(text: str) -> dict[str, Any] | None:
    start_index = text.find("{")
    if start_index < 0:
        return None

    candidate = text[start_index:].strip()
    if not candidate.startswith("{"):
        return None

    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


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
                "command": ACCOUNT_STATS_COMMAND_NAME,
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


def _ok_account_result(instance: AccountProviderContext, payload: dict[str, Any]) -> dict[str, Any]:
    result = {
        "id": instance.instance_id,
        "label": instance.label,
        "provider": instance.provider,
        "check_status": "ok",
        "cli_command": list(instance.cli_command),
        "timeout_sec": instance.timeout_sec,
        **payload,
    }
    if instance.usage_progression_limit is not None:
        result["usage_progression_limit"] = instance.usage_progression_limit
    return result


def _error_account_result(
    instance: AccountProviderContext,
    *,
    error_type: str,
    message: str,
    exit_code: int | None = None,
) -> dict[str, Any]:
    result = {
        "id": instance.instance_id,
        "label": instance.label,
        "provider": instance.provider,
        "check_status": "error",
        "cli_command": list(instance.cli_command),
        "timeout_sec": instance.timeout_sec,
        "error": _build_account_error_payload(
            provider=instance.provider,
            error_type=error_type,
            message=message,
            exit_code=exit_code,
        ),
    }
    if instance.usage_progression_limit is not None:
        result["usage_progression_limit"] = instance.usage_progression_limit
    return result


def _pending_account_result(instance: AccountProviderContext) -> dict[str, Any]:
    result = {
        "id": instance.instance_id,
        "label": instance.label,
        "provider": instance.provider,
        "check_status": "pending",
        "cli_command": list(instance.cli_command),
        "timeout_sec": instance.timeout_sec,
        "summary": "Refreshing account status...",
        "usage_status": "pending",
        "usage_message": "Waiting for provider response.",
    }
    if instance.usage_progression_limit is not None:
        result["usage_progression_limit"] = instance.usage_progression_limit
    return result

def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise CliError("provider status field must be a string when present")
    stripped = value.strip()
    return stripped or None


def _optional_number_like(value: object, *, field_name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise CliError(f"{field_name} must be a number")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return float(stripped)
        except ValueError as exc:
            raise CliError(f"{field_name} must be a number") from exc
    raise CliError(f"{field_name} must be a number")


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


def _format_display_datetime_local_compact(
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
    return local_dt.strftime("%a %m-%d %H:%M")


def _iso_from_epoch_seconds(epoch_seconds: int | None) -> str | None:
    if epoch_seconds is None:
        return None
    return datetime.datetime.fromtimestamp(epoch_seconds, tz=datetime.timezone.utc).isoformat().replace(
        "+00:00",
        "Z",
    )


def _iso_from_datetime(value: datetime.datetime) -> str:
    if value.tzinfo is None:
        return value.isoformat(timespec="seconds")
    return value.astimezone(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


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


def _account_provider_environment(instance: AccountProviderContext) -> dict[str, str]:
    env = os.environ.copy()
    env.update(instance.env_mapping())
    return env


def _rounded_percent(value: float) -> int:
    clamped = max(0.0, min(100.0, value))
    return int(clamped + 0.5)


__all__ = [
    "chat_account_stats",
    "configured_account_provider_instances",
    "format_chat_account_stats_markdown",
    "format_chat_account_stats_usage",
    "iter_chat_account_stats_refresh_payloads",
    "load_agent_accounts_instance_ids",
    "supported_account_provider_families",
]
