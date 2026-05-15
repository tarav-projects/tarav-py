from __future__ import annotations

import datetime
import hashlib
import json
import os
import pty
import re
import select
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from agentos._core.errors import CliError
from agentos._core.process import run_process
from agentos._core.project import agentos_home_dir
from agentos.agent.account_registry import load_account, load_links
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
from agentos.agent.usage_registry import append_usage_record


DEFAULT_USAGE_STATUS_TIMEOUT_SEC = 45
DEFAULT_USAGE_GET_TIMEOUT_SEC = 5
CLAUDE_USAGE_GET_CACHE_MAX_AGE_SEC = 300
CLAUDE_USAGE_GET_STALE_FALLBACK_MAX_AGE_SEC = 3600
CLAUDE_USAGE_API_URL = "https://api.anthropic.com/api/oauth/usage"
CLAUDE_OAUTH_BETA_HEADER = "oauth-2025-04-20"
CLAUDE_CREDENTIALS_SERVICE_SUFFIX = "-credentials"
CLAUDE_STATUSLINE_CACHE_MAX_AGE_SEC = 60
CLAUDE_STATUSLINE_STALE_FALLBACK_MAX_AGE_SEC = 600
CLAUDE_USAGE_REFRESH_PROMPT = "Reply with OK."
CLAUDE_USAGE_REFRESH_MODEL = "haiku"
CLAUDE_REFRESH_TRUST_CONFIRM_DELAY_SEC = 0.75
CLAUDE_REFRESH_TRUST_CONFIRM_RETRY_SEC = 0.75
CLAUDE_REFRESH_PROMPT_FALLBACK_DELAY_SEC = 2.5
CLAUDE_REFRESH_INTERRUPT_SETTLE_SEC = 0.05
CLAUDE_REFRESH_TERMINATE_WAIT_SEC = 0.5

_ANSI_CSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_ANSI_OSC_RE = re.compile(r"\x1b\].*?(?:\x07|\x1b\\)", re.DOTALL)
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def _claude_account_status_impl(
    agent: Agent,
    *,
    record_usage: bool = True,
) -> AccountStatus:
    if agent.account is None:
        raise CliError("claude-code account_status requires an agent account context")
    if agent.home is None:
        raise CliError("claude-code account_status requires an agent home")

    account_record = load_account(agent.provider, agent.account.account)
    expected_identity = _expected_identity(account_record)
    home_config = _load_home_config(agent.home)
    fetched_identity = _fetched_identity_from_home_config(home_config)
    link = _linked_home_record(agent)
    link_state = _link_state(link=link, agent=agent)
    errors = list(_setup_errors(agent=agent, link_state=link_state, link=link))
    identity_match = _identity_match(expected_identity, fetched_identity)
    if identity_match == "mismatched":
        errors.append(
            AccountStatusError(
                error_type="identity_mismatch",
                message=(
                    "claude-code home identity does not match registered account "
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
        usage_payload: dict[str, Any] | None = None
    else:
        limits, usage_errors, usage_payload = _account_usage_GET(agent)
        usage_status = "error" if usage_errors else "ok"
        usage_summary = _limits_summary(limits) if limits else None
        auth_summary = "Claude usage API read" if usage_status == "ok" else None
        if (
            record_usage
            and usage_status == "ok"
            and limits
            and usage_payload is not None
            and _usage_get_cache_status(usage_payload) == "live"
        ):
            append_usage_record(
                provider=agent.provider,
                account=agent.account.account,
                home=agent.home,
                source="oauth_usage_get",
                payload=_usage_get_provider_payload(usage_payload),
            )

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
            "link": link,
            "oauth_account": (
                home_config.get("oauthAccount")
                if isinstance(home_config, dict)
                else None
            ),
            "usage": usage_payload,
        },
    )


def _expected_identity(account_record: dict[str, object]) -> AccountIdentity:
    return AccountIdentity(
        email=_string_or_none(account_record.get("email")),
        label=_string_or_none(account_record.get("label")),
        raw=account_record,
    )


def _load_home_config(home: Path) -> dict[str, object] | None:
    path = home / ".claude.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _fetched_identity_from_home_config(
    home_config: Mapping[str, object] | None,
) -> AccountIdentity | None:
    if home_config is None:
        return None
    oauth_account = home_config.get("oauthAccount")
    if not isinstance(oauth_account, dict):
        return None
    return AccountIdentity(
        provider_account_id=_string_or_none(oauth_account.get("accountUuid")),
        email=_string_or_none(oauth_account.get("emailAddress")),
        label=_string_or_none(oauth_account.get("displayName")),
        raw=oauth_account,
    )


