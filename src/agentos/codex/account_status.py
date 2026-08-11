# $kw: ^codex-account-quota-live-read --from Normalization.Pipeline::Account.Usage.Model --note [DC] live account status requests provider quota windows only; account token-history accounting is outside monitor scope --supp ^c20260811-47u
from __future__ import annotations

import json
import os
import select
import subprocess
from collections.abc import Mapping
from typing import Any

from agentos._core.errors import CliError
from agentos.agent import auth_registry
from agentos.agent.account_status import (
    AccountIdentity,
    AccountIdentityMatch,
    AccountLimit,
    AccountStatus,
    AccountStatusError,
    UsageOverTimeLimitData,
    USAGE_RECORD_STATUS_REGISTRY_FALLBACK,
    fresh_usage_record_metadata,
    iso_from_epoch_seconds,
    limits_summary,
    optional_int,
    period_bounds_from_reset,
    string_or_none,
)
from agentos.agent.account_usage_fallback import (
    AccountUsageReadResult,
    account_usage_registry_fallback,
)
from agentos.agent.primitives import AgentConfig
from agentos.agent.run_runtime import AgentCommandConfig
from agentos.agent.usage_registry import append_usage_record


DEFAULT_ACCOUNT_STATUS_TIMEOUT_SEC = 15
CODEX_APP_SERVER_ARGV = ("app-server",)
CODEX_APP_SERVER_USAGE_SOURCE = "app_server"
CODEX_APP_SERVER_RATE_LIMITS_METHOD = "account/rateLimits/read"


def _codex_account_status_impl(
    agent: AgentConfig,
    *,
    record_usage: bool = True,
    fallback_to_usage_registry: bool = True,
) -> AccountStatus:
    if agent.account is None:
        raise CliError("codex account_status requires an agent account context")
    if agent.home is None:
        raise CliError("codex account_status requires an agent home")

    from agentos.codex.auth_method import CodexAuthMethod

    expected_identity = (
        auth_registry.expected_identity(agent.provider, agent.account.account)
        or AccountIdentity()
    )
    method = CodexAuthMethod()
    auth_data = method.read_auth_data(agent.home)
    auth_state = "logged-in" if auth_data is not None else "missing"
    fetched_identity = method.extract_identity(auth_data) if auth_data is not None else None
    home_status: dict[str, object] = {"classification": auth_state, "home": str(agent.home)}
    errors = list(_setup_errors(auth_state=auth_state, home_status=home_status))
    identity_match = _identity_match(expected_identity, fetched_identity)
    if identity_match == "mismatched":
        errors.append(
            AccountStatusError(
                error_type="identity_mismatch",
                message=(
                    "codex home auth identity does not match registered account "
                    f"{agent.account.account}"
                ),
                detail={
                    "expected_identity": expected_identity.summary(),
                    "fetched_identity": (
                        fetched_identity.summary() if fetched_identity is not None else None
                    ),
                },
            )
        )

    check_status = "error" if errors else "ok"
    auth_summary: str | None = None
    auth_artifact_record: dict[str, object] | None = None
    if check_status == "error":
        usage_status = "unavailable"
        usage_summary = None
        limits: tuple[AccountLimit, ...] = ()
        usage_errors: tuple[AccountStatusError, ...] = ()
        usage_payload: dict[str, Any] | None = None
        usage_record_metadata: dict[str, Any] | None = None
    else:
        (
            limits,
            usage_errors,
            usage_payload,
            usage_record_payload,
            usage_record_metadata,
        ) = _account_usage_app_server(agent)
        if usage_errors:
            live_error = usage_errors[0]
            (
                limits,
                usage_errors,
                usage_payload,
                usage_record_payload,
                usage_record_metadata,
            ) = account_usage_registry_fallback(
                provider=agent.provider,
                account=agent.account.account,
                home=agent.home,
                source=CODEX_APP_SERVER_USAGE_SOURCE,
                parser=codex_usage_record_limits,
                live_error=live_error,
                fallback_to_usage_registry=fallback_to_usage_registry,
            )
        usage_status = "error" if usage_errors else "ok"
        usage_summary = limits_summary(limits) if limits else None
        auth_summary = _usage_auth_summary(
            usage_record_metadata,
            usage_status=usage_status,
        )
        if record_usage and usage_status == "ok" and limits and usage_record_payload is not None:
            append_usage_record(
                provider=agent.provider,
                account=agent.account.account,
                home=agent.home,
                source=CODEX_APP_SERVER_USAGE_SOURCE,
                payload=usage_record_payload,
            )
        # account_status is read-only: no active-promote. Capture (Keep.Up.With.Rotation)
        # is handled by the run path, not by status.

    return AccountStatus(
        provider=agent.provider,
        account=agent.account.account,
        home=agent.home,
        check_status=check_status,
        usage_status=usage_status,
        auth_state=auth_state,
        expected_identity=expected_identity,
        fetched_identity=fetched_identity,
        identity_match=identity_match,
        auth_summary=auth_summary,
        usage_summary=usage_summary,
        limits=limits,
        errors=tuple(errors),
        usage_errors=tuple(usage_errors),
        raw={
            "home_status": home_status,
            "reconciliation": None,
            "usage": usage_payload,
            "usage_record": usage_record_metadata,
            "auth_artifact_record": auth_artifact_record,
        },
    )


