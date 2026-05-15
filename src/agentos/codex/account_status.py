from __future__ import annotations

import datetime
import json
import os
import select
import subprocess
from collections.abc import Mapping
from typing import Any

from agentos._core.errors import CliError
from agentos.agent.account_registry import load_account
from agentos.agent.account_status import (
    AccountIdentity,
    AccountIdentityMatch,
    AccountLimit,
    AccountStatus,
    AccountStatusError,
    UsageOverTimeLimitData,
)
from agentos.agent.primitives import Agent
from agentos.agent.run_runtime import AgentCommandConfig
from agentos.codex.account_registry import inspect_codex_account_home


DEFAULT_ACCOUNT_STATUS_TIMEOUT_SEC = 15
CODEX_APP_SERVER_ARGV = ("app-server",)


def codex_account_status(
    agent: Agent,
) -> AccountStatus:
    if agent.account is None:
        raise CliError("codex account_status requires an agent account context")
    if agent.home is None:
        raise CliError("codex account_status requires an agent home")

    account_record = load_account(agent.provider, agent.account.account)
    home_status = inspect_codex_account_home(home=agent.home)
    link_state = _string_or_none(home_status.get("link_consistency")) or "unknown"
    expected_identity = _expected_identity(account_record)
    fetched_identity = _fetched_identity_from_home_status(home_status)
    errors = list(_setup_errors(link_state=link_state, home_status=home_status))
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
    if check_status == "error":
        usage_status = "unavailable"
        usage_summary = None
        limits: tuple[AccountLimit, ...] = ()
        usage_errors: tuple[AccountStatusError, ...] = ()
    else:
        limits, usage_errors = _codex_usage_limits(agent)
        usage_status = "error" if usage_errors else "ok"
        usage_summary = _limits_summary(limits) if limits else None
        auth_summary = "Codex rate limits read" if usage_status == "ok" else None

    return AccountStatus(
        provider=agent.provider,
        account=agent.account.account,
        home=agent.home,
        check_status=check_status,
        usage_status=usage_status,
        link_state=link_state,
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
        },
    )


def _expected_identity(account_record: dict[str, object]) -> AccountIdentity:
    return AccountIdentity(
        provider_account_id=_string_or_none(account_record.get("account_id")),
        email=_string_or_none(account_record.get("email")),
        label=_string_or_none(account_record.get("label")),
        raw=account_record,
    )


def _fetched_identity_from_home_status(home_status: Mapping[str, object]) -> AccountIdentity | None:
    auth = home_status.get("auth")
    if not isinstance(auth, dict):
        return None
    return AccountIdentity(
        provider_account_id=_string_or_none(auth.get("account_id")),
        email=_string_or_none(auth.get("email")),
        raw=auth,
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
    link_state: str,
    home_status: Mapping[str, object],
) -> tuple[AccountStatusError, ...]:
    errors: list[AccountStatusError] = []
    if link_state not in {"verified", "stale"}:
        errors.append(
            AccountStatusError(
                error_type="home_link_unusable",
                message=f"codex account home link is not usable: {link_state}",
                detail={
                    "classification": home_status.get("classification"),
                    "link_state": link_state,
                    "home": home_status.get("home"),
                    "auth_path": home_status.get("auth_path"),
                    "error": home_status.get("error"),
                },
            )
        )
    return tuple(errors)


def _codex_usage_limits(agent: Agent) -> tuple[tuple[AccountLimit, ...], tuple[AccountStatusError, ...]]:
    try:
        payload = _read_codex_account_rate_limits(agent)
        return tuple(_parse_codex_rate_limits(payload)), ()
    except AccountStatusError as exc:
        return (), (exc,)
    except (CliError, json.JSONDecodeError, TypeError, ValueError) as exc:
        return (), (AccountStatusError(error_type="invalid_output", message=str(exc)),)


def _read_codex_account_rate_limits(agent: Agent) -> dict[str, Any]:
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
        response = _read_process_json_response(
            process,
            request_id=request_id + 1,
            request_name="rate-limit request",
            timeout_sec=timeout_sec,
        )
        error_payload = response.get("error")
        if error_payload is not None:
            raise AccountStatusError(
                error_type="command_failed",
                message=_codex_response_error_message(error_payload),
            )

        payload = response.get("result")
        if not isinstance(payload, dict):
            raise CliError("codex app-server rate-limit response must be a JSON object")
        return payload
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


def _build_codex_account_status_command(agent: Agent, *, argv: tuple[str, ...]):
    return agent.build_command(AgentCommandConfig(argv=argv))


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
        snapshots.append((_string_or_none(raw_rate_limits.get("limitId")), raw_rate_limits))

    limits: list[AccountLimit] = []
    for limit_id, snapshot in snapshots:
        limits.extend(_parse_codex_snapshot_windows(snapshot, limit_id=limit_id))
    return tuple(limits)


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
            AccountLimit(
                limit_class="usage_over_time",
                limit_name=_codex_window_name(window_duration_mins, window_key=window_key),
                limit_label=_codex_window_label(window_duration_mins, window_key=window_key),
                usage_over_time=UsageOverTimeLimitData(
                    used_percent=used_percent,
                    period_started_at=period_started_at,
                    period_ends_at=period_ends_at,
                    period_duration_mins=window_duration_mins,
                    resets_at=_iso_from_epoch_seconds(resets_at_epoch),
                ),
                provider_limit={
                    "limit_id": limit_id,
                    "window_key": window_key,
                    "window_duration_mins": window_duration_mins,
                },
            )
        )
    return tuple(limits)


def _codex_window_name(window_duration_mins: int | None, *, window_key: str) -> str:
    if window_duration_mins is None:
        return window_key
    if window_duration_mins >= 60 and window_duration_mins % 60 == 0:
        return f"{window_duration_mins // 60}h"
    return f"{window_duration_mins}m"


def _codex_window_label(window_duration_mins: int | None, *, window_key: str) -> str:
    if window_duration_mins is None:
        return window_key.title()
    if window_duration_mins >= 60 and window_duration_mins % 60 == 0:
        hours = window_duration_mins // 60
        unit = "hour" if hours == 1 else "hours"
        return f"{hours} {unit}"
    unit = "minute" if window_duration_mins == 1 else "minutes"
    return f"{window_duration_mins} {unit}"


def _limits_summary(limits: tuple[AccountLimit, ...]) -> str | None:
    parts: list[str] = []
    for limit in limits:
        usage = limit.usage_over_time
        if usage is None:
            continue
        if usage.used_percent is None:
            if limit.limit_label is not None:
                parts.append(limit.limit_label)
            continue
        label = limit.limit_label or limit.limit_name
        parts.append(f"{label} {usage.used_percent}%")
    return ", ".join(parts) or None


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


def _account_timeout_sec(agent: Agent) -> int:
    return agent.timeout_sec or DEFAULT_ACCOUNT_STATUS_TIMEOUT_SEC


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


def _iso_from_epoch_seconds(epoch_seconds: int | None) -> str | None:
    if epoch_seconds is None:
        return None
    return datetime.datetime.fromtimestamp(
        epoch_seconds,
        tz=datetime.timezone.utc,
    ).isoformat().replace("+00:00", "Z")


def _required_int(value: object, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise CliError(f"{field_name} must be an integer")
    return value


def _optional_int(value: object, *, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise CliError(f"{field_name} must be an integer")
    return value


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


__all__ = ["codex_account_status"]
