# $kw: ^claude-statusline-usage-hook --from Agentos.Hook --from Normalization.Pipeline::Account.Usage.Model --from Account.Management --note [DC] Claude statusLine contexts normalize into account-scoped quota observations with callback-owned throttling --supp ^c20260811-5u ^c20260811-13u ^c20260811-22u ^c20260813-26u
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from tarav._core.clock import utc_now_iso
from tarav._core.errors import CliError
from tarav.agent import auth_registry
from tarav.agent.account_status import usage_record_age_sec
from tarav.agent.providers.claude_code.account_status import (
    claude_statusline_usage_record_limits,
)
from tarav.agent.providers.claude_code.auth_method import read_claude_home_identity
from tarav.agent.usage_registry import (
    append_usage_record,
    latest_account_usage_record,
)
from tarav.hooks import HookError, HookInvocation, HookRegistry


CLAUDE_STATUSLINE_CONTEXT_HOOK = "agent.statusline.context"
CLAUDE_STATUSLINE_HOOK_USAGE_SOURCE = "statusline_hook"
CLAUDE_STATUSLINE_HOOK_MIN_INTERVAL_SEC = 60
_SUPPORTED_LIMIT_TYPES = ("five_hour", "seven_day")
_SUPPORTED_LIMIT_FIELDS = ("used_percentage", "resets_at")


def register_claude_usage_hook_callbacks(registry: HookRegistry) -> None:
    registry.register(
        CLAUDE_STATUSLINE_CONTEXT_HOOK,
        _consume_claude_statusline_context,
        callback_id="agentos.agent.providers.claude-code.account-quota-report",
    )


def _consume_claude_statusline_context(invocation: HookInvocation) -> None:
    if invocation.ctx_type != "claude-code":
        return
    report_claude_usage_from_hook(invocation)


def report_claude_usage_from_hook(
    invocation: HookInvocation,
    *,
    min_interval_sec: int = CLAUDE_STATUSLINE_HOOK_MIN_INTERVAL_SEC,
) -> Path | None:
    if (
        invocation.name != CLAUDE_STATUSLINE_CONTEXT_HOOK
        or invocation.ctx_type != "claude-code"
    ):
        raise HookError(
            "Claude quota reporting requires a claude-code "
            "agent.statusline.context invocation"
        )
    if min_interval_sec <= 0:
        raise HookError("Claude statusLine hook interval must be positive")

    home = _claude_home_from_ctx(invocation.ctx)
    account = _resolve_account(home)
    payload = _usage_payload(invocation.ctx)
    previous = latest_account_usage_record(
        provider="claude-code",
        account=account,
        source=CLAUDE_STATUSLINE_HOOK_USAGE_SOURCE,
    )
    if _should_throttle(
        previous,
        rate_limits=payload["rate_limits"],
        min_interval_sec=min_interval_sec,
    ):
        return None
    return append_usage_record(
        provider="claude-code",
        account=account,
        home=home,
        source=CLAUDE_STATUSLINE_HOOK_USAGE_SOURCE,
        payload=payload,
    )


def _claude_home_from_ctx(ctx: Mapping[str, object]) -> Path:
    """The home that produced this context, read from the context itself.

    Attribution must come from the invocation, never from the environment. The
    hook runs as a child of whichever session fired it, and Claude Code does not
    pass ``CLAUDE_CONFIG_DIR`` down to that child — so an environment read falls
    back to the default home and files every session's usage under whichever
    account owns it.

    ``transcript_path`` is ``<home>/projects/<project-slug>/<session>.jsonl``, so
    it names the home unambiguously.
    """

    transcript_path = ctx.get("transcript_path")
    if not isinstance(transcript_path, str) or not transcript_path.strip():
        raise HookError(
            "Claude statusLine context is missing transcript_path; the reporting "
            "home cannot be attributed"
        )
    projects_dir = Path(transcript_path).expanduser().parent.parent
    if projects_dir.name != "projects":
        raise HookError(
            "Claude statusLine transcript_path is not under a provider home: "
            f"{transcript_path}"
        )
    return projects_dir.parent.resolve()


def _resolve_account(home: Path) -> str:
    identity = read_claude_home_identity(home)
    if identity is None:
        raise HookError(
            "Claude quota reporting could not identify the provider account"
        )
    account = auth_registry.resolve_account_by_identity("claude-code", identity)
    if account is None:
        raise HookError("Claude quota reporting could not resolve a registered account")
    return account


def _usage_payload(ctx: Mapping[str, object]) -> dict[str, Any]:
    rate_limits = _normalized_rate_limits(ctx.get("rate_limits"))
    try:
        claude_statusline_usage_record_limits({"rate_limits": rate_limits})
    except (CliError, TypeError, ValueError) as exc:
        raise HookError(
            "Claude statusLine context carries invalid rate limits"
        ) from exc

    observation: dict[str, object] = {"observedAt": utc_now_iso()}
    session_id = ctx.get("session_id")
    if isinstance(session_id, str) and session_id.strip():
        observation["sessionId"] = session_id
    return {
        "rate_limits": rate_limits,
        "observation": observation,
    }


def _normalized_rate_limits(value: object) -> dict[str, dict[str, object]]:
    if not isinstance(value, Mapping):
        raise HookError("Claude statusLine context is missing rate_limits")
    normalized: dict[str, dict[str, object]] = {}
    for limit_type in _SUPPORTED_LIMIT_TYPES:
        raw_limit = value.get(limit_type)
        if raw_limit is None:
            continue
        if not isinstance(raw_limit, Mapping):
            raise HookError(f"Claude {limit_type} rate limit must be an object")
        normalized[limit_type] = {
            field: raw_limit[field]
            for field in _SUPPORTED_LIMIT_FIELDS
            if field in raw_limit
        }
    if not normalized:
        raise HookError("Claude statusLine context has no supported rate limits")
    return normalized


def _should_throttle(
    previous: Mapping[str, Any] | None,
    *,
    rate_limits: Mapping[str, object],
    min_interval_sec: int,
) -> bool:
    if previous is None:
        return False
    payload = previous.get("payload")
    if not isinstance(payload, Mapping) or payload.get("rate_limits") != rate_limits:
        return False
    recorded_at = previous.get("recorded_at")
    age_sec = usage_record_age_sec(
        recorded_at if isinstance(recorded_at, str) else None
    )
    return age_sec is not None and age_sec < min_interval_sec


__all__ = [
    "CLAUDE_STATUSLINE_CONTEXT_HOOK",
    "CLAUDE_STATUSLINE_HOOK_MIN_INTERVAL_SEC",
    "CLAUDE_STATUSLINE_HOOK_USAGE_SOURCE",
    "register_claude_usage_hook_callbacks",
    "report_claude_usage_from_hook",
]
