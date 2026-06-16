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
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentos._core.errors import CliError
from agentos._core.path_validation import validate_string_for_path
from agentos._core.project import agentos_home_dir
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
from agentos.agent.primitives import AgentConfig
from agentos.agent.run_runtime import AgentCommandConfig
from agentos.agent.usage_registry import append_usage_record
from agentos.claude.account_registry import (
    CLAUDE_AUTH_KIND,
    promote_verified_claude_ambient_auth_from_home,
    read_claude_secure_storage,
)


DEFAULT_USAGE_STATUS_TIMEOUT_SEC = 45
DEFAULT_USAGE_GET_TIMEOUT_SEC = 5
CLAUDE_USAGE_API_URL = "https://api.anthropic.com/api/oauth/usage"
CLAUDE_USAGE_GET_SOURCE = "oauth_usage_get"
CLAUDE_STATUSLINE_USAGE_SOURCE = "statusline_rate_limits"
CLAUDE_USAGE_GET_THROTTLE_SCHEMA_VERSION = 1
CLAUDE_USAGE_GET_THROTTLE_MARGIN_SEC = 300
CLAUDE_OAUTH_BETA_HEADER = "oauth-2025-04-20"
CLAUDE_USAGE_REFRESH_PROMPT = "Reply with OK."
CLAUDE_USAGE_REFRESH_MODEL = "haiku"
CLAUDE_REFRESH_TRUST_CONFIRM_DELAY_SEC = 0.75
CLAUDE_REFRESH_TRUST_CONFIRM_RETRY_SEC = 0.75
CLAUDE_REFRESH_PROMPT_FALLBACK_DELAY_SEC = 2.5
CLAUDE_REFRESH_INTERRUPT_SETTLE_SEC = 0.05
CLAUDE_REFRESH_TERMINATE_WAIT_SEC = 0.5
CLAUDE_STATUSLINE_PROMPT_SUBMIT_BYTES = b"\r\n"
CLAUDE_STATUSLINE_TRANSCRIPT_TAIL_CHARS = 4_000
CLAUDE_STATUSLINE_PARENT_ENV_ALLOWLIST = frozenset(
    {
        "HOME",
        "LANG",
        "LOGNAME",
        "PATH",
        "SHELL",
        "SSH_AUTH_SOCK",
        "TERM",
        "TMPDIR",
        "USER",
    }
)
CLAUDE_STATUSLINE_LAST_RUN_LOG_FILENAME = "claude-statusline-last-run.json"

_ANSI_CSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_ANSI_OSC_RE = re.compile(r"\x1b\].*?(?:\x07|\x1b\\)", re.DOTALL)
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


@dataclass
class _ClaudeStatusLineRunLog:
    agent: AgentConfig
    argv: tuple[str, ...]
    cwd: Path
    capture_path: Path
    settings_path: Path
    timeout_sec: int
    env: Mapping[str, str]
    started_at_monotonic: float
    events: list[dict[str, object]] = field(default_factory=list)
    prompt_sent: bool = False
    trust_prompt_seen: bool = False
    trust_confirm_sent: bool = False
    process_returncode: int | None = None
    transcript_text: str = ""
    normalized_transcript_text: str = ""
    statusline_payload: Mapping[str, Any] | None = None
    invalid_capture_payload: Mapping[str, Any] | None = None
    invalid_capture_error: str | None = None
    error: Mapping[str, Any] | None = None