def _identity_match(
    expected_identity: AccountIdentity,
    fetched_identity: AccountIdentity | None,
) -> AccountIdentityMatch:
    if fetched_identity is None:
        return "unavailable"
    if expected_identity.provider_account_id is None or fetched_identity.provider_account_id is None:
        return "unknown"
    if expected_identity.provider_account_id == fetched_identity.provider_account_id:
        return "verified"
    return "mismatched"


def _setup_errors(
    *,
    auth_state: str,
    home_status: Mapping[str, object],
) -> tuple[AccountStatusError, ...]:
    errors: list[AccountStatusError] = []
    if auth_state != "logged-in":
        errors.append(
            AccountStatusError(
                error_type="home_auth_unusable",
                message=f"codex account home auth is not usable: {auth_state}",
                detail={
                    "auth_state": auth_state,
                    "home": home_status.get("home"),
                },
            )
        )
    return tuple(errors)


# Codex usage data may grow additional sources. Keep each implementation
# isolated while we evaluate which one should become the long-term capability.
def _account_usage_app_server(
    agent: AgentConfig,
) -> AccountUsageReadResult:
    try:
        payload = _fetch_account_usage_app_server_payload(agent)
        return (
            tuple(_parse_codex_rate_limits(payload)),
            (),
            payload,
            payload,
            fresh_usage_record_metadata(source=CODEX_APP_SERVER_USAGE_SOURCE),
        )
    except AccountStatusError as exc:
        return (), (exc,), None, None, None
    except (CliError, json.JSONDecodeError, TypeError, ValueError) as exc:
        return (
            (),
            (AccountStatusError(error_type="invalid_output", message=str(exc)),),
            None,
            None,
            None,
        )


def _fetch_account_usage_app_server_payload(agent: AgentConfig) -> dict[str, Any]:
    command = _build_codex_account_status_command(agent, argv=CODEX_APP_SERVER_ARGV)
    timeout_sec = _account_timeout_sec(agent)
    try:
        process = subprocess.Popen(
            command.argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=_process_environment(command.env_overrides),
        )
    except FileNotFoundError as exc:
        raise AccountStatusError(error_type="command_not_found", message=str(exc)) from exc
    except OSError as exc:
        raise AccountStatusError(error_type="command_failed", message=str(exc)) from exc

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
    rate_limits_request_id = request_id + 1
    rate_limits_request = {
        "id": rate_limits_request_id,
        "method": CODEX_APP_SERVER_RATE_LIMITS_METHOD,
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
            request_id=rate_limits_request_id,
            request_name="rate-limit request",
            timeout_sec=timeout_sec,
        )
        error_payload = rate_limits_response.get("error")
        if error_payload is not None:
            raise AccountStatusError(
                error_type="command_failed",
                message=_codex_response_error_message(error_payload),
            )

        rate_limits_payload = rate_limits_response.get("result")
        if not isinstance(rate_limits_payload, dict):
            raise CliError("codex app-server rate-limit response must be a JSON object")
        return dict(rate_limits_payload)
    except subprocess.TimeoutExpired as exc:
        raise AccountStatusError(
            error_type="timeout",
            message=f"provider command timed out after {timeout_sec} seconds",
        ) from exc
    except BrokenPipeError as exc:
        stderr = _read_process_stderr(process)
        raise AccountStatusError(
            error_type="command_failed",
            message=stderr or str(exc),
        ) from exc
    finally:
        _terminate_process(process)


def _build_codex_account_status_command(agent: AgentConfig, *, argv: tuple[str, ...]):
    return agent._build_command(AgentCommandConfig(argv=argv))


def _parse_codex_rate_limits(payload: Mapping[str, Any]) -> tuple[AccountLimit, ...]:
    rate_limits_by_id = payload.get("rateLimitsByLimitId")
    snapshots: list[tuple[str | None, Mapping[str, Any]]] = []
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
        snapshots.append((string_or_none(raw_rate_limits.get("limitId")), raw_rate_limits))

    limits: list[AccountLimit] = []
    for limit_id, snapshot in snapshots:
        limits.extend(_parse_codex_snapshot_windows(snapshot, limit_id=limit_id))
    return tuple(limits)