def _identity_match(
    expected_identity: AccountIdentity,
    fetched_identity: AccountIdentity | None,
) -> AccountIdentityMatch:
    if fetched_identity is None:
        return "unavailable"
    if expected_identity.email is None or fetched_identity.email is None:
        return "unknown"
    if expected_identity.email == fetched_identity.email:
        return "verified"
    return "mismatched"


def _linked_home_record(agent: Agent) -> dict[str, object] | None:
    assert agent.home is not None
    links = load_links(agent.provider).get("links")
    if not isinstance(links, dict):
        return None
    link = links.get(str(agent.home.expanduser().resolve()))
    return link if isinstance(link, dict) else None


def _link_state(*, link: dict[str, object] | None, agent: Agent) -> str:
    if link is None:
        return "unlinked"
    if link.get("kind") != "claimed":
        return "unsupported-link"
    if agent.account is None or link.get("account") != agent.account.account:
        return "mismatched"
    return "claimed-unverified"


def _setup_errors(
    *,
    agent: Agent,
    link_state: str,
    link: dict[str, object] | None,
) -> tuple[AccountStatusError, ...]:
    errors: list[AccountStatusError] = []
    if agent.home is None:
        errors.append(
            AccountStatusError(
                error_type="home_missing",
                message="claude-code account_status requires an agent home",
            )
        )
        return tuple(errors)
    if not agent.home.exists():
        errors.append(
            AccountStatusError(
                error_type="home_missing",
                message=f"claude-code account home does not exist: {agent.home}",
            )
        )
    if link_state != "claimed-unverified":
        errors.append(
            AccountStatusError(
                error_type="home_link_unusable",
                message=f"claude-code account home link is not usable: {link_state}",
                detail={
                    "link_state": link_state,
                    "home": str(agent.home),
                    "link": link,
                },
            )
        )
    return tuple(errors)


# Claude usage data has multiple possible sources. Keep each implementation
# isolated while we evaluate which one should become the long-term capability.
def _account_usage_GET(
    agent: Agent,
) -> tuple[tuple[AccountLimit, ...], tuple[AccountStatusError, ...], dict[str, Any] | None]:
    cached_payload = _load_cached_claude_usage_get_payload(
        agent,
        max_age_sec=CLAUDE_USAGE_GET_CACHE_MAX_AGE_SEC,
    )
    if cached_payload is not None:
        return _parse_claude_usage_get_limits(cached_payload), (), cached_payload

    try:
        payload = _fetch_claude_usage_payload(agent)
        _write_cached_claude_usage_get_payload(agent, payload)
        return (
            _parse_claude_usage_get_limits(payload),
            (),
            _with_usage_get_cache_metadata(payload, cache_status="live"),
        )
    except AccountStatusError as exc:
        cached_payload = _load_cached_claude_usage_get_payload(
            agent,
            max_age_sec=CLAUDE_USAGE_GET_STALE_FALLBACK_MAX_AGE_SEC,
            stale_error=exc,
        )
        if cached_payload is not None:
            return _parse_claude_usage_get_limits(cached_payload), (), cached_payload
        return (), (exc,), None
    except (CliError, json.JSONDecodeError, TypeError, ValueError) as exc:
        return (), (AccountStatusError(error_type="invalid_output", message=str(exc)),), None


