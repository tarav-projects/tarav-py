from __future__ import annotations

import calendar
import datetime
import json
import urllib.error
import urllib.request
from collections.abc import Mapping
from typing import Any

from agentos._core.errors import CliError
from agentos._core.process import run_process
from agentos.agent.account_registry import load_account
from agentos.agent.account_status import (
    AccountIdentity,
    AccountIdentityMatch,
    AccountLimit,
    AccountStatus,
    AccountStatusError,
    USAGE_RECORD_STATUS_REGISTRY_FALLBACK,
    UsageOverTimeLimitData,
    fresh_usage_record_metadata,
)
from agentos.agent.account_usage_fallback import (
    AccountUsageReadResult,
    account_usage_registry_fallback,
)
from agentos.agent.primitives import Agent
from agentos.agent.usage_registry import append_usage_record


DEFAULT_COPILOT_USAGE_TIMEOUT_SEC = 15
COPILOT_USAGE_API_URL = "https://api.github.com/copilot_internal/user"
COPILOT_INTERNAL_USER_USAGE_SOURCE = "copilot_internal_user"
COPILOT_EDITOR_VERSION = "vscode/1.96.2"
COPILOT_EDITOR_PLUGIN_VERSION = "copilot-chat/0.26.7"
COPILOT_USER_AGENT = "GitHubCopilotChat/0.26.7"
COPILOT_GITHUB_API_VERSION = "2025-04-01"


def _copilot_account_status_impl(
    agent: Agent,
    *,
    record_usage: bool = True,
    fallback_to_usage_registry: bool = True,
) -> AccountStatus:
    if agent.account is None:
        raise CliError("copilot-cli account_status requires an agent account context")
    if agent.home is None:
        raise CliError("copilot-cli account_status requires an agent home")

    account_record = load_account(agent.provider, agent.account.account)
    expected_identity = _expected_identity(account_record)
    auth_state = "home-present" if agent.home.exists() else "home-missing"
    errors = list(_setup_errors(agent=agent))

    fetched_identity: AccountIdentity | None = None
    identity_match: AccountIdentityMatch = "unavailable"
    auth_summary: str | None = None
    if errors:
        usage_status = "unavailable"
        usage_summary = None
        limits: tuple[AccountLimit, ...] = ()
        usage_errors: tuple[AccountStatusError, ...] = ()
        usage_payload: dict[str, Any] | None = None
        usage_record_payload: dict[str, Any] | None = None
        usage_record_metadata: dict[str, Any] | None = None
    else:
        (
            limits,
            usage_errors,
            usage_payload,
            usage_record_payload,
            usage_record_metadata,
        ) = _account_usage_internal_user(agent)
        fetched_identity = _fetched_identity_from_usage_payload(usage_payload)
        identity_match = _identity_match(expected_identity, fetched_identity)
        if identity_match == "mismatched":
            errors.append(
                AccountStatusError(
                    error_type="identity_mismatch",
                    message=(
                        "copilot-cli usage identity does not match registered account "
                        f"{agent.account.account}"
                    ),
                    detail={
                        "expected_identity": expected_identity.summary(),
                        "fetched_identity": (
                            fetched_identity.summary()
                            if fetched_identity is not None
                            else None
                        ),
                    },
                )
            )
        if errors:
            usage_status = "unavailable"
            usage_summary = None
            limits = ()
            usage_errors = ()
            usage_record_payload = None
            usage_record_metadata = None
        elif usage_errors:
            live_error = usage_errors[0]
            (
                limits,
                usage_errors,
                usage_payload,
                usage_record_payload,
                usage_record_metadata,
            ) = account_usage_registry_fallback(
                provider=agent.provider,
                account=_account_name(agent),
                home=agent.home,
                source=COPILOT_INTERNAL_USER_USAGE_SOURCE,
                parser=copilot_usage_record_limits,
                live_error=live_error,
                fallback_to_usage_registry=fallback_to_usage_registry,
            )
            usage_status = "error" if usage_errors else "ok"
            if (
                usage_record_metadata is not None
                and usage_record_metadata.get("status")
                == USAGE_RECORD_STATUS_REGISTRY_FALLBACK
            ):
                auth_summary = "Copilot usage registry fallback"
        else:
            usage_status = "ok"
            auth_summary = "Copilot usage read"
        usage_summary = _limits_summary(limits) if limits else None
        if record_usage and usage_status == "ok" and limits and usage_record_payload is not None:
            append_usage_record(
                provider=agent.provider,
                account=agent.account.account,
                home=agent.home,
                source=COPILOT_INTERNAL_USER_USAGE_SOURCE,
                payload=usage_record_payload,
            )

    return AccountStatus(
        provider=agent.provider,
        account=agent.account.account,
        home=agent.home,
        check_status="error" if errors else "ok",
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
            "usage": usage_payload,
            "usage_record": usage_record_metadata,
        },
    )