def _claude_account_status_impl(
    agent: AgentConfig,
    *,
    record_usage: bool = True,
    fallback_to_usage_registry: bool = True,
) -> AccountStatus:
    if agent.account is None:
        raise CliError("claude-code account_status requires an agent account context")
    if agent.home is None:
        raise CliError("claude-code account_status requires an agent home")

    account_record = load_account(agent.provider, agent.account.account)
    expected_identity = _expected_identity(account_record)
    home_config = _load_home_config(agent.home)
    fetched_identity = _fetched_identity_from_home_config(home_config)
    auth_state = "home-config" if home_config is not None else "home-missing-config"
    errors = list(_setup_errors(agent=agent))
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
    auth_artifact_record: dict[str, object] | None = None
    if check_status == "error":
        usage_status = "unavailable"
        usage_summary = None
        limits: tuple[AccountLimit, ...] = ()
        usage_errors: tuple[AccountStatusError, ...] = ()
        usage_payload: dict[str, Any] | None = None
    else:
        (
            limits,
            usage_errors,
            usage_payload,
            usage_record_payload,
            usage_record_metadata,
        ) = _account_usage_statusline(agent, cleanup_transcript=False)
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
                account=_account_name(agent),
                home=agent.home,
                source=CLAUDE_STATUSLINE_USAGE_SOURCE,
                parser=_parse_claude_statusline_rate_limits,
                live_error=live_error,
                fallback_to_usage_registry=fallback_to_usage_registry,
            )
        usage_status = "error" if usage_errors else "ok"
        usage_summary = _limits_summary(limits) if limits else None
        auth_summary = _usage_auth_summary(usage_record_metadata, usage_status=usage_status)
        if record_usage and usage_status == "ok" and limits and usage_record_payload is not None:
            append_usage_record(
                provider=agent.provider,
                account=agent.account.account,
                home=agent.home,
                source=_usage_record_source(usage_record_metadata)
                or CLAUDE_STATUSLINE_USAGE_SOURCE,
                payload=usage_record_payload,
            )
        auth_artifact_record = _refresh_claude_ambient_auth_artifact(
            agent,
            account_record=account_record,
            usage_status=usage_status,
            usage_record_metadata=usage_record_metadata,
        )

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
            "oauth_account": (
                home_config.get("oauthAccount")
                if isinstance(home_config, dict)
                else None
            ),
            "usage": usage_payload,
            "usage_record": usage_record_metadata,
            "auth_artifact_record": auth_artifact_record,
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


