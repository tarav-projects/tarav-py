from __future__ import annotations

import json
import subprocess
from typing import Any

from agentos._core.errors import CliError
from agentos.agent.account_runtime import (
    AccountCommandError,
    AccountStatsRequest,
    account_provider_environment,
    account_timeout_sec,
    collect_parsed_command_payload,
)
from agentos.agent.primitives import Agent
from agentos.agent.accounts import (
    _merge_account_payloads,
    _parse_codex_login_status,
    _parse_codex_rate_limits,
    _read_process_json_response,
    _read_process_stderr,
    _usage_error_payload,
    _write_json_line,
)


def codex_account_stats(agent: Agent, request: AccountStatsRequest) -> dict[str, Any]:
    del request

    auth_payload = collect_parsed_command_payload(
        agent,
        extra_args=("login", "status"),
        parser=_parse_codex_login_status,
    )

    try:
        usage_payload = _parse_codex_rate_limits(_read_codex_account_rate_limits(agent))
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


def _read_codex_account_rate_limits(agent: Agent) -> dict[str, Any]:
    command = [*agent.cli_command, "app-server"]
    timeout_sec = account_timeout_sec(agent)
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=account_provider_environment(agent),
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

    request_id = 1
    initialize_request = {
        "id": request_id,
        "method": "initialize",
        "params": {
            "capabilities": {
                "optOutNotificationMethods": [
                    "account/updated",
                    "account/rateLimits/updated",
                ],
            },
            "clientInfo": {
                "name": "agentos",
                "version": "1",
            },
        },
    }
    rate_limits_request = {
        "id": request_id + 1,
        "method": "account/rateLimits/read",
    }

    try:
        _write_json_line(process, initialize_request)
        _read_process_json_response(
            process,
            request_id=request_id,
            request_name="initialize",
            timeout_sec=timeout_sec,
        )
        _write_json_line(process, rate_limits_request)
        rate_limits_response = _read_process_json_response(
            process,
            request_id=request_id + 1,
            request_name="rate-limit request",
            timeout_sec=timeout_sec,
        )
        error_payload = rate_limits_response.get("error")
        if error_payload is not None:
            if isinstance(error_payload, dict):
                message = error_payload.get("message")
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
            message=f"provider command timed out after {timeout_sec} seconds",
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