def _account_usage_statusline(
    agent: Agent,
) -> tuple[tuple[AccountLimit, ...], tuple[AccountStatusError, ...], dict[str, Any] | None]:
    try:
        payload = _collect_claude_statusline_payload(agent)
        return _parse_claude_statusline_rate_limits(payload), (), payload
    except AccountStatusError as exc:
        cached_payload = _load_cached_claude_statusline_payload(
            agent,
            max_age_sec=CLAUDE_STATUSLINE_STALE_FALLBACK_MAX_AGE_SEC,
        )
        if cached_payload is not None:
            cached_payload = dict(cached_payload)
            cached_payload["agentos_cache"] = {
                "stale_fallback": True,
                "live_error": exc.summary(),
            }
            return _parse_claude_statusline_rate_limits(cached_payload), (), cached_payload
        return (), (exc,), None
    except (CliError, json.JSONDecodeError, TypeError, ValueError) as exc:
        return (), (AccountStatusError(error_type="invalid_output", message=str(exc)),), None


def _fetch_claude_usage_payload(agent: Agent) -> dict[str, Any]:
    access_token = _claude_oauth_access_token(agent)
    timeout_sec = agent.timeout_sec or DEFAULT_USAGE_GET_TIMEOUT_SEC
    request = urllib.request.Request(
        CLAUDE_USAGE_API_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "anthropic-beta": CLAUDE_OAUTH_BETA_HEADER,
            "Content-Type": "application/json",
            "User-Agent": "claude-cli/agentos",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_sec) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = _read_http_error_detail(exc)
        raise AccountStatusError(
            error_type="usage_api_http_error",
            message=f"claude usage API returned HTTP {exc.code}",
            detail=detail,
            exit_code=exc.code,
        ) from exc
    except TimeoutError as exc:
        raise AccountStatusError(
            error_type="timeout",
            message=f"claude usage API timed out after {timeout_sec} seconds",
        ) from exc
    except OSError as exc:
        raise AccountStatusError(
            error_type="usage_api_failed",
            message=str(exc),
        ) from exc
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise CliError("claude usage API response must be a JSON object")
    return payload


def _load_cached_claude_usage_get_payload(
    agent: Agent,
    *,
    max_age_sec: int,
    stale_error: AccountStatusError | None = None,
) -> dict[str, Any] | None:
    cache_path = _claude_usage_get_cache_path(agent)
    if not cache_path.is_file():
        return None
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(cache, dict):
        return None
    captured_at = cache.get("captured_at_epoch")
    payload = cache.get("payload")
    if not isinstance(captured_at, int | float) or not isinstance(payload, dict):
        return None
    age_sec = time.time() - float(captured_at)
    if age_sec < 0 or age_sec > max_age_sec:
        return None
    cache_status = "stale_fallback" if stale_error is not None else "fresh"
    return _with_usage_get_cache_metadata(
        payload,
        cache_status=cache_status,
        captured_at_epoch=float(captured_at),
        age_sec=age_sec,
        stale_error=stale_error,
    )


def _write_cached_claude_usage_get_payload(agent: Agent, payload: dict[str, Any]) -> None:
    cache_path = _claude_usage_get_cache_path(agent)
    now = time.time()
    cache = {
        "schema_version": 1,
        "provider": agent.provider,
        "account": _account_name(agent),
        "method": "oauth_usage_get",
        "captured_at_epoch": now,
        "captured_at": _iso_from_epoch_seconds(int(now)),
        "payload": payload,
    }
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = cache_path.parent / f".{cache_path.name}.agentos-tmp-{os.getpid()}"
    temp_path.write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp_path, cache_path)


def _claude_usage_get_cache_path(agent: Agent) -> Path:
    return (
        agentos_home_dir()
        / "cache"
        / "account-status"
        / agent.provider
        / _account_name(agent)
        / "oauth_usage_get.json"
    )