def codex_usage_record_limits(payload: Mapping[str, Any]) -> tuple[AccountLimit, ...]:
    return _parse_codex_rate_limits(payload)


def _parse_codex_snapshot_windows(
    snapshot: Mapping[str, Any],
    *,
    limit_id: str | None,
) -> tuple[AccountLimit, ...]:
    limits: list[AccountLimit] = []
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
        window_duration_mins = optional_int(
            raw_window.get("windowDurationMins"),
            field_name=f"codex {window_key} windowDurationMins",
        )
        resets_at_epoch = optional_int(
            raw_window.get("resetsAt"),
            field_name=f"codex {window_key} resetsAt",
        )
        period_started_at, period_ends_at = period_bounds_from_reset(
            resets_at_epoch=resets_at_epoch,
            period_duration_mins=window_duration_mins,
        )
        parsed_limit_id = _codex_window_limit_id(
            window_key,
            window_duration_mins=window_duration_mins,
        )
        parsed_limit_label = _codex_limit_label(parsed_limit_id)
        limits.append(
            AccountLimit(
                limit_class="usage_over_time",
                limit_id=parsed_limit_id,
                limit_name=parsed_limit_id,
                limit_label=parsed_limit_label,
                usage_over_time=UsageOverTimeLimitData(
                    used_percent=used_percent,
                    period_started_at=period_started_at,
                    period_ends_at=period_ends_at,
                    period_duration_mins=window_duration_mins,
                    resets_at=iso_from_epoch_seconds(resets_at_epoch),
                ),
                provider_limit={
                    "limit_id": limit_id,
                    "window_key": window_key,
                    "window_duration_mins": window_duration_mins,
                },
            )
        )
    return tuple(limits)


def _codex_window_limit_id(
    window_key: str,
    *,
    window_duration_mins: int | None,
) -> str:
    if window_duration_mins == 300:
        return "burst"
    if window_duration_mins == 10_080:
        return "weekly"
    if window_key == "primary":
        return "burst"
    if window_key == "secondary":
        return "weekly"
    raise CliError(f"unsupported codex rate-limit window {window_key!r}")


def _codex_limit_label(limit_id: str) -> str:
    if limit_id == "burst":
        return "Burst"
    if limit_id == "weekly":
        return "Weekly"
    return limit_id


def _usage_auth_summary(
    usage_record_metadata: Mapping[str, Any] | None,
    *,
    usage_status: str,
) -> str | None:
    if usage_status != "ok":
        return None
    if (
        isinstance(usage_record_metadata, Mapping)
        and usage_record_metadata.get("status") == USAGE_RECORD_STATUS_REGISTRY_FALLBACK
    ):
        return "Codex usage registry fallback"
    return "Codex app-server usage read"


def _write_json_line(process: subprocess.Popen[str], payload: Mapping[str, Any]) -> None:
    if process.stdin is None:
        raise CliError("provider process stdin is not available")
    process.stdin.write(json.dumps(payload, separators=(",", ":")) + "\n")
    process.stdin.flush()


def _read_process_json_response(
    process: subprocess.Popen[str],
    *,
    timeout_sec: int,
    request_id: int,
    request_name: str,
) -> dict[str, Any]:
    while True:
        payload = _read_process_json_line(process, timeout_sec=timeout_sec)
        if payload.get("id") == request_id:
            return payload
        if "method" in payload and "id" not in payload:
            continue
        raise CliError(f"codex app-server {request_name} returned an unexpected response id")


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
        raise AccountStatusError(
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


def _terminate_process(process: subprocess.Popen[str]) -> None:
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


def _codex_response_error_message(error_payload: object) -> str:
    if isinstance(error_payload, dict):
        message = error_payload.get("message")
        code = error_payload.get("code")
        suffix = f" (code {code})" if code is not None else ""
        return str(message) if message is not None else f"codex app-server returned an error{suffix}"
    return "codex app-server returned an invalid error payload"


def _process_environment(env_overrides: Mapping[str, str]) -> dict[str, str]:
    env = os.environ.copy()
    env.update(env_overrides)
    return env


def _account_timeout_sec(agent: AgentConfig) -> int:
    return agent.timeout_sec or DEFAULT_ACCOUNT_STATUS_TIMEOUT_SEC


def _required_int(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CliError(f"{field_name} must be an integer")
    return value


__all__: list[str] = []