def _expected_identity(account_record: dict[str, object]) -> AccountIdentity:
    return AccountIdentity(
        provider_account_id=_string_or_none(account_record.get("account_id")),
        email=_string_or_none(account_record.get("email")),
        label=_string_or_none(account_record.get("label")),
        raw=account_record,
    )


def _fetched_identity_from_usage_payload(
    usage_payload: Mapping[str, Any] | None,
) -> AccountIdentity | None:
    if usage_payload is None:
        return None
    login = _string_or_none(usage_payload.get("login"))
    if login is None:
        return None
    return AccountIdentity(
        provider_account_id=login,
        label=_string_or_none(usage_payload.get("name")),
        raw={"login": login},
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
    agent: Agent,
) -> tuple[AccountStatusError, ...]:
    errors: list[AccountStatusError] = []
    if agent.home is None:
        errors.append(
            AccountStatusError(
                error_type="home_missing",
                message="copilot-cli account_status requires an agent home",
            )
        )
        return tuple(errors)
    if not agent.home.exists():
        errors.append(
            AccountStatusError(
                error_type="home_missing",
                message=f"copilot-cli account home does not exist: {agent.home}",
            )
        )
    return tuple(errors)


# Copilot usage data may grow additional sources. Keep each implementation
# isolated while we evaluate which one should become the long-term capability.
def _account_usage_internal_user(
    agent: Agent,
) -> AccountUsageReadResult:
    try:
        payload = _fetch_copilot_internal_user_payload(agent)
        return (
            _parse_copilot_usage_response(payload),
            (),
            payload,
            payload,
            fresh_usage_record_metadata(source=COPILOT_INTERNAL_USER_USAGE_SOURCE),
        )
    except AccountStatusError as exc:
        return (), (exc,), None, None, None
    except (CliError, OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        return (
            (),
            (AccountStatusError(error_type="invalid_output", message=str(exc)),),
            None,
            None,
            None,
        )


def _fetch_copilot_internal_user_payload(agent: Agent) -> dict[str, Any]:
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
    timeout_sec = _account_timeout_sec(agent)
    try:
        with urllib.request.urlopen(request, timeout=timeout_sec) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise AccountStatusError(
            error_type="usage_api_http_error",
            message=_copilot_http_error_message(exc),
            exit_code=exc.code,
        ) from exc
    except urllib.error.URLError as exc:
        reason = exc.reason
        raise AccountStatusError(
            error_type="network_error",
            message=str(reason) if reason is not None else str(exc),
        ) from exc
    except TimeoutError as exc:
        raise AccountStatusError(
            error_type="timeout",
            message=f"copilot usage API timed out after {timeout_sec} seconds",
        ) from exc
    except OSError as exc:
        raise AccountStatusError(error_type="network_error", message=str(exc)) from exc
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise CliError("copilot usage response must be a JSON object")
    return payload


def _read_github_cli_auth_token(agent: Agent) -> str:
    try:
        result = run_process(
            ("gh", "auth", "token"),
            mode="capture",
            env_overrides=dict(agent.env),
            timeout_sec=_account_timeout_sec(agent),
        )
    except OSError as exc:
        raise AccountStatusError(error_type="command_failed", message=str(exc)) from exc
    if result.exit_code != 0:
        message = (result.stderr or result.stdout or "").strip()
        raise AccountStatusError(
            error_type="command_failed",
            message=message or f"gh auth token exited with {result.exit_code}",
            exit_code=result.exit_code,
        )
    token = (result.stdout or "").strip()
    if not token:
        raise AccountStatusError(
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
    if body:
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return body
        message = payload.get("message") if isinstance(payload, dict) else None
        if isinstance(message, str) and message.strip():
            return message.strip()
    return f"copilot usage API returned HTTP {exc.code}"


def _parse_copilot_usage_response(payload: Mapping[str, Any]) -> tuple[AccountLimit, ...]:
    direct_snapshots = _parse_copilot_quota_snapshots(payload.get("quota_snapshots"))
    monthly_snapshots = _copilot_monthly_quota_snapshots(payload)
    period_started_at, period_ends_at, period_duration_mins = _copilot_monthly_period_bounds(payload)

    premium_snapshot = _usable_copilot_quota_snapshot(
        direct_snapshots["premium_interactions"]
    ) or _usable_copilot_quota_snapshot(monthly_snapshots["premium_interactions"])
    chat_snapshot = _usable_copilot_quota_snapshot(
        direct_snapshots["chat"]
    ) or _usable_copilot_quota_snapshot(monthly_snapshots["chat"])

    limits: list[AccountLimit] = []
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
    if not limits:
        raise CliError("copilot usage response did not contain any usable quota snapshots")
    return tuple(limits)


def copilot_usage_record_limits(payload: Mapping[str, Any]) -> tuple[AccountLimit, ...]:
    return _parse_copilot_usage_response(payload)


def _parse_copilot_quota_snapshots(value: object) -> dict[str, dict[str, Any] | None]:
    if value is None:
        return {
            "premium_interactions": None,
            "chat": None,
        }
    if not isinstance(value, dict):
        raise CliError("copilot quota_snapshots must be an object")
    return {
        "premium_interactions": _parse_copilot_quota_snapshot(
            value.get("premium_interactions"),
            field_name="copilot quota_snapshots.premium_interactions",
        ),
        "chat": _parse_copilot_quota_snapshot(
            value.get("chat"),
            field_name="copilot quota_snapshots.chat",
        ),
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
    entitlement = _optional_number(
        value.get("entitlement"),
        field_name=f"{field_name}.entitlement",
    )
    remaining = _optional_number(
        value.get("remaining"),
        field_name=f"{field_name}.remaining",
    )
    raw_percent_remaining = _optional_number(
        value.get("percent_remaining"),
        field_name=f"{field_name}.percent_remaining",
    )
    if value.get("unlimited") is True:
        return None
    if (
        value.get("has_quota") is False
        and (entitlement is None or entitlement <= 0)
        and (remaining is None or remaining <= 0)
    ):
        return None
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


def _copilot_monthly_quota_snapshots(payload: Mapping[str, Any]) -> dict[str, dict[str, Any] | None]:
    monthly_quotas = _parse_copilot_quota_counts(
        payload.get("monthly_quotas"),
        field_name="copilot monthly_quotas",
    )
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
        "chat": _optional_number(value.get("chat"), field_name=f"{field_name}.chat"),
        "completions": _optional_number(
            value.get("completions"),
            field_name=f"{field_name}.completions",
        ),
    }


def _copilot_quota_snapshot_from_monthly(
    *,
    monthly: float | None,
    limited: float | None,
    quota_id: str,
) -> dict[str, Any] | None:
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
    if snapshot is None or not snapshot.get("has_percent_remaining"):
        return None
    if _copilot_quota_snapshot_is_placeholder(snapshot):
        return None
    return snapshot


def _copilot_quota_snapshot_is_placeholder(snapshot: Mapping[str, Any]) -> bool:
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
    period_started_at: str | None,
    period_ends_at: str | None,
    period_duration_mins: int | None,
) -> AccountLimit | None:
    if snapshot is None:
        return None
    percent_remaining = _optional_number(
        snapshot.get("percent_remaining"),
        field_name="copilot percent_remaining",
    )
    if percent_remaining is None:
        return None
    return AccountLimit(
        limit_class="usage_over_time",
        limit_id=name,
        limit_name=name,
        limit_label=label,
        usage_over_time=UsageOverTimeLimitData(
            used_percent=round(100 - percent_remaining),
            period_started_at=period_started_at,
            period_ends_at=period_ends_at,
            period_duration_mins=period_duration_mins,
            resets_at=period_ends_at,
        ),
        provider_limit={
            "quota_id": snapshot.get("quota_id"),
            "entitlement": snapshot.get("entitlement"),
            "remaining": snapshot.get("remaining"),
            "percent_remaining": percent_remaining,
        },
    )


def _copilot_monthly_period_bounds(payload: Mapping[str, Any]) -> tuple[str | None, str | None, int | None]:
    period_ends_at = _copilot_quota_reset_at(payload)
    if period_ends_at is None:
        return (None, None, None)
    period_ends_at_dt = _parse_iso_datetime(period_ends_at)
    if period_ends_at_dt is None:
        return (None, period_ends_at, None)
    period_started_at_dt = _previous_month_same_instant(period_ends_at_dt)
    period_duration_mins = int((period_ends_at_dt - period_started_at_dt).total_seconds() // 60)
    return (
        _datetime_to_iso(period_started_at_dt),
        _datetime_to_iso(period_ends_at_dt),
        period_duration_mins,
    )


def _copilot_quota_reset_at(payload: Mapping[str, Any]) -> str | None:
    raw_reset_at = _string_or_none(payload.get("quota_reset_date_utc"))
    if raw_reset_at is not None:
        reset_at = _parse_iso_datetime(raw_reset_at)
        return _datetime_to_iso(reset_at) if reset_at is not None else raw_reset_at
    raw_reset_date = _string_or_none(payload.get("quota_reset_date"))
    if raw_reset_date is None:
        return None
    try:
        reset_date = datetime.date.fromisoformat(raw_reset_date)
    except ValueError:
        return raw_reset_date
    reset_at = datetime.datetime.combine(reset_date, datetime.time.min, tzinfo=datetime.UTC)
    return _datetime_to_iso(reset_at)


def _previous_month_same_instant(value: datetime.datetime) -> datetime.datetime:
    month = value.month - 1
    year = value.year
    if month == 0:
        month = 12
        year -= 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


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


def _account_name(agent: Agent) -> str:
    if agent.account is None:
        raise AccountStatusError(
            error_type="account_missing",
            message="copilot-cli account_status requires an agent account context",
        )
    return agent.account.account


def _account_timeout_sec(agent: Agent) -> int:
    return agent.timeout_sec or DEFAULT_COPILOT_USAGE_TIMEOUT_SEC


def _optional_number(value: object, *, field_name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise CliError(f"{field_name} must be a number")
    return float(value)


def _parse_iso_datetime(value: str | None) -> datetime.datetime | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=datetime.UTC)
    return parsed.astimezone(datetime.UTC)


def _datetime_to_iso(value: datetime.datetime) -> str:
    return value.astimezone(datetime.UTC).isoformat().replace("+00:00", "Z")


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


__all__ = [
    "COPILOT_INTERNAL_USER_USAGE_SOURCE",
    "copilot_usage_record_limits",
]