def _with_usage_get_cache_metadata(
    payload: Mapping[str, Any],
    *,
    cache_status: str,
    captured_at_epoch: float | None = None,
    age_sec: float | None = None,
    stale_error: AccountStatusError | None = None,
) -> dict[str, Any]:
    payload_with_metadata = dict(payload)
    metadata: dict[str, object] = {
        "method": "oauth_usage_get",
        "status": cache_status,
    }
    if captured_at_epoch is not None:
        metadata["captured_at_epoch"] = captured_at_epoch
        metadata["captured_at"] = _iso_from_epoch_seconds(int(captured_at_epoch))
    if age_sec is not None:
        metadata["age_sec"] = round(age_sec, 3)
    if stale_error is not None:
        metadata["live_error"] = stale_error.summary()
    payload_with_metadata["agentos_cache"] = metadata
    return payload_with_metadata


def _usage_get_cache_status(payload: Mapping[str, Any]) -> str | None:
    metadata = payload.get("agentos_cache")
    if not isinstance(metadata, dict):
        return None
    status = metadata.get("status")
    return status if isinstance(status, str) else None


def _usage_get_provider_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    provider_payload = dict(payload)
    provider_payload.pop("agentos_cache", None)
    return provider_payload


def _account_name(agent: Agent) -> str:
    if agent.account is None:
        raise AccountStatusError(
            error_type="account_missing",
            message="claude-code account_status requires an agent account context",
        )
    return agent.account.account


def _claude_oauth_access_token(agent: Agent) -> str:
    if agent.home is None:
        raise AccountStatusError(
            error_type="home_missing",
            message="claude-code account_status requires an agent home",
        )
    storage_data = _read_claude_secure_storage(agent.home)
    oauth_data = storage_data.get("claudeAiOauth")
    if not isinstance(oauth_data, dict):
        raise AccountStatusError(
            error_type="oauth_token_missing",
            message="claude-code OAuth token is not available in secure storage",
        )
    access_token = oauth_data.get("accessToken")
    if not isinstance(access_token, str) or not access_token:
        raise AccountStatusError(
            error_type="oauth_token_missing",
            message="claude-code OAuth access token is missing",
        )
    return access_token


