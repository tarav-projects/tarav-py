from __future__ import annotations

import argparse
import datetime
import io
import json
import os
import subprocess
import threading
import time
from pathlib import Path

import pytest

from agentos.chat import accounts as chat_accounts
from agentos.chat import commands as chat_commands
from agentos.cli import main
from agentos.tara_tapes.core import load_tara_tape_manifest, read_tara_tape_segment_records


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _account_instance(
    *,
    provider: str,
    instance_id: str,
    label: str,
    cli_command: tuple[str, ...] = (),
    env: tuple[tuple[str, str], ...] = (),
    timeout_sec: int = 15,
    live_usage_refresh: bool = False,
) -> chat_accounts.ProviderInstance:
    return chat_accounts.ProviderInstance(
        family=provider,
        instance_id=instance_id,
        label=label,
        cli_command=cli_command,
        env=env,
        timeout_sec=timeout_sec,
        live_usage_refresh=live_usage_refresh,
    )


def _account_context(
    *,
    provider: str,
    instance_id: str,
    label: str,
    cli_command: tuple[str, ...] = (),
    env: tuple[tuple[str, str], ...] = (),
    timeout_sec: int = 15,
    live_usage_refresh: bool = False,
) -> chat_accounts.AccountProviderContext:
    return chat_accounts._build_account_provider_context(
        _account_instance(
            provider=provider,
            instance_id=instance_id,
            label=label,
            cli_command=cli_command,
            env=env,
            timeout_sec=timeout_sec,
            live_usage_refresh=live_usage_refresh,
        )
    )


def _write_global_config(
    path: Path,
    *,
    provider_instances: list[dict[str, object]] | None = None,
) -> None:
    _write(
        path,
        json.dumps(
            {
                "class": "agentos.global.config",
                "schema_version": 1,
                "chat": {
                    "accounts": {
                        "provider_instances": provider_instances or [],
                    }
                },
            }
        ),
    )


