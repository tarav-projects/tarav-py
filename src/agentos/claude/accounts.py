from __future__ import annotations

import json
import os
import pty
import re
import select
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from agentos._core.errors import CliError
from agentos.agent.account_runtime import (
    AccountCommandError,
    AccountStatsRequest,
    account_provider_environment,
    collect_parsed_command_payload,
    run_account_command,
)
from agentos.agent.primitives import Agent
from agentos.agent.accounts import (
    AccountProviderContext,
    CHAT_USAGE_BURST_LABEL,
    CHAT_USAGE_WEEKLY_LABEL,
    _format_limit_summary,
    _iso_from_epoch_seconds,
    _merge_account_payloads,
    _optional_bool,
    _optional_float,
    _optional_int,
    _period_bounds_from_reset,
    _parse_claude_code_auth_status,
    _string_or_none,
    _usage_error_payload,
    _usage_over_time_limit,
    _usage_unavailable_payload,
    default_chat_account_stats_root,
)

_CLAUDE_USAGE_REFRESH_PROMPT = "Reply with OK."
_CLAUDE_USAGE_REFRESH_MODEL = "haiku"
CLAUDE_REFRESH_WORKSPACE_DIRNAME = "claude-refresh-workspace"
CLAUDE_REFRESH_TRUST_CONFIRM_DELAY_SEC = 0.75
CLAUDE_REFRESH_TRUST_CONFIRM_RETRY_SEC = 0.75
CLAUDE_REFRESH_PROMPT_FALLBACK_DELAY_SEC = 2.5
CLAUDE_REFRESH_INTERRUPT_SETTLE_SEC = 0.05
CLAUDE_REFRESH_TERMINATE_WAIT_SEC = 0.5

_ANSI_CSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_ANSI_OSC_RE = re.compile(r"\x1b\].*?(?:\x07|\x1b\\)", re.DOTALL)
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


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
        result = run_account_command(
            instance.agent,
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
    env = account_provider_environment(instance.agent)
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


def collect_claude_account_stats(agent: Agent, request: AccountStatsRequest) -> dict[str, Any]:
    should_refresh_usage = request.refresh_usage or bool(agent.account_live_usage_refresh)

    if should_refresh_usage:
        with ThreadPoolExecutor(max_workers=2) as executor:
            auth_future = executor.submit(
                collect_parsed_command_payload,
                agent,
                extra_args=("auth", "status", "--json"),
                parser=_parse_claude_code_auth_status,
            )
            usage_future = executor.submit(
                _collect_claude_code_live_usage,
                AccountProviderContext(agent=agent),
            )

        auth_payload = auth_future.result()
        try:
            usage_payload = usage_future.result()
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
    else:
        auth_payload = collect_parsed_command_payload(
            agent,
            extra_args=("auth", "status", "--json"),
            parser=_parse_claude_code_auth_status,
        )
        usage_payload = _usage_unavailable_payload(
            "live usage refresh disabled; pass --refresh-usage or set live_usage_refresh=true"
        )

    return _merge_account_payloads(auth_payload, usage_payload)
