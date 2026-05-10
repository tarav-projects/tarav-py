from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from agentos._core.errors import CliError
from agentos.agent.account_runtime import (
    AccountCommandError,
    AccountStatsRequest,
    account_provider_environment,
    account_timeout_sec,
    collect_parsed_command_payload,
    run_captured_command,
    successful_command_output,
)
from agentos.agent.primitives import Agent
from agentos.agent.accounts import (
    _merge_account_payloads,
    _parse_copilot_cli_probe_output,
    _parse_copilot_usage_response,
    _usage_error_payload,
)


COPILOT_CLI_PROBE_MODEL = "gpt-4.1"
COPILOT_CLI_PROBE_PROMPT = "Reply with OK only."
COPILOT_USAGE_API_URL = "https://api.github.com/copilot_internal/user"
COPILOT_EDITOR_VERSION = "vscode/1.96.2"
COPILOT_EDITOR_PLUGIN_VERSION = "copilot-chat/0.26.7"
COPILOT_USER_AGENT = "GitHubCopilotChat/0.26.7"
COPILOT_GITHUB_API_VERSION = "2025-04-01"


def collect_copilot_account_stats(agent: Agent, request: AccountStatsRequest) -> dict[str, Any]:
    del request

    auth_payload = collect_parsed_command_payload(
        agent,
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

    try:
        usage_payload = _parse_copilot_usage_response(_read_copilot_account_usage(agent))
    except AccountCommandError as exc:
        usage_payload = _usage_error_payload(
            provider=agent.provider,
            error_type=exc.error_type,
            message=exc.message,
            exit_code=exc.exit_code,
        )
    except (CliError, json.JSONDecodeError, TypeError, ValueError) as exc:
        usage_payload = _usage_error_payload(
            provider=agent.provider,
            error_type="invalid_output",
            message=str(exc),
        )

    return _merge_account_payloads(auth_payload, usage_payload)


def _read_copilot_account_usage(agent: Agent) -> dict[str, Any]:
    token = _read_github_cli_auth_token(agent)
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
        with urllib.request.urlopen(request, timeout=account_timeout_sec(agent)) as response:
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


def _read_github_cli_auth_token(agent: Agent) -> str:
    result = run_captured_command(
        ["gh", "auth", "token"],
        env=account_provider_environment(agent),
        timeout_sec=account_timeout_sec(agent),
    )
    token = successful_command_output(result).strip()
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
            message = payload.get("message")
            if isinstance(message, str) and message.strip():
                return message.strip()
        return body

    return f"Copilot API request failed with HTTP {exc.code}"