def test_chat_accounts_stats_summarizes_configured_provider_instances(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    _write_global_config(
        agentos_home / "config.json",
        provider_instances=[
            {
                "provider": "codex",
                "id": "codex-tk",
                "label": "Codex tk",
                "cli_command": ["/opt/homebrew/bin/codex"],
                "env": {
                    "CODEX_HOME": str(home / ".codex-tk"),
                },
                "timeout_sec": 9,
            },
            {
                "provider": "claude-code",
                "id": "claude-main",
                "label": "Claude main",
                "cli_command": ["claude"],
            },
        ],
    )

    monkeypatch.setattr(chat_accounts, "_utc_now_iso", lambda: "2026-03-25T12:00:00Z")

    observed_calls: list[tuple[list[str], int]] = []

    def fake_run(
        command: list[str],
        *,
        capture_output: bool,
        text: bool,
        check: bool,
        env: dict[str, str],
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        assert capture_output is True
        assert text is True
        assert check is False
        observed_calls.append((command, timeout))

        if command == ["/opt/homebrew/bin/codex", "login", "status"]:
            assert env["CODEX_HOME"] == str(home / ".codex-tk")
            return subprocess.CompletedProcess(
                command,
                0,
                stdout="",
                stderr="Logged in using ChatGPT\n",
            )
        if command == ["claude", "auth", "status", "--json"]:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps(
                    {
                        "loggedIn": True,
                        "authMethod": "claude.ai",
                        "apiProvider": "firstParty",
                        "email": "user@example.com",
                        "orgId": "org-123",
                        "orgName": "Example Org",
                        "subscriptionType": "pro",
                    }
                ),
                stderr="",
            )
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(chat_accounts.subprocess, "run", fake_run)
    monkeypatch.setattr(
        chat_accounts,
        "_read_codex_account_rate_limits",
        lambda instance: {
            "rateLimits": {
                "limitId": "codex",
                "primary": {
                    "usedPercent": 0,
                    "windowDurationMins": 300,
                    "resetsAt": 1_774_503_641,
                },
                "secondary": {
                    "usedPercent": 99,
                    "windowDurationMins": 10_080,
                    "resetsAt": 1_774_559_427,
                },
                "credits": {
                    "hasCredits": False,
                    "unlimited": False,
                    "balance": "0",
                },
                "planType": "plus",
            }
        },
    )

    assert main(["chat", "accounts", "stats"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert sorted(observed_calls) == sorted(
        [
            (["/opt/homebrew/bin/codex", "login", "status"], 9),
            (["claude", "auth", "status", "--json"], chat_accounts.DEFAULT_ACCOUNT_TIMEOUT_SEC),
        ]
    )
    assert payload["status"] == "ok"
    assert payload["command"] == "chat accounts stats"
    assert payload["recorded_at"] == "2026-03-25T12:00:00Z"
    assert payload["provider_count"] == 2
    assert payload["account_count"] == 2
    assert payload["ok_count"] == 2
    assert payload["error_count"] == 0
    assert payload["history"]["status"] == "ok"

    history_root = agentos_home / "chat-account-stats"
    tape_root = history_root / "history"
    latest_path = history_root / "latest.json"
    manifest_path = tape_root / "tape.json"
    segment_path = tape_root / "segments" / "202603.jsonl"
    assert payload["history"]["latest_path"] == str(latest_path)
    assert payload["history"]["root"] == str(history_root)
    assert payload["history"]["tape_root"] == str(tape_root)
    assert payload["history"]["segment_name"] == "202603.jsonl"
    assert payload["history"]["manifest_path"] == str(manifest_path)
    assert json.loads(latest_path.read_text(encoding="utf-8")) == payload
    assert manifest_path.is_file()
    assert segment_path.is_file()
    assert load_tara_tape_manifest(tape_root)["tape_name"] == "chat-account-stats"
    assert read_tara_tape_segment_records(tape_root, segment_name="202603.jsonl") == [payload]

    providers = {provider["provider"]: provider for provider in payload["providers"]}

    codex_account = providers["codex"]["accounts"][0]
    assert codex_account["id"] == "codex-tk"
    assert codex_account["label"] == "Codex tk"
    assert codex_account["check_status"] == "ok"
    assert codex_account["auth_summary"] == "Logged in using ChatGPT"
    assert codex_account["summary"] == "Logged in using ChatGPT; 5h 0%, 7d 99%"
    assert codex_account["logged_in"] is True
    assert codex_account["auth_method"] == "ChatGPT"
    assert codex_account["plan"] == "plus"
    assert codex_account["usage_status"] == "ok"
    assert codex_account["usage_summary"] == "5h 0%, 7d 99%"
    assert codex_account["usage_source"] == "app-server"
    codex_limits = codex_account["usage"]["limits"]
    assert codex_limits[0]["period_duration_mins"] == 300
    assert codex_limits[0]["period_started_at"] == "2026-03-26T00:40:41Z"
    assert codex_limits[0]["period_ends_at"] == "2026-03-26T05:40:41Z"
    assert codex_limits[1]["period_duration_mins"] == 10_080
    assert codex_limits[1]["period_started_at"] == "2026-03-19T21:10:27Z"
    assert codex_limits[1]["period_ends_at"] == "2026-03-26T21:10:27Z"

    claude_account = providers["claude-code"]["accounts"][0]
    assert claude_account["id"] == "claude-main"
    assert claude_account["check_status"] == "ok"
    assert claude_account["logged_in"] is True
    assert claude_account["auth_method"] == "claude.ai"
    assert claude_account["plan"] == "pro"
    assert claude_account["account_email"] == "user@example.com"
    assert claude_account["organization_name"] == "Example Org"
    assert claude_account["summary"] == "Logged in via claude.ai (pro)"
    assert claude_account["usage_status"] == "unavailable"
    assert "live usage refresh disabled" in claude_account["usage_message"]


def test_chat_accounts_stats_summarizes_configured_copilot_account(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    _write_global_config(
        agentos_home / "config.json",
        provider_instances=[
            {
                "provider": "copilot",
                "id": "copilot-main",
                "label": "Copilot main",
            }
        ],
    )

    observed_calls: list[list[str]] = []

    def fake_run(
        command: list[str],
        *,
        capture_output: bool,
        text: bool,
        check: bool,
        env: dict[str, str],
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        assert capture_output is True
        assert text is True
        assert check is False
        assert timeout == chat_accounts.DEFAULT_ACCOUNT_TIMEOUT_SEC
        observed_calls.append(command)

        if command == [
            "copilot",
            "--model",
            "gpt-4.1",
            "-p",
            "Reply with OK only.",
            "--allow-all-tools",
            "--no-ask-user",
            "--no-custom-instructions",
            "--no-auto-update",
            "--output-format",
            "json",
            "--stream",
            "off",
        ]:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout="\n".join(
                    [
                        json.dumps({"type": "session.model_change", "data": {"newModel": "gpt-4.1"}}),
                        json.dumps({"type": "assistant.message", "data": {"content": "OK"}}),
                        json.dumps(
                            {
                                "type": "result",
                                "sessionId": "session-123",
                                "exitCode": 0,
                                "usage": {
                                    "premiumRequests": 1,
                                    "sessionDurationMs": 3210,
                                },
                            }
                        ),
                    ]
                ),
                stderr="",
            )
        if command == ["gh", "auth", "token"]:
            return subprocess.CompletedProcess(command, 0, stdout="gho-test-token\n", stderr="")
        raise AssertionError(f"unexpected command: {command}")

    class FakeCopilotResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def __enter__(self) -> "FakeCopilotResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(self._payload).encode("utf-8")

    def fake_urlopen(request, timeout: int):  # type: ignore[no-untyped-def]
        assert timeout == chat_accounts.DEFAULT_ACCOUNT_TIMEOUT_SEC
        assert request.full_url == chat_accounts.COPILOT_USAGE_API_URL
        assert request.get_header("Authorization") == "token gho-test-token"
        return FakeCopilotResponse(
            {
                "login": "josePereiro",
                "copilot_plan": "individual",
                "quota_snapshots": {
                    "premium_interactions": {
                        "entitlement": 500,
                        "remaining": 450,
                        "percent_remaining": 90,
                        "quota_id": "premium_interactions",
                    },
                    "chat": {
                        "entitlement": 300,
                        "remaining": 150,
                        "percent_remaining": 50,
                        "quota_id": "chat",
                    },
                },
            }
        )

    monkeypatch.setattr(chat_accounts.subprocess, "run", fake_run)
    monkeypatch.setattr(chat_accounts.urllib.request, "urlopen", fake_urlopen)

    assert main(["chat", "accounts", "stats"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["provider_count"] == 1
    assert payload["account_count"] == 1
    copilot_account = payload["providers"][0]["accounts"][0]
    assert copilot_account["id"] == "copilot-main"
    assert copilot_account["label"] == "Copilot main"
    assert copilot_account["provider"] == "copilot"
    assert copilot_account["check_status"] == "ok"
    assert copilot_account["cli_command"] == ["copilot"]
    assert copilot_account["auth_summary"] == "Copilot CLI ready (gpt-4.1)"
    assert copilot_account["auth_method"] == "copilot-cli"
    assert copilot_account["logged_in"] is True
    assert copilot_account["account_login"] == "josePereiro"
    assert copilot_account["plan"] == "individual"
    assert copilot_account["usage_status"] == "ok"
    assert copilot_account["usage_source"] == "copilot-api"
    assert copilot_account["usage_summary"] == "Premium 10%, Chat 50%"
    assert copilot_account["summary"] == "Copilot CLI ready (gpt-4.1); Premium 10%, Chat 50%"
    assert copilot_account["provider_status"]["copilot_cli_probe"]["session_id"] == "session-123"
    copilot_limits = copilot_account["usage"]["limits"]
    assert [limit["limit_label"] for limit in copilot_limits] == ["Premium", "Chat"]
    assert [limit["used_percent"] for limit in copilot_limits] == [10, 50]
    assert observed_calls == [
        [
            "copilot",
            "--model",
            "gpt-4.1",
            "-p",
            "Reply with OK only.",
            "--allow-all-tools",
            "--no-ask-user",
            "--no-custom-instructions",
            "--no-auto-update",
            "--output-format",
            "json",
            "--stream",
            "off",
        ],
        ["gh", "auth", "token"],
    ]


def test_chat_accounts_stats_degrades_when_copilot_github_token_fetch_fails(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    _write_global_config(
        agentos_home / "config.json",
        provider_instances=[
            {
                "provider": "copilot",
                "id": "copilot-main",
                "label": "Copilot main",
            }
        ],
    )

    def fake_run(
        command: list[str],
        *,
        capture_output: bool,
        text: bool,
        check: bool,
        env: dict[str, str],
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        del capture_output, text, check, env, timeout
        if command[0] == "copilot":
            return subprocess.CompletedProcess(
                command,
                0,
                stdout="\n".join(
                    [
                        json.dumps({"type": "session.model_change", "data": {"newModel": "gpt-4.1"}}),
                        json.dumps(
                            {
                                "type": "result",
                                "sessionId": "session-123",
                                "exitCode": 0,
                                "usage": {"premiumRequests": 1},
                            }
                        ),
                    ]
                ),
                stderr="",
            )
        if command == ["gh", "auth", "token"]:
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="gh auth token failed")
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(chat_accounts.subprocess, "run", fake_run)

    assert main(["chat", "accounts", "stats"]) == 0
    payload = json.loads(capsys.readouterr().out)

    copilot_account = payload["providers"][0]["accounts"][0]
    assert copilot_account["check_status"] == "ok"
    assert copilot_account["auth_method"] == "copilot-cli"
    assert copilot_account["usage_status"] == "error"
    assert copilot_account["usage_error"]["type"] == "command_failed"
    assert copilot_account["usage_error"]["message"] == "gh auth token failed"


def test_chat_accounts_stats_refresh_usage_enables_claude_live_usage(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    _write_global_config(
        agentos_home / "config.json",
        provider_instances=[
            {
                "provider": "claude-code",
                "id": "claude-main",
                "label": "Claude main",
                "cli_command": ["claude"],
            }
        ],
    )

    observed_calls: list[list[str]] = []

    def fake_run(
        command: list[str],
        *,
        capture_output: bool,
        text: bool,
        check: bool,
        env: dict[str, str],
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        del capture_output, text, check, env, timeout
        observed_calls.append(command)
        if command == ["claude", "auth", "status", "--json"]:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps(
                    {
                        "loggedIn": True,
                        "authMethod": "claude.ai",
                        "subscriptionType": "pro",
                    }
                ),
                stderr="",
            )
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(chat_accounts.subprocess, "run", fake_run)

    live_usage_observed: list[str] = []

    def fake_collect_live_usage(instance: chat_accounts.AccountProviderContext) -> dict[str, object]:
        live_usage_observed.append(instance.instance_id)
        return {
            "usage_status": "ok",
            "usage_source": "interactive-statusline",
            "usage_summary": "5h 1%, 7d 100%",
            "usage_refresh_cost_usd": 0.023,
            "usage": {
                "kind": "subscription_rate_limit",
                "limits": [
                    {
                        "limit_type": "five_hour",
                        "limit_label": "5h",
                        "used_percent": 1,
                    },
                    {
                        "limit_type": "seven_day",
                        "limit_label": "7d",
                        "used_percent": 100,
                    },
                ],
            },
            "provider_status": {
                "live_usage_refresh": {
                    "statusline": {
                        "rate_limits": {
                            "five_hour": {
                                "used_percentage": 1,
                                "resets_at": 1_774_537_200,
                            },
                            "seven_day": {
                                "used_percentage": 100,
                                "resets_at": 1_774_605_600,
                            },
                        },
                    }
                }
            },
        }

    monkeypatch.setattr(chat_accounts, "_collect_claude_code_live_usage", fake_collect_live_usage)

    assert main(["chat", "accounts", "stats", "--refresh-usage"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert observed_calls == [["claude", "auth", "status", "--json"]]
    assert live_usage_observed == ["claude-main"]

    claude_account = payload["providers"][0]["accounts"][0]
    assert claude_account["summary"] == "Logged in via claude.ai (pro); 5h 1%, 7d 100%"
    assert claude_account["usage_status"] == "ok"
    assert claude_account["usage_summary"] == "5h 1%, 7d 100%"
    assert claude_account["usage_source"] == "interactive-statusline"
    assert claude_account["usage_refresh_cost_usd"] == 0.023


def test_chat_account_stats_collects_instances_in_parallel_and_preserves_order(monkeypatch) -> None:
    instances = (
        _account_instance(
            provider="alpha",
            instance_id="alpha-1",
            label="Alpha 1",
            cli_command=("alpha",),
            env=(),
            timeout_sec=15,
            live_usage_refresh=False,
        ),
        _account_instance(
            provider="beta",
            instance_id="beta-1",
            label="Beta 1",
            cli_command=("beta",),
            env=(),
            timeout_sec=15,
            live_usage_refresh=False,
        ),
        _account_instance(
            provider="alpha",
            instance_id="alpha-2",
            label="Alpha 2",
            cli_command=("alpha",),
            env=(),
            timeout_sec=15,
            live_usage_refresh=False,
        ),
    )

    lock = threading.Lock()
    in_flight = 0
    max_in_flight = 0

    def collect(instance: chat_accounts.AccountProviderContext, refresh_usage: bool) -> dict[str, object]:
        nonlocal in_flight, max_in_flight
        assert refresh_usage is False
        with lock:
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
        time.sleep(0.05)
        with lock:
            in_flight -= 1
        return {
            "id": instance.instance_id,
            "label": instance.label,
            "provider": instance.provider,
            "check_status": "ok",
        }

    monkeypatch.setattr(
            chat_accounts,
            "supported_account_provider_families",
            lambda: (
            chat_accounts.AccountProviderHandler(
                provider_family=chat_accounts.ProviderFamily(family="alpha"),
                collect_stats=collect,
            ),
            chat_accounts.AccountProviderHandler(
                provider_family=chat_accounts.ProviderFamily(family="beta"),
                collect_stats=collect,
            ),
        ),
    )
    monkeypatch.setattr(
        chat_accounts,
        "configured_account_provider_instances",
        lambda start_path=".": instances,
    )
    monkeypatch.setattr(chat_accounts, "_persist_chat_account_stats_payload", lambda payload: {"status": "ok"})
    monkeypatch.setattr(chat_accounts, "_utc_now_iso", lambda: "2026-03-25T12:00:00Z")

    payload = chat_accounts.chat_account_stats()

    assert max_in_flight >= 2
    assert [provider["provider"] for provider in payload["providers"]] == ["alpha", "beta"]
    assert [account["id"] for account in payload["providers"][0]["accounts"]] == ["alpha-1", "alpha-2"]
    assert [account["id"] for account in payload["providers"][1]["accounts"]] == ["beta-1"]


def test_collect_claude_code_account_stats_overlaps_auth_and_live_usage(monkeypatch) -> None:
    instance = _account_context(
        provider="claude-code",
        instance_id="claude-main",
        label="Claude main",
        cli_command=("claude",),
        env=(),
        timeout_sec=15,
        live_usage_refresh=False,
    )

    lock = threading.Lock()
    in_flight = 0
    max_in_flight = 0

    def enter_task() -> None:
        nonlocal in_flight, max_in_flight
        with lock:
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)

    def exit_task() -> None:
        nonlocal in_flight
        with lock:
            in_flight -= 1

    def fake_collect_parsed_command_payload(
        task_instance: chat_accounts.AccountProviderContext,
        *,
        extra_args: tuple[str, ...],
        parser,
        cwd: str | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> dict[str, object]:
        del parser, cwd, extra_env
        assert task_instance == instance
        assert extra_args == ("auth", "status", "--json")
        enter_task()
        try:
            time.sleep(0.05)
            return {
                "logged_in": True,
                "summary": "Authenticated",
            }
        finally:
            exit_task()

    def fake_collect_live_usage(
        task_instance: chat_accounts.AccountProviderContext,
    ) -> dict[str, object]:
        assert task_instance == instance
        enter_task()
        try:
            time.sleep(0.05)
            return {
                "usage_status": "ok",
                "usage_summary": "5h 10%, 7d 20%",
                "usage_source": "interactive-statusline",
                "usage": {
                    "kind": "rate_limits",
                    "limits": [],
                },
            }
        finally:
            exit_task()

    monkeypatch.setattr(
        chat_accounts,
        "_collect_parsed_command_payload",
        fake_collect_parsed_command_payload,
    )
    monkeypatch.setattr(
        chat_accounts,
        "_collect_claude_code_live_usage",
        fake_collect_live_usage,
    )

    payload = chat_accounts._collect_claude_code_account_stats(instance, refresh_usage=True)

    assert max_in_flight >= 2
    assert payload["check_status"] == "ok"
    assert payload["usage_status"] == "ok"
    assert payload["usage_source"] == "interactive-statusline"


def test_loop_chat_accounts_stats_repeats_until_keyboard_interrupt(monkeypatch) -> None:
    args = argparse.Namespace(
        instance_ids=[],
        providers=None,
        refresh_usage=False,
        full_output=False,
        output_format="json",
        loop=True,
    )

    outputs = iter(("snapshot-1", "snapshot-2"))
    monkeypatch.setattr(
        chat_commands,
        "_render_chat_accounts_stats_output",
        lambda loop_args: next(outputs),
    )

    wait_calls: list[float] = []

    def fake_wait(interval_sec: float, input_stream) -> None:  # type: ignore[no-untyped-def]
        del input_stream
        wait_calls.append(interval_sec)
        if len(wait_calls) >= 2:
            raise KeyboardInterrupt()

    output_stream = io.StringIO()
    exit_code = chat_commands._loop_chat_accounts_stats(
        args,
        input_stream=io.StringIO(),
        output_stream=output_stream,
        interval_sec=60.0,
        wait_for_trigger=fake_wait,
    )

    rendered = output_stream.getvalue()
    assert exit_code == 0
    assert wait_calls == [60.0, 60.0]
    assert "snapshot-1" in rendered
    assert "snapshot-2" in rendered
    assert rendered.count(chat_commands._CHAT_ACCOUNTS_LOOP_REFRESHING_MESSAGE) == 1
    assert "[loop] refreshes every 60s; press Enter to refresh now; Ctrl-C to stop" in rendered


def test_loop_chat_accounts_stats_fetches_before_clearing_tty(monkeypatch) -> None:
    args = argparse.Namespace(
        instance_ids=[],
        providers=None,
        refresh_usage=False,
        full_output=False,
        output_format="json",
        loop=True,
    )

    events: list[str] = []

    def fake_render(loop_args: argparse.Namespace) -> str:
        assert loop_args is args
        events.append("render")
        return "snapshot"

    def fake_clear(output_stream) -> None:  # type: ignore[no-untyped-def]
        del output_stream
        events.append("clear")

    def fake_wait(interval_sec: float, input_stream) -> None:  # type: ignore[no-untyped-def]
        del interval_sec, input_stream
        raise KeyboardInterrupt()

    class FakeTTYOutput(io.StringIO):
        def isatty(self) -> bool:
            return True

        def write(self, text: str) -> int:
            if text == "snapshot":
                events.append("write")
            return super().write(text)

    monkeypatch.setattr(chat_commands, "_render_chat_accounts_stats_output", fake_render)
    monkeypatch.setattr(chat_commands, "_clear_terminal_screen", fake_clear)

    exit_code = chat_commands._loop_chat_accounts_stats(
        args,
        input_stream=io.StringIO(),
        output_stream=FakeTTYOutput(),
        interval_sec=60.0,
        wait_for_trigger=fake_wait,
    )

    assert exit_code == 0
    assert events == ["render", "clear", "write"]


def test_loop_chat_accounts_stats_shows_refreshing_feedback_before_next_tty_fetch(monkeypatch) -> None:
    args = argparse.Namespace(
        instance_ids=[],
        providers=None,
        refresh_usage=False,
        full_output=False,
        output_format="json",
        loop=True,
    )

    outputs = iter(("snapshot-1", "snapshot-2"))
    events: list[str] = []
    wait_calls = 0

    def fake_render(loop_args: argparse.Namespace) -> str:
        assert loop_args is args
        snapshot = next(outputs)
        events.append(f"render:{snapshot}")
        return snapshot

    def fake_clear(output_stream) -> None:  # type: ignore[no-untyped-def]
        del output_stream
        events.append("clear")

    def fake_wait(interval_sec: float, input_stream) -> None:  # type: ignore[no-untyped-def]
        nonlocal wait_calls
        del interval_sec, input_stream
        wait_calls += 1
        events.append(f"wait:{wait_calls}")
        if wait_calls >= 2:
            raise KeyboardInterrupt()

    class FakeTTYOutput(io.StringIO):
        def isatty(self) -> bool:
            return True

        def write(self, text: str) -> int:
            if text in {"snapshot-1", "snapshot-2"}:
                events.append(f"write:{text}")
            elif text == chat_commands._CHAT_ACCOUNTS_LOOP_REFRESHING_MESSAGE + "\n":
                events.append("write:refreshing")
            return super().write(text)

    monkeypatch.setattr(chat_commands, "_render_chat_accounts_stats_output", fake_render)
    monkeypatch.setattr(chat_commands, "_clear_terminal_screen", fake_clear)

    exit_code = chat_commands._loop_chat_accounts_stats(
        args,
        input_stream=io.StringIO(),
        output_stream=FakeTTYOutput(),
        interval_sec=60.0,
        wait_for_trigger=fake_wait,
    )

    assert exit_code == 0
    assert events == [
        "render:snapshot-1",
        "clear",
        "write:snapshot-1",
        "wait:1",
        "write:refreshing",
        "render:snapshot-2",
        "clear",
        "write:snapshot-2",
        "wait:2",
    ]


def test_wait_for_chat_accounts_loop_trigger_returns_immediately_on_enter() -> None:
    class FakeTTYInput:
        def __init__(self, wrapped) -> None:  # type: ignore[no-untyped-def]
            self._wrapped = wrapped

        def fileno(self) -> int:
            return self._wrapped.fileno()

        def readline(self) -> str:
            return self._wrapped.readline()

        def isatty(self) -> bool:
            return True

    read_fd, write_fd = os.pipe()
    read_stream = os.fdopen(read_fd, "r", encoding="utf-8", buffering=1)
    write_stream = os.fdopen(write_fd, "w", encoding="utf-8", buffering=1)
    try:
        write_stream.write("\n")
        write_stream.flush()
        start = time.perf_counter()
        chat_commands._wait_for_chat_accounts_loop_trigger(1.0, FakeTTYInput(read_stream))
        elapsed = time.perf_counter() - start
    finally:
        read_stream.close()
        write_stream.close()

    assert elapsed < 0.5


def test_format_display_datetime_local_converts_utc_timestamp() -> None:
    tzinfo = datetime.timezone(datetime.timedelta(hours=-4), name="CDT")

    assert (
        chat_accounts._format_display_datetime_local("2026-03-28T14:06:58Z", tzinfo=tzinfo)
        == "2026-03-28 10:06:58 CDT"
    )


def test_chat_accounts_stats_supports_full_output_and_markdown(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    def fail_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("subprocess.run should not be called without configured instances")

    monkeypatch.setattr(chat_accounts.subprocess, "run", fail_run)
    monkeypatch.setattr(chat_accounts, "_format_display_datetime_local", lambda value, tzinfo=None: "LOCAL_TIME")

    assert main(["chat", "accounts", "stats"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["provider_count"] == 0
    assert payload["account_count"] == 0
    assert payload["providers"] == []

    assert main(["chat", "accounts", "stats", "--full-output"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["provider_count"] == 3
    assert [provider["provider"] for provider in payload["providers"]] == ["codex", "claude-code", "copilot"]
    assert all(provider["account_count"] == 0 for provider in payload["providers"])

    assert main(["chat", "accounts", "stats", "--full-output", "--output", "markdown"]) == 0
    output = capsys.readouterr().out
    assert "# Chat Accounts Stats" in output
    assert "- Recorded at: LOCAL_TIME" in output
    assert "- History: ok" in output
    assert "- History segment: " in output
    assert "## codex" in output
    assert "## claude-code" in output
    assert "## copilot" in output


def test_chat_accounts_stats_supports_compact_usage_output(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))
    monkeypatch.setattr(chat_accounts, "_utc_now_iso", lambda: "2026-03-25T12:00:00Z")
    display_timestamps = {
        "2026-03-25T12:00:00Z": "2026-03-25 08:00:00 CDT",
        "2026-03-26T05:40:41Z": "2026-03-26 01:40:41 CDT",
        "2026-03-26T21:10:27Z": "2026-03-26 17:10:27 CDT",
    }
    monkeypatch.setattr(
        chat_accounts,
        "_format_display_datetime_local",
        lambda value, tzinfo=None: display_timestamps.get(value, value),
    )
    compact_display_timestamps = {
        "2026-03-26T05:40:41Z": "Wed 03-26 01:40",
        "2026-03-26T21:10:27Z": "Wed 03-26 17:10",
    }
    monkeypatch.setattr(
        chat_accounts,
        "_format_display_datetime_local_compact",
        lambda value, tzinfo=None: compact_display_timestamps.get(value, value),
    )

    _write_global_config(
        agentos_home / "config.json",
        provider_instances=[
            {
                "provider": "codex",
                "id": "codex-tk",
                "label": "Codex tk",
                "cli_command": ["codex"],
            },
            {
                "provider": "claude-code",
                "id": "claude-main",
                "label": "Claude main",
                "cli_command": ["claude"],
            },
        ],
    )

    def fake_run(
        command: list[str],
        *,
        capture_output: bool,
        text: bool,
        check: bool,
        env: dict[str, str],
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        del capture_output, text, check, env, timeout
        if command == ["codex", "login", "status"]:
            return subprocess.CompletedProcess(command, 0, stdout="Logged in using ChatGPT\n", stderr="")
        if command == ["claude", "auth", "status", "--json"]:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps(
                    {
                        "loggedIn": True,
                        "authMethod": "claude.ai",
                        "subscriptionType": "pro",
                    }
                ),
                stderr="",
            )
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(chat_accounts.subprocess, "run", fake_run)
    monkeypatch.setattr(
        chat_accounts,
        "_read_codex_account_rate_limits",
        lambda instance: {
            "rateLimits": {
                "limitId": "codex",
                "primary": {
                    "usedPercent": 64,
                    "windowDurationMins": 300,
                    "resetsAt": 1_774_503_641,
                },
                "secondary": {
                    "usedPercent": 20,
                    "windowDurationMins": 10_080,
                    "resetsAt": 1_774_559_427,
                },
            }
        },
    )

    assert main(["chat", "accounts", "stats", "--output", "usage"]) == 0
    output = capsys.readouterr().out

    assert "# Chat Accounts Usage" in output
    assert "- Recorded at: 2026-03-25 08:00:00 CDT" in output
    assert "codex-tk (Codex tk):" in output
    assert "  usage/time | 64% /  0% = n/a | 5h" in output
    assert "      resets | Wed 03-26 01:40 | 17h 40m" in output
    assert "  usage/time | 20% / 80% = 0.2 | 7d" in output
    assert "      resets | Wed 03-26 17:10 | 1d 9h 10m" in output
    assert "claude-main (Claude main):" in output
    assert "  usage | unavailable" in output
    assert "     | live usage refresh disabled; pass --refresh-usage or set live_usage_refresh=true" in output


def test_format_chat_account_stats_usage_sorts_accounts_by_highest_ratio() -> None:
    output = chat_accounts.format_chat_account_stats_usage(
        {
            "recorded_at": "2026-03-25T12:00:00Z",
            "providers": [
                {
                    "accounts": [
                        {
                            "id": "steady-low",
                            "label": "Steady low",
                            "usage": {
                                "limits": [
                                    {
                                        "limit_label": "5h",
                                        "used_percent": 70,
                                        "period_started_at": "2026-03-25T04:30:00Z",
                                        "period_ends_at": "2026-03-25T14:30:00Z",
                                    }
                                ]
                            },
                        },
                        {
                            "id": "burst-high",
                            "label": "Burst high",
                            "usage": {
                                "limits": [
                                    {
                                        "limit_label": "5h",
                                        "used_percent": 20,
                                        "period_started_at": "2026-03-25T09:30:00Z",
                                        "period_ends_at": "2026-03-25T14:30:00Z",
                                    },
                                    {
                                        "limit_label": "7d",
                                        "used_percent": 90,
                                        "period_started_at": "2026-03-19T12:00:00Z",
                                        "period_ends_at": "2026-03-26T12:00:00Z",
                                    },
                                ]
                            },
                        },
                    ]
                }
            ],
        }
    )

    assert output.index("burst-high (Burst high):") < output.index("steady-low (Steady low):")
    assert "  usage/time | 90% / 86% = 1.0 | 7d" in output
    assert "  usage/time | 70% / 75% = 0.9 | 5h" in output


def test_chat_accounts_stats_usage_output_styles_fetch_errors(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    _write_global_config(
        agentos_home / "config.json",
        provider_instances=[
            {
                "provider": "codex",
                "id": "codex-main",
                "label": "Codex main",
                "cli_command": ["codex"],
            }
        ],
    )

    def fake_run(
        command: list[str],
        *,
        capture_output: bool,
        text: bool,
        check: bool,
        env: dict[str, str],
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        del capture_output, text, check, env, timeout
        if command == ["codex", "login", "status"]:
            return subprocess.CompletedProcess(command, 0, stdout="Logged in using ChatGPT\n", stderr="")
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(chat_accounts.subprocess, "run", fake_run)
    monkeypatch.setattr(
        chat_accounts,
        "_read_codex_account_rate_limits",
        lambda instance: (_ for _ in ()).throw(
            chat_accounts.AccountCommandError(
                error_type="command_failed",
                message="rate-limit request failed",
                exit_code=2,
            )
        ),
    )

    assert main(["chat", "accounts", "stats", "--output", "usage"]) == 0
    output = capsys.readouterr().out

    assert "codex-main (Codex main):" in output
    assert "  usage | error" in output
    assert "     | command_failed: rate-limit request failed" in output


def test_chat_accounts_stats_usage_formats_account_check_errors_nicely(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    _write_global_config(
        agentos_home / "config.json",
        provider_instances=[
            {
                "provider": "codex",
                "id": "codex-main",
                "label": "Codex main",
                "cli_command": ["codex"],
            }
        ],
    )

    def fake_run(
        command: list[str],
        *,
        capture_output: bool,
        text: bool,
        check: bool,
        env: dict[str, str],
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        del capture_output, text, check, env, timeout
        if command == ["codex", "login", "status"]:
            return subprocess.CompletedProcess(command, 2, stdout="", stderr="login failed")
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(chat_accounts.subprocess, "run", fake_run)
    monkeypatch.setattr(
        chat_accounts,
        "_read_codex_account_rate_limits",
        lambda instance: {
            "rateLimits": {
                "limitId": "codex",
                "primary": {
                    "usedPercent": 1,
                    "windowDurationMins": 300,
                    "resetsAt": 1_774_537_200,
                },
            }
        },
    )

    assert main(["chat", "accounts", "stats", "--output", "usage"]) == 0
    output = capsys.readouterr().out

    assert "codex-main (Codex main):" in output
    assert "  check | error" in output
    assert "     | command_failed: login failed" in output


def test_chat_accounts_stats_history_accumulates_into_month_segment(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    timestamps = iter(("2026-03-25T12:00:00Z", "2026-03-25T12:05:00Z"))
    monkeypatch.setattr(chat_accounts, "_utc_now_iso", lambda: next(timestamps))

    def fail_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("subprocess.run should not be called without configured instances")

    monkeypatch.setattr(chat_accounts.subprocess, "run", fail_run)

    assert main(["chat", "accounts", "stats", "--full-output"]) == 0
    first_payload = json.loads(capsys.readouterr().out)
    assert main(["chat", "accounts", "stats", "--full-output"]) == 0
    second_payload = json.loads(capsys.readouterr().out)

    tape_root = agentos_home / "chat-account-stats" / "history"
    records = read_tara_tape_segment_records(tape_root, segment_name="202603.jsonl")
    assert records == [first_payload, second_payload]


def test_parse_claude_code_live_usage_output_derives_period_bounds() -> None:
    payload = chat_accounts._parse_claude_code_live_usage_output(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "rate_limit_event",
                        "rate_limit_info": {
                            "rateLimitType": "seven_day",
                            "utilization": 0.42,
                            "resetsAt": 1_774_559_427,
                            "status": "ok",
                            "isUsingOverage": False,
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "result",
                        "session_id": "session-123",
                        "total_cost_usd": 0.004,
                        "modelUsage": {
                            "claude-3-5-haiku": {
                                "inputTokens": 1,
                            }
                        },
                    }
                ),
            ]
        )
    )

    assert payload["usage_status"] == "ok"
    assert payload["usage_summary"] == "7d 42%"
    assert payload["usage_refresh_cost_usd"] == 0.004
    limit_payload = payload["usage"]["limits"][0]
    assert limit_payload["period_duration_mins"] == 10_080
    assert limit_payload["period_started_at"] == "2026-03-19T21:10:27Z"
    assert limit_payload["period_ends_at"] == "2026-03-26T21:10:27Z"
    assert limit_payload["resets_at"] == "2026-03-26T21:10:27Z"


def test_format_remaining_duration_uses_human_day_hour_minute_units() -> None:
    assert chat_accounts._format_remaining_duration(0) == "0m"
    assert chat_accounts._format_remaining_duration(59) == "1m"
    assert chat_accounts._format_remaining_duration(60 * 60 * 2 + 60) == "2h 1m"
    assert chat_accounts._format_remaining_duration(60 * (2 * 24 * 60 + 3 * 60 + 1)) == "2d 3h 1m"


def test_format_usage_limit_elapsed_percent_uses_period_bounds() -> None:
    recorded_at = chat_accounts._parse_iso_datetime_or_none("2026-03-25T12:30:00Z")
    assert recorded_at is not None

    assert (
        chat_accounts._format_usage_limit_elapsed_percent(
            {
                "period_started_at": "2026-03-25T12:00:00Z",
                "period_ends_at": "2026-03-25T13:00:00Z",
            },
            recorded_at=recorded_at,
        )
        == 50
    )
    assert (
        chat_accounts._format_usage_limit_elapsed_percent(
            {
                "period_ends_at": "2026-03-25T13:00:00Z",
                "period_duration_mins": 60,
            },
            recorded_at=recorded_at,
        )
        == 50
    )


def test_parse_copilot_usage_response_falls_back_to_monthly_quotas() -> None:
    payload = chat_accounts._parse_copilot_usage_response(
        {
            "copilot_plan": "free",
            "quota_reset_date_utc": "2026-04-01T00:00:00.000Z",
            "monthly_quotas": {
                "chat": "500",
                "completions": 300,
            },
            "limited_user_quotas": {
                "chat": 125,
                "completions": "75",
            },
        }
    )

    assert payload["plan"] == "free"
    assert payload["usage_summary"] == "Premium 75%, Chat 75%"
    limits = payload["usage"]["limits"]
    assert [limit["limit_label"] for limit in limits] == ["Premium", "Chat"]
    assert [limit["used_percent"] for limit in limits] == [75, 75]
    assert [limit["period_duration_mins"] for limit in limits] == [44_640, 44_640]
    assert [limit["period_started_at"] for limit in limits] == [
        "2026-03-01T00:00:00Z",
        "2026-03-01T00:00:00Z",
    ]
    assert [limit["period_ends_at"] for limit in limits] == [
        "2026-04-01T00:00:00Z",
        "2026-04-01T00:00:00Z",
    ]


def test_normalize_terminal_output_detects_trust_and_main_prompts() -> None:
    trust_text = chat_accounts._normalize_terminal_output(
        [b"\x1b[1CQuick\x1b[1Csafety\x1b[1Ccheck \x1b[1CYes,\x1b[1CI\x1b[1Ctrust\x1b[1Cthis\x1b[1Cfolder"]
    )
    assert chat_accounts._claude_refresh_trust_prompt_visible(trust_text) is True

    main_text = chat_accounts._normalize_terminal_output(
        [b"\x1b[?2026hClaude\x1b[1CCode\x1Cv2.1.81 \x1b[1CWelcome\x1b[1Cback"]
    )
    assert chat_accounts._claude_refresh_main_prompt_visible(main_text) is True


def test_parse_claude_code_statusline_usage_output_includes_five_hour_and_seven_day() -> None:
    payload = chat_accounts._parse_claude_code_statusline_usage_output(
        {
            "session_id": "session-123",
            "transcript_path": "/Users/pereiro/.claude/projects/tmp/session-123.jsonl",
            "model": {
                "id": "claude-haiku-4-5-20251001",
                "display_name": "Haiku 4.5",
            },
            "cost": {
                "total_cost_usd": 0.02309745,
            },
            "rate_limits": {
                "five_hour": {
                    "used_percentage": 1,
                    "resets_at": 1_774_537_200,
                },
                "seven_day": {
                    "used_percentage": 100,
                    "resets_at": 1_774_605_600,
                },
            },
        }
    )

    assert payload["usage_status"] == "ok"
    assert payload["usage_source"] == "interactive-statusline"
    assert payload["usage_summary"] == "5h 1%, 7d 100%"
    assert payload["usage_refresh_cost_usd"] == 0.02309745
    assert payload["usage"]["refresh_model"] == "claude-haiku-4-5-20251001"
    assert payload["usage"]["refresh_session_id"] == "session-123"
    limits = payload["usage"]["limits"]
    assert [limit["limit_type"] for limit in limits] == ["five_hour", "seven_day"]
    assert limits[0]["period_duration_mins"] == 300
    assert limits[0]["period_started_at"] == "2026-03-26T10:00:00Z"
    assert limits[0]["period_ends_at"] == "2026-03-26T15:00:00Z"
    assert limits[1]["period_duration_mins"] == 10_080
    assert limits[1]["period_started_at"] == "2026-03-20T10:00:00Z"
    assert limits[1]["period_ends_at"] == "2026-03-27T10:00:00Z"


def test_claude_code_refresh_workspace_root_is_instance_scoped() -> None:
    instance = _account_context(
        provider="claude-code",
        instance_id="claude-main",
        label="Claude main",
        cli_command=("claude",),
        env=(),
        timeout_sec=15,
        live_usage_refresh=False,
    )

    workspace_root = chat_accounts._claude_code_refresh_workspace_root(instance)
    assert workspace_root.name == "claude-main"
    assert workspace_root.parent.name == chat_accounts.CLAUDE_REFRESH_WORKSPACE_DIRNAME


def test_collect_claude_code_live_usage_falls_back_to_stream_json(monkeypatch) -> None:
    instance = _account_context(
        provider="claude-code",
        instance_id="claude-main",
        label="Claude main",
        cli_command=("claude",),
        env=(),
        timeout_sec=15,
        live_usage_refresh=False,
    )

    monkeypatch.setattr(
        chat_accounts,
        "_collect_claude_code_live_usage_from_statusline",
        lambda instance: (_ for _ in ()).throw(
            chat_accounts.AccountCommandError(
                error_type="invalid_output",
                message="statusline missing",
            )
        ),
    )
    monkeypatch.setattr(
        chat_accounts,
        "_collect_claude_code_live_usage_from_stream_json",
        lambda instance: {
            "usage_status": "ok",
            "usage_source": "live-refresh",
            "usage_summary": "7d 42%",
        },
    )

    payload = chat_accounts._collect_claude_code_live_usage(instance)
    assert payload["usage_status"] == "ok"
    assert payload["usage_source"] == "live-refresh"
    assert payload["usage_summary"] == "7d 42%"


def test_chat_accounts_stats_keeps_per_account_errors_in_payload(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    _write_global_config(
        agentos_home / "config.json",
        provider_instances=[
            {
                "provider": "codex",
                "id": "codex-main",
                "cli_command": ["codex"],
            },
            {
                "provider": "claude-code",
                "id": "claude-main",
                "cli_command": ["claude"],
            },
        ],
    )

    def fake_run(
        command: list[str],
        *,
        capture_output: bool,
        text: bool,
        check: bool,
        env: dict[str, str],
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        del capture_output, text, check, env, timeout
        if command == ["codex", "login", "status"]:
            return subprocess.CompletedProcess(command, 0, stdout="Logged in using ChatGPT\n", stderr="")
        if command == ["claude", "auth", "status", "--json"]:
            return subprocess.CompletedProcess(command, 0, stdout="not-json", stderr="")
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(chat_accounts.subprocess, "run", fake_run)
    monkeypatch.setattr(
        chat_accounts,
        "_read_codex_account_rate_limits",
        lambda instance: {
            "rateLimits": {
                "limitId": "codex",
                "primary": {
                    "usedPercent": 1,
                    "windowDurationMins": 300,
                    "resetsAt": 1_774_503_641,
                },
            }
        },
    )

    assert main(["chat", "accounts", "stats"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["ok_count"] == 1
    assert payload["error_count"] == 1

    providers = {provider["provider"]: provider for provider in payload["providers"]}
    assert providers["codex"]["accounts"][0]["check_status"] == "ok"

    claude_account = providers["claude-code"]["accounts"][0]
    assert claude_account["check_status"] == "error"
    assert claude_account["error"]["type"] == "invalid_output"


def test_chat_accounts_stats_rejects_unknown_instance_ids(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))

    _write_global_config(
        agentos_home / "config.json",
        provider_instances=[
            {
                "provider": "codex",
                "id": "codex-main",
                "cli_command": ["codex"],
            }
        ],
    )

    def fail_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("subprocess.run should not be called for unknown instance ids")

    monkeypatch.setattr(chat_accounts.subprocess, "run", fail_run)

    assert main(["chat", "accounts", "stats", "missing"]) == 1
    assert "unknown account instance id: missing" in capsys.readouterr().err