def _setup_errors(
    *,
    agent: AgentConfig,
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
    return tuple(errors)


# Claude usage data has multiple possible sources. Keep each implementation
# isolated while we evaluate which one should become the long-term capability.
def _account_usage_GET(
    agent: AgentConfig,
) -> AccountUsageReadResult:
    throttle_error = _load_claude_usage_get_throttle(agent)
    if throttle_error is not None:
        return (), (throttle_error,), None, None, None

    try:
        payload = _fetch_claude_usage_payload(agent)
        _clear_claude_usage_get_throttle(agent)
        return (
            _parse_claude_usage_get_limits(payload),
            (),
            payload,
            payload,
            fresh_usage_record_metadata(source=CLAUDE_USAGE_GET_SOURCE),
        )
    except AccountStatusError as exc:
        _write_claude_usage_get_throttle(agent, exc)
        return (), (exc,), None, None, None
    except (CliError, OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        return (
            (),
            (AccountStatusError(error_type="invalid_output", message=str(exc)),),
            None,
            None,
            None,
        )


def _usage_record_source(usage_record_metadata: Mapping[str, Any] | None) -> str | None:
    if not isinstance(usage_record_metadata, Mapping):
        return None
    source = usage_record_metadata.get("source")
    return source if isinstance(source, str) and source else None


def _refresh_claude_ambient_auth_artifact(
    agent: AgentConfig,
    *,
    account_record: dict[str, object],
    usage_status: str,
    usage_record_metadata: Mapping[str, Any] | None,
) -> dict[str, object] | None:
    if account_record.get("auth_kind") != CLAUDE_AUTH_KIND:
        return None
    if agent.home is None or agent.account is None:
        return None
    if usage_status != "ok":
        return None
    if _usage_record_source(usage_record_metadata) != CLAUDE_STATUSLINE_USAGE_SOURCE:
        return None
    if (
        isinstance(usage_record_metadata, Mapping)
        and usage_record_metadata.get("status") == USAGE_RECORD_STATUS_REGISTRY_FALLBACK
    ):
        return None
    try:
        payload = promote_verified_claude_ambient_auth_from_home(
            home=agent.home,
            account=agent.account.account,
            source="account.status",
        )
    except CliError as exc:
        return {
            "status": "error",
            "message": str(exc),
        }
    account_payload = payload.get("account_record")
    return {
        "status": "ok",
        "artifact_id": payload.get("artifact_id"),
        "artifact_appended": bool(payload.get("artifact_appended")),
        "active_artifact_id": (
            account_payload.get("active_artifact_id")
            if isinstance(account_payload, dict)
            else None
        ),
    }


def _account_usage_statusline(
    agent: AgentConfig,
    *,
    cleanup_transcript: bool = False,
) -> AccountUsageReadResult:
    try:
        timeout_sec = max(
            agent.timeout_sec or DEFAULT_USAGE_STATUS_TIMEOUT_SEC,
            DEFAULT_USAGE_STATUS_TIMEOUT_SEC,
        )
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
        limits = _parse_claude_statusline_rate_limits(payload)
        if cleanup_transcript:
            try:
                _cleanup_claude_statusline_transcript(
                    agent=agent,
                    statusline_payload=payload,
                )
            except Exception:
                pass
        return (
            limits,
            (),
            payload,
            payload,
            fresh_usage_record_metadata(source=CLAUDE_STATUSLINE_USAGE_SOURCE),
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


def _fetch_claude_usage_payload(agent: AgentConfig) -> dict[str, Any]:
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
        return "Claude usage registry fallback"
    if _usage_record_source(usage_record_metadata) == CLAUDE_STATUSLINE_USAGE_SOURCE:
        return "Claude statusLine read"
    return "Claude usage API read"


def _account_name(agent: AgentConfig) -> str:
    if agent.account is None:
        raise AccountStatusError(
            error_type="account_missing",
            message="claude-code account_status requires an agent account context",
        )
    return agent.account.account


def _claude_usage_get_throttle_path(agent: AgentConfig) -> Path:
    provider = validate_string_for_path(agent.provider, field_name="provider")
    account = validate_string_for_path(_account_name(agent), field_name="account")
    return (
        agentos_home_dir()
        / "cache"
        / "account-status"
        / provider
        / account
        / "oauth_usage_get-throttle.json"
    )


def _load_claude_usage_get_throttle(agent: AgentConfig) -> AccountStatusError | None:
    throttle_path = _claude_usage_get_throttle_path(agent)
    if not throttle_path.is_file():
        return None
    try:
        payload = json.loads(throttle_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or not _claude_usage_get_throttle_matches(agent, payload):
        return None
    retry_after_until = _parse_iso_datetime(_string_or_none(payload.get("retry_after_until")))
    if retry_after_until is None:
        return None
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    remaining_sec = round((retry_after_until - now).total_seconds())
    if remaining_sec <= 0:
        _clear_claude_usage_get_throttle(agent)
        return None
    live_error = payload.get("live_error")
    if not isinstance(live_error, dict):
        return None
    detail = live_error.get("detail")
    detail_payload = dict(detail) if isinstance(detail, Mapping) else {}
    detail_payload["retry_after_remaining_sec"] = remaining_sec
    return AccountStatusError(
        error_type=_string_or_none(live_error.get("type")) or "usage_api_throttled",
        message=_string_or_none(live_error.get("message"))
        or "claude usage API is temporarily throttled",
        exit_code=_optional_error_exit_code(live_error.get("exit_code")),
        detail=detail_payload,
    )


def _write_claude_usage_get_throttle(agent: AgentConfig, error: AccountStatusError) -> None:
    if error.exit_code != 429:
        return
    retry_after_sec = _optional_positive_retry_after_sec(error.detail.get("retry_after_sec"))
    retry_after_until = _string_or_none(error.detail.get("retry_after_until"))
    if retry_after_sec is None or _parse_iso_datetime(retry_after_until) is None:
        return
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    throttle = {
        "schema_version": CLAUDE_USAGE_GET_THROTTLE_SCHEMA_VERSION,
        "provider": agent.provider,
        "account": _account_name(agent),
        "source": CLAUDE_USAGE_GET_SOURCE,
        "reason": "http_429",
        "captured_at": _datetime_to_iso(now),
        "retry_after_sec": retry_after_sec,
        "retry_after_until": retry_after_until,
        "live_error": error.summary(),
    }
    throttle_path = _claude_usage_get_throttle_path(agent)
    throttle_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=throttle_path.parent,
        delete=False,
    ) as handle:
        temp_path = Path(handle.name)
        json.dump(throttle, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(temp_path, throttle_path)


def _clear_claude_usage_get_throttle(agent: AgentConfig) -> None:
    try:
        _claude_usage_get_throttle_path(agent).unlink()
    except FileNotFoundError:
        return


def _claude_usage_get_throttle_matches(agent: AgentConfig, payload: Mapping[str, Any]) -> bool:
    return (
        payload.get("schema_version") == CLAUDE_USAGE_GET_THROTTLE_SCHEMA_VERSION
        and payload.get("provider") == agent.provider
        and payload.get("account") == _account_name(agent)
        and payload.get("source") == CLAUDE_USAGE_GET_SOURCE
        and payload.get("reason") == "http_429"
    )


def _optional_error_exit_code(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _claude_oauth_access_token(agent: AgentConfig) -> str:
    if agent.home is None:
        raise AccountStatusError(
            error_type="home_missing",
            message="claude-code account_status requires an agent home",
        )
    storage_data = read_claude_secure_storage(agent.home)
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


def _read_http_error_detail(exc: urllib.error.HTTPError) -> dict[str, object]:
    try:
        body = exc.read().decode("utf-8")
    except OSError:
        body = ""
    detail: dict[str, object] = {"status": exc.code}
    retry_after_value = exc.headers.get("Retry-After") if exc.headers is not None else None
    retry_after_sec = _parse_retry_after_seconds(retry_after_value)
    if exc.code == 429 and retry_after_sec is not None:
        effective_retry_after_sec = retry_after_sec + CLAUDE_USAGE_GET_THROTTLE_MARGIN_SEC
        retry_after_until = datetime.datetime.now(
            tz=datetime.timezone.utc
        ) + datetime.timedelta(seconds=effective_retry_after_sec)
        detail["retry_after_sec"] = retry_after_sec
        detail["retry_after_margin_sec"] = CLAUDE_USAGE_GET_THROTTLE_MARGIN_SEC
        detail["retry_after_until"] = _datetime_to_iso(retry_after_until)
    if body:
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            detail["body"] = body[:500]
        else:
            detail["body"] = parsed
    return detail


def _parse_retry_after_seconds(value: str | None) -> int | None:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    try:
        retry_after_sec = int(normalized)
    except ValueError:
        return None
    if retry_after_sec <= 0:
        return None
    return retry_after_sec


def _optional_positive_retry_after_sec(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value <= 0:
        return None
    return value


def _claude_statusline_workspace(agent: AgentConfig) -> Path:
    if agent.home is None:
        raise AccountStatusError(
            error_type="home_missing",
            message="claude-code account_status requires an agent home",
        )
    return agent.home / "agentos" / "workspaces" / "statusline-refresh"


def _run_claude_statusline_refresh_session(
    agent: AgentConfig,
    *,
    cwd: Path,
    capture_path: Path,
    settings_path: Path,
    timeout_sec: int,
) -> dict[str, Any]:
    command = agent._build_command(
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
    env = _claude_statusline_process_environment(command.env_overrides)
    started_at = time.monotonic()
    run_log = _ClaudeStatusLineRunLog(
        agent=agent,
        argv=command.argv,
        cwd=cwd,
        capture_path=capture_path,
        settings_path=settings_path,
        timeout_sec=timeout_sec,
        env=env,
        started_at_monotonic=started_at,
    )
    _append_claude_statusline_log_event(run_log, "start")

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
        error = AccountStatusError(error_type="command_not_found", message=str(exc))
        _finalize_claude_statusline_log(run_log, error=error)
        raise error from exc
    except OSError as exc:
        error = AccountStatusError(error_type="command_failed", message=str(exc))
        _finalize_claude_statusline_log(run_log, error=error)
        raise error from exc
    finally:
        if "slave_fd" in locals():
            os.close(slave_fd)

    os.set_blocking(master_fd, False)
    start = started_at
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
                run_log.prompt_sent = prompt_sent
                run_log.trust_prompt_seen = trust_prompt_seen
                run_log.trust_confirm_sent = trust_confirm_sent
                run_log.transcript_text = _decode_terminal_transcript(transcript_chunks)
                run_log.normalized_transcript_text = _normalize_terminal_output(
                    transcript_chunks
                )
                _record_claude_statusline_invalid_capture(run_log)
                error = AccountStatusError(
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
                _finalize_claude_statusline_log(run_log, error=error)
                raise error

            transcript_chunks.extend(_read_pty_chunks(master_fd, timeout_sec=0.25))
            transcript_text = _normalize_terminal_output(transcript_chunks)

            if not prompt_sent and _claude_refresh_trust_prompt_visible(transcript_text):
                trust_prompt_seen = True
                if now >= next_trust_confirm_at:
                    _write_pty(master_fd, b"\r")
                    trust_confirm_sent = True
                    run_log.trust_prompt_seen = trust_prompt_seen
                    run_log.trust_confirm_sent = trust_confirm_sent
                    _append_claude_statusline_log_event(run_log, "trust_confirm_sent")
                    next_trust_confirm_at = now + CLAUDE_REFRESH_TRUST_CONFIRM_RETRY_SEC

            if not prompt_sent and _claude_refresh_main_prompt_visible(transcript_text):
                _write_claude_statusline_prompt(master_fd)
                prompt_sent = True
                run_log.prompt_sent = prompt_sent
                _append_claude_statusline_log_event(
                    run_log,
                    "prompt_sent",
                    prompt_submit_bytes=repr(CLAUDE_STATUSLINE_PROMPT_SUBMIT_BYTES),
                )

            if (
                not prompt_sent
                and not _claude_refresh_trust_prompt_visible(transcript_text)
                and ((not trust_prompt_seen and now >= prompt_fallback_at) or trust_confirm_sent)
            ):
                _write_claude_statusline_prompt(master_fd)
                prompt_sent = True
                run_log.prompt_sent = prompt_sent
                _append_claude_statusline_log_event(
                    run_log,
                    "prompt_fallback_sent",
                    prompt_submit_bytes=repr(CLAUDE_STATUSLINE_PROMPT_SUBMIT_BYTES),
                )

            statusline_payload = _load_claude_statusline_capture(capture_path)
            if statusline_payload is not None:
                run_log.statusline_payload = statusline_payload
                _append_claude_statusline_log_event(run_log, "capture_loaded")
                break
            _record_claude_statusline_invalid_capture(run_log)

            if process.poll() is not None:
                _append_claude_statusline_log_event(run_log, "process_exited")
                break
    finally:
        _terminate_pty_process(process, master_fd)

    run_log.prompt_sent = prompt_sent
    run_log.trust_prompt_seen = trust_prompt_seen
    run_log.trust_confirm_sent = trust_confirm_sent
    run_log.process_returncode = process.returncode
    run_log.transcript_text = _decode_terminal_transcript(transcript_chunks)
    run_log.normalized_transcript_text = _normalize_terminal_output(transcript_chunks)
    run_log.statusline_payload = statusline_payload
    if statusline_payload is None:
        _record_claude_statusline_invalid_capture(run_log)
    if statusline_payload is not None:
        _finalize_claude_statusline_log(run_log, error=None)
        return statusline_payload

    if process.returncode not in (0, None):
        error = AccountStatusError(
            error_type="command_failed",
            message=(
                run_log.transcript_text.strip()
                or f"provider command exited with code {process.returncode}"
            ),
            exit_code=process.returncode,
        )
        _finalize_claude_statusline_log(run_log, error=error)
        raise error
    error = AccountStatusError(
        error_type="invalid_output",
        message="provider command did not emit a statusLine payload with rate_limits",
    )
    _finalize_claude_statusline_log(run_log, error=error)
    raise error


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


def _append_claude_statusline_log_event(
    run_log: _ClaudeStatusLineRunLog,
    event: str,
    **extra: object,
) -> None:
    run_log.events.append(
        {
            "event": event,
            "elapsed_sec": round(time.monotonic() - run_log.started_at_monotonic, 3),
            "capture": _claude_statusline_capture_file_status(run_log.capture_path),
            **extra,
        }
    )


def _finalize_claude_statusline_log(
    run_log: _ClaudeStatusLineRunLog,
    *,
    error: AccountStatusError | None,
) -> None:
    run_log.error = error.summary() if error is not None else None
    payload = {
        "class": "agentos.claude.statusline.last-run-log",
        "schema_version": 1,
        "finished_at": _datetime_to_iso(datetime.datetime.now(tz=datetime.timezone.utc)),
        "elapsed_sec": round(time.monotonic() - run_log.started_at_monotonic, 3),
        "status": "error" if error is not None else "ok",
        "provider": run_log.agent.provider,
        "account": _account_name_or_none(run_log.agent),
        "home": str(run_log.agent.home) if run_log.agent.home is not None else None,
        "cwd": str(run_log.cwd),
        "argv": list(run_log.argv),
        "model": CLAUDE_USAGE_REFRESH_MODEL,
        "timeout_sec": run_log.timeout_sec,
        "env": dict(run_log.env),
        "settings_path": str(run_log.settings_path),
        "capture_path": str(run_log.capture_path),
        "capture": _claude_statusline_capture_file_status(run_log.capture_path),
        "events": run_log.events,
        "state": {
            "prompt_sent": run_log.prompt_sent,
            "trust_prompt_seen": run_log.trust_prompt_seen,
            "trust_confirm_sent": run_log.trust_confirm_sent,
            "process_returncode": run_log.process_returncode,
        },
        "transcript": run_log.transcript_text,
        "transcript_tail": _text_tail(run_log.transcript_text),
        "normalized_transcript_tail": _text_tail(run_log.normalized_transcript_text),
        "statusline_payload": run_log.statusline_payload,
        "invalid_capture_payload": run_log.invalid_capture_payload,
        "invalid_capture_error": run_log.invalid_capture_error,
        "error": run_log.error,
    }
    _write_claude_statusline_last_run_log(payload)


def _write_claude_statusline_last_run_log(payload: Mapping[str, Any]) -> None:
    log_path = _claude_statusline_last_run_log_path()
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=log_path.parent,
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temp_path, log_path)
    except OSError:
        return


def _claude_statusline_last_run_log_path() -> Path:
    return agentos_home_dir() / "logs" / CLAUDE_STATUSLINE_LAST_RUN_LOG_FILENAME


def _claude_statusline_capture_file_status(path: Path) -> dict[str, object]:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return {
            "exists": False,
            "path": str(path),
        }
    except OSError as exc:
        return {
            "exists": False,
            "path": str(path),
            "error": str(exc),
        }
    return {
        "exists": True,
        "path": str(path),
        "size_bytes": stat.st_size,
    }


def _record_claude_statusline_invalid_capture(
    run_log: _ClaudeStatusLineRunLog,
) -> None:
    if run_log.statusline_payload is not None:
        return
    payload, error = _read_claude_statusline_invalid_capture(run_log.capture_path)
    if payload is None and error is None:
        return
    if payload == run_log.invalid_capture_payload and error == run_log.invalid_capture_error:
        return
    run_log.invalid_capture_payload = payload
    run_log.invalid_capture_error = error
    _append_claude_statusline_log_event(
        run_log,
        "capture_rejected",
        invalid_capture_payload=run_log.invalid_capture_payload,
        invalid_capture_error=run_log.invalid_capture_error,
    )


def _read_claude_statusline_invalid_capture(
    capture_path: Path,
) -> tuple[dict[str, Any] | None, str | None]:
    if not capture_path.exists():
        return None, None
    try:
        raw = capture_path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, str(exc)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON: {exc}"
    if not isinstance(payload, dict):
        return None, f"capture payload must be a JSON object, got {type(payload).__name__}"
    rate_limits = payload.get("rate_limits")
    if isinstance(rate_limits, dict) and rate_limits:
        return None, None
    return payload, "capture payload is missing rate_limits"


def _account_name_or_none(agent: AgentConfig) -> str | None:
    if agent.account is None:
        return None
    return agent.account.account


def _decode_terminal_transcript(chunks: list[bytes]) -> str:
    return b"".join(chunks).decode("utf-8", errors="ignore")


def _write_claude_statusline_prompt(master_fd: int) -> None:
    _write_pty(
        master_fd,
        CLAUDE_USAGE_REFRESH_PROMPT.encode("utf-8")
        + CLAUDE_STATUSLINE_PROMPT_SUBMIT_BYTES,
    )


def _text_tail(text: str) -> str:
    return text[-CLAUDE_STATUSLINE_TRANSCRIPT_TAIL_CHARS:]


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
        limit_id=_claude_rate_limit_id(limit_type),
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


def claude_statusline_usage_record_limits(
    payload: Mapping[str, Any],
) -> tuple[AccountLimit, ...]:
    return _parse_claude_statusline_rate_limits(payload)


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
        limit_id=_claude_rate_limit_id(limit_type),
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


def _claude_rate_limit_id(limit_type: str) -> str:
    if limit_type == "five_hour":
        return "burst"
    if limit_type == "seven_day":
        return "weekly"
    raise CliError(f"unsupported claude rate-limit type {limit_type!r}")


def _claude_rate_limit_name(limit_type: str) -> str:
    return _claude_rate_limit_id(limit_type)


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
    raise CliError(f"unsupported claude rate-limit type {limit_type!r}")


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
    *, agent: AgentConfig, statusline_payload: Mapping[str, Any]
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


def _claude_statusline_process_environment(env_overrides: Mapping[str, str]) -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if _allow_claude_statusline_parent_env(key)
    }
    env.update(env_overrides)
    return env


def _allow_claude_statusline_parent_env(key: str) -> bool:
    return key in CLAUDE_STATUSLINE_PARENT_ENV_ALLOWLIST or key.startswith("LC_")


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


__all__: list[str] = []
