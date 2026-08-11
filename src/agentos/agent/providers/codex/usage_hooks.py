# $kw: ^codex-account-quota-hook --from Agentos.Hook --from Normalization.Pipeline::Account.Usage.Model --note [DC] Codex turn-stop callbacks normalize the active session quota snapshot into the account usage registry --supp ^c20260811-5u ^c20260811-13u ^c20260811-32u ^c20260811-47u
# $kw: ^agentos-provider-codex-usage-hooks --from Agent.Navigable.Codebase --note [DF] provider-specific behavior lives beneath the agent provider namespace --supp ^c20260811-62u
from __future__ import annotations

import json
import os
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

from agentos.agent import auth_registry
from agentos.agent.usage_registry import append_usage_record
from agentos.agent.providers.codex.auth_method import CodexAuthMethod
from agentos.hooks import HookError, HookInvocation, HookRegistry


CODEX_SESSION_HOOK_USAGE_SOURCE = "session_hook"


def register_codex_usage_hook_callbacks(registry: HookRegistry) -> None:
    registry.register(
        "agent.turn.stop",
        _consume_codex_turn_stop,
        callback_id="agentos.agent.providers.codex.account-quota-report",
    )


def _consume_codex_turn_stop(invocation: HookInvocation) -> None:
    if invocation.ctx_type != "codex":
        return
    report_codex_quota_from_hook(invocation)


def report_codex_quota_from_hook(invocation: HookInvocation) -> Path:
    if invocation.name != "agent.turn.stop" or invocation.ctx_type != "codex":
        raise HookError(
            "Codex quota reporting requires a codex agent.turn.stop invocation"
        )

    session_id = _required_string(invocation.ctx.get("session_id"), field="session_id")
    transcript_hint = _optional_path(invocation.ctx.get("transcript_path"))
    home = _codex_home(transcript_hint)
    transcript = _resolve_transcript(
        home=home,
        session_id=session_id,
        transcript_hint=transcript_hint,
    )
    _validate_transcript_session(transcript, session_id=session_id)
    observed_at, rate_limits = _latest_rate_limits(transcript)
    account = _resolve_account(home)
    return append_usage_record(
        provider="codex",
        account=account,
        home=home,
        source=CODEX_SESSION_HOOK_USAGE_SOURCE,
        payload={
            "rateLimits": _normalize_rate_limits(rate_limits),
            "observation": {
                "sessionId": session_id,
                "observedAt": observed_at,
            },
        },
    )


def _codex_home(transcript_hint: Path | None) -> Path:
    configured_home = os.getenv("CODEX_HOME")
    if configured_home:
        return Path(configured_home).expanduser().resolve()
    if transcript_hint is not None:
        for parent in transcript_hint.expanduser().resolve().parents:
            if parent.name == "sessions":
                return parent.parent
    return (Path.home() / ".codex").resolve()


def _resolve_transcript(
    *,
    home: Path,
    session_id: str,
    transcript_hint: Path | None,
) -> Path:
    if transcript_hint is not None:
        transcript = transcript_hint.expanduser().resolve()
        allowed_roots = {home, (Path.home() / ".codex").resolve()}
        if not any(transcript.is_relative_to(root) for root in allowed_roots):
            raise HookError(
                "Codex hook transcript is outside a recognized provider home"
            )
        if not transcript.is_file():
            raise HookError("Codex hook transcript does not exist")
        return transcript

    session_roots = {home / "sessions", Path.home() / ".codex" / "sessions"}
    matches = sorted(
        path
        for sessions_dir in session_roots
        if sessions_dir.is_dir()
        for path in sessions_dir.rglob(f"*{session_id}*.jsonl")
    )
    if len(matches) != 1:
        raise HookError(
            "Codex hook session must resolve to exactly one transcript "
            f"(found {len(matches)})"
        )
    return matches[0].resolve()


def _validate_transcript_session(path: Path, *, session_id: str) -> None:
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict) or event.get("type") != "session_meta":
                continue
            payload = event.get("payload")
            if not isinstance(payload, dict):
                break
            transcript_session_id = payload.get("id") or payload.get("session_id")
            if transcript_session_id != session_id:
                raise HookError("Codex hook session does not match its transcript")
            return
    raise HookError("Codex hook transcript is missing session metadata")


def _latest_rate_limits(path: Path) -> tuple[str, Mapping[str, Any]]:
    for line in _iter_lines_reverse(path):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict) or event.get("type") != "event_msg":
            continue
        payload = event.get("payload")
        if not isinstance(payload, dict) or payload.get("type") != "token_count":
            continue
        rate_limits = payload.get("rate_limits")
        observed_at = event.get("timestamp")
        if isinstance(rate_limits, dict) and isinstance(observed_at, str):
            return observed_at, rate_limits
    raise HookError("Codex hook transcript has no quota snapshot")


def _normalize_rate_limits(rate_limits: Mapping[str, Any]) -> dict[str, Any]:
    primary = _normalize_window(rate_limits.get("primary"), window="primary")
    secondary = _normalize_window(rate_limits.get("secondary"), window="secondary")
    if primary is None and secondary is None:
        raise HookError("Codex hook quota snapshot has no supported windows")
    return {
        "limitId": _optional_string(rate_limits.get("limit_id")),
        "primary": primary,
        "secondary": secondary,
    }


def _normalize_window(value: object, *, window: str) -> dict[str, int] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise HookError(f"Codex hook {window} quota window must be an object")
    return {
        "usedPercent": _required_integral_number(
            value.get("used_percent"), field=f"{window}.used_percent"
        ),
        "windowDurationMins": _required_integral_number(
            value.get("window_minutes"), field=f"{window}.window_minutes"
        ),
        "resetsAt": _required_integral_number(
            value.get("resets_at"), field=f"{window}.resets_at"
        ),
    }


def _resolve_account(home: Path) -> str:
    method = CodexAuthMethod()
    auth_data = method.read_auth_data(home)
    if auth_data is None:
        raise HookError("Codex quota reporting requires readable home auth data")
    identity = method.extract_identity(auth_data)
    if identity is None:
        raise HookError("Codex quota reporting could not identify the provider account")
    account = auth_registry.resolve_account_by_identity("codex", identity)
    if account is None:
        raise HookError("Codex quota reporting could not resolve a registered account")
    return account


def _iter_lines_reverse(path: Path, *, chunk_size: int = 8192) -> Iterator[str]:
    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        position = handle.tell()
        buffer = b""
        while position > 0:
            read_size = min(chunk_size, position)
            position -= read_size
            handle.seek(position)
            data = handle.read(read_size)
            parts = (data + buffer).split(b"\n")
            buffer = parts[0]
            for line in reversed(parts[1:]):
                if line:
                    yield line.decode("utf-8")
        if buffer:
            yield buffer.decode("utf-8")


def _required_integral_number(value: object, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise HookError(f"Codex hook {field} must be an integer")
    if int(value) != value:
        raise HookError(f"Codex hook {field} must be an integer")
    return int(value)


def _required_string(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HookError(f"Codex hook {field} must be a nonempty string")
    return value.strip()


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _optional_path(value: object) -> Path | None:
    return Path(value) if isinstance(value, str) and value.strip() else None


__all__ = [
    "CODEX_SESSION_HOOK_USAGE_SOURCE",
    "register_codex_usage_hook_callbacks",
    "report_codex_quota_from_hook",
]