def _read_claude_secure_storage(home: Path) -> dict[str, Any]:
    if sys.platform == "darwin":
        keychain_data = _read_claude_keychain_storage(home)
        if keychain_data is not None:
            return keychain_data
    credentials_path = home / ".credentials.json"
    if credentials_path.is_file():
        try:
            payload = json.loads(credentials_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AccountStatusError(
                error_type="oauth_storage_invalid",
                message=f"invalid claude-code credentials file: {exc}",
            ) from exc
        if isinstance(payload, dict):
            return payload
    raise AccountStatusError(
        error_type="oauth_storage_missing",
        message="claude-code OAuth secure storage was not found",
    )


def _read_claude_keychain_storage(home: Path) -> dict[str, Any] | None:
    for service_name in _claude_keychain_service_names(home):
        result = run_process(
            (
                "security",
                "find-generic-password",
                "-a",
                os.environ.get("USER", ""),
                "-s",
                service_name,
                "-w",
            ),
            mode="capture",
            timeout_sec=DEFAULT_USAGE_GET_TIMEOUT_SEC,
        )
        if result.exit_code != 0:
            continue
        raw = result.stdout or ""
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _claude_keychain_service_names(home: Path) -> tuple[str, ...]:
    home_hash = hashlib.sha256(str(home).encode("utf-8")).hexdigest()[:8]
    return (
        f"Claude Code{CLAUDE_CREDENTIALS_SERVICE_SUFFIX}-{home_hash}",
        f"Claude Code{CLAUDE_CREDENTIALS_SERVICE_SUFFIX}",
    )


def _read_http_error_detail(exc: urllib.error.HTTPError) -> dict[str, object]:
    try:
        body = exc.read().decode("utf-8")
    except OSError:
        body = ""
    detail: dict[str, object] = {"status": exc.code}
    if body:
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            detail["body"] = body[:500]
        else:
            detail["body"] = parsed
    return detail


def _collect_claude_statusline_payload(agent: Agent) -> dict[str, Any]:
    cached_payload = _load_cached_claude_statusline_payload(
        agent,
        max_age_sec=CLAUDE_STATUSLINE_CACHE_MAX_AGE_SEC,
    )
    if cached_payload is not None:
        return cached_payload

    timeout_sec = max(agent.timeout_sec or DEFAULT_USAGE_STATUS_TIMEOUT_SEC, DEFAULT_USAGE_STATUS_TIMEOUT_SEC)
    workspace_root = _claude_statusline_workspace(agent)
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

        payload = _run_claude_statusline_refresh_session(
            agent,
            cwd=workspace_root,
            capture_path=capture_path,
            settings_path=settings_path,
            timeout_sec=timeout_sec,
        )
    _write_cached_claude_statusline_payload(agent=agent, statusline_payload=payload)
    _cleanup_claude_statusline_transcript(agent=agent, statusline_payload=payload)
    return payload


def _claude_statusline_workspace(agent: Agent) -> Path:
    if agent.home is None:
        raise AccountStatusError(
            error_type="home_missing",
            message="claude-code account_status requires an agent home",
        )
    return agent.home / "agentos" / "workspaces" / "statusline-refresh"


def _claude_statusline_cache_path(agent: Agent) -> Path:
    if agent.home is None:
        raise AccountStatusError(
            error_type="home_missing",
            message="claude-code account_status requires an agent home",
        )
    return agent.home / "agentos" / "cache" / "statusline-rate-limits.json"


def _load_cached_claude_statusline_payload(
    agent: Agent,
    *,
    max_age_sec: int,
) -> dict[str, Any] | None:
    cache_path = _claude_statusline_cache_path(agent)
    if not cache_path.is_file():
        return None
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    try:
        captured_at = _optional_float(
            payload.get("captured_at_epoch"),
            field_name="claude statusLine cache captured_at_epoch",
        )
    except CliError:
        return None
    if captured_at is None or time.time() - captured_at > max_age_sec:
        return None
    statusline_payload = payload.get("statusline")
    if not isinstance(statusline_payload, dict):
        return None
    rate_limits = statusline_payload.get("rate_limits")
    if not isinstance(rate_limits, dict) or not rate_limits:
        return None
    return statusline_payload


def _write_cached_claude_statusline_payload(
    *, agent: Agent, statusline_payload: Mapping[str, Any]
) -> None:
    cache_path = _claude_statusline_cache_path(agent)
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(
                {
                    "captured_at_epoch": time.time(),
                    "statusline": dict(statusline_payload),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    except OSError:
        return


def _run_claude_statusline_refresh_session(
    agent: Agent,
    *,
    cwd: Path,
    capture_path: Path,
    settings_path: Path,
    timeout_sec: int,
) -> dict[str, Any]:
    command = agent.build_command(
        AgentCommandConfig(
            argv=(
                "--disable-slash-commands",
                "--setting-sources",
                "local",
                "--settings",
                str(settings_path),
            ),
            model=CLAUDE_USAGE_REFRESH_MODEL,
            interaction_mode="interactive",
        )
    )
    env = _process_environment(command.env_overrides)
    env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] = "1"
    env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"

    try:
        master_fd, slave_fd = pty.openpty()
        process = subprocess.Popen(
            command.argv,
            cwd=str(cwd),
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            env=env,
            text=False,
            close_fds=True,
        )
    except FileNotFoundError as exc:
        raise AccountStatusError(error_type="command_not_found", message=str(exc)) from exc
    except OSError as exc:
        raise AccountStatusError(error_type="command_failed", message=str(exc)) from exc
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
                raise AccountStatusError(
                    error_type="timeout",
                    message=(
                        "provider command timed out after "
                        f"{timeout_sec} seconds using model {CLAUDE_USAGE_REFRESH_MODEL}"
                    ),
                    detail={
                        "model": CLAUDE_USAGE_REFRESH_MODEL,
                        "home": str(agent.home) if agent.home is not None else None,
                    },
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
                _write_pty(master_fd, (CLAUDE_USAGE_REFRESH_PROMPT + "\r").encode("utf-8"))
                prompt_sent = True

            if (
                not prompt_sent
                and not _claude_refresh_trust_prompt_visible(transcript_text)
                and ((not trust_prompt_seen and now >= prompt_fallback_at) or trust_confirm_sent)
            ):
                _write_pty(master_fd, (CLAUDE_USAGE_REFRESH_PROMPT + "\r").encode("utf-8"))
                prompt_sent = True

            statusline_payload = _load_claude_statusline_capture(capture_path)
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
        raise AccountStatusError(
            error_type="command_failed",
            message=transcript or f"provider command exited with code {process.returncode}",
            exit_code=process.returncode,
        )
    raise AccountStatusError(
        error_type="invalid_output",
        message="provider command did not emit a statusLine payload with rate_limits",
    )


def _load_claude_statusline_capture(capture_path: Path) -> dict[str, Any] | None:
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


def _parse_claude_usage_get_limits(payload: Mapping[str, Any]) -> tuple[AccountLimit, ...]:
    limits: list[AccountLimit] = []
    for limit_type in ("five_hour", "seven_day"):
        raw_limit = payload.get(limit_type)
        if raw_limit is None:
            continue
        if not isinstance(raw_limit, dict):
            raise CliError(f"claude {limit_type} usage payload must be an object")
        limits.append(_parse_claude_usage_get_limit(limit_type, raw_limit))
    if not limits:
        raise CliError("claude usage API payload has no supported limits")
    return tuple(limits)


def _parse_claude_usage_get_limit(
    limit_type: str,
    raw_limit: Mapping[str, Any],
) -> AccountLimit:
    utilization = _optional_float(
        raw_limit.get("utilization"),
        field_name=f"claude {limit_type} utilization",
    )
    used_percent = round(utilization) if utilization is not None else None
    resets_at = _string_or_none(raw_limit.get("resets_at"))
    period_duration_mins = _claude_rate_limit_duration_mins(limit_type)
    period_started_at, period_ends_at = _period_bounds_from_reset_iso(
        resets_at=resets_at,
        period_duration_mins=period_duration_mins,
    )
    return AccountLimit(
        limit_class="usage_over_time",
        limit_name=_claude_rate_limit_name(limit_type),
        limit_label=_claude_rate_limit_label(limit_type),
        usage_over_time=UsageOverTimeLimitData(
            used_percent=used_percent,
            period_started_at=period_started_at,
            period_ends_at=period_ends_at,
            period_duration_mins=period_duration_mins,
            resets_at=_normalize_iso_datetime(resets_at),
        ),
        provider_limit={
            "limit_type": limit_type,
        },
    )


def _parse_claude_statusline_rate_limits(payload: Mapping[str, Any]) -> tuple[AccountLimit, ...]:
    raw_rate_limits = payload.get("rate_limits")
    if not isinstance(raw_rate_limits, dict) or not raw_rate_limits:
        raise CliError("claude statusLine payload is missing rate_limits")

    limits: list[AccountLimit] = []
    for limit_type in ("five_hour", "seven_day"):
        raw_limit = raw_rate_limits.get(limit_type)
        if raw_limit is None:
            continue
        if not isinstance(raw_limit, dict):
            raise CliError(f"claude {limit_type} rate limit payload must be an object")
        limits.append(_parse_claude_statusline_limit(limit_type, raw_limit))
    if not limits:
        raise CliError("claude statusLine payload has no supported rate_limits")
    return tuple(limits)


def _parse_claude_statusline_limit(
    limit_type: str,
    raw_limit: Mapping[str, Any],
) -> AccountLimit:
    used_percentage = _optional_float(
        raw_limit.get("used_percentage"),
        field_name=f"claude {limit_type} used_percentage",
    )
    used_percent = round(used_percentage) if used_percentage is not None else None
    resets_at_epoch = _optional_int(
        raw_limit.get("resets_at"),
        field_name=f"claude {limit_type} resets_at",
    )
    period_duration_mins = _claude_rate_limit_duration_mins(limit_type)
    period_started_at, period_ends_at = _period_bounds_from_reset(
        resets_at_epoch=resets_at_epoch,
        period_duration_mins=period_duration_mins,
    )
    return AccountLimit(
        limit_class="usage_over_time",
        limit_name=_claude_rate_limit_name(limit_type),
        limit_label=_claude_rate_limit_label(limit_type),
        usage_over_time=UsageOverTimeLimitData(
            used_percent=used_percent,
            period_started_at=period_started_at,
            period_ends_at=period_ends_at,
            period_duration_mins=period_duration_mins,
            resets_at=_iso_from_epoch_seconds(resets_at_epoch),
        ),
        provider_limit={
            "limit_type": limit_type,
        },
    )


def _claude_rate_limit_name(limit_type: str) -> str:
    if limit_type == "five_hour":
        return "burst"
    if limit_type == "seven_day":
        return "weekly"
    return limit_type


def _claude_rate_limit_label(limit_type: str) -> str:
    if limit_type == "five_hour":
        return "Burst"
    if limit_type == "seven_day":
        return "Weekly"
    return limit_type


def _claude_rate_limit_duration_mins(limit_type: str) -> int | None:
    if limit_type == "five_hour":
        return 300
    if limit_type == "seven_day":
        return 10_080
    return None


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


def _period_bounds_from_reset_iso(
    *,
    resets_at: str | None,
    period_duration_mins: int | None,
) -> tuple[str | None, str | None]:
    if resets_at is None or period_duration_mins is None:
        return (None, None)
    reset_at = _parse_iso_datetime(resets_at)
    if reset_at is None:
        return (None, _normalize_iso_datetime(resets_at))
    period_started_at = reset_at - datetime.timedelta(minutes=period_duration_mins)
    return (
        _datetime_to_iso(period_started_at),
        _datetime_to_iso(reset_at),
    )


def _iso_from_epoch_seconds(epoch_seconds: int | None) -> str | None:
    if epoch_seconds is None:
        return None
    return datetime.datetime.fromtimestamp(
        epoch_seconds,
        tz=datetime.timezone.utc,
    ).isoformat().replace("+00:00", "Z")


def _normalize_iso_datetime(value: str | None) -> str | None:
    parsed = _parse_iso_datetime(value)
    if parsed is None:
        return value
    return _datetime_to_iso(parsed)


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
        return parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed.astimezone(datetime.timezone.utc)


def _datetime_to_iso(value: datetime.datetime) -> str:
    return value.astimezone(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _optional_int(value: object, *, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise CliError(f"{field_name} must be an integer")
    return value


def _optional_float(value: object, *, field_name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise CliError(f"{field_name} must be a number")
    return float(value)


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
        except (BlockingIOError, OSError):
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
        or "haiku" in text
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


def _cleanup_claude_statusline_transcript(
    *, agent: Agent, statusline_payload: Mapping[str, Any]
) -> None:
    if agent.home is None:
        return
    transcript_path_value = _string_or_none(statusline_payload.get("transcript_path"))
    if transcript_path_value is None:
        return
    transcript_path = Path(transcript_path_value)
    claude_projects_root = agent.home / "projects"
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


def _process_environment(env_overrides: Mapping[str, str]) -> dict[str, str]:
    env = os.environ.copy()
    env.update(env_overrides)
    return env


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


__all__: list[str] = []
