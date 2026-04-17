from __future__ import annotations

import argparse
import datetime
import io
import json
import math
import os
import subprocess
import threading
import time
from pathlib import Path

import pytest
from rich.cells import cell_len

from agentos.chat import accounts as chat_accounts
from agentos.chat import commands as chat_commands
from agentos.cli import main
from agentos.tara_tapes.core import load_tara_tape_manifest, read_tara_tape_segment_records


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _span_tuples(rendered) -> list[tuple[int, int, str]]:  # type: ignore[no-untyped-def]
    return [(span.start, span.end, str(span.style)) for span in rendered.spans]


def _offset_gradient_runs(
    offset: int,
    start_cell: int,
    end_cell: int,
    *,
    width: int,
    palette: tuple[str, ...],
) -> list[tuple[int, int, str]]:
    return [
        (offset + start, offset + end, style)
        for start, end, style in chat_commands._cell_gradient_runs(
            start_cell,
            end_cell,
            width=width,
            palette=palette,
        )
    ]


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


def _usage_over_time_limit_payload(
    *,
    limit_name: str,
    limit_label: str,
    used_percent: int | None,
    period_started_at: str | None = None,
    period_ends_at: str | None = None,
    period_duration_mins: int | None = None,
    resets_at: str | None = None,
    provider_limit: dict[str, object] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "limit_class": "usage_over_time",
        "limit_name": limit_name,
        "limit_label": limit_label,
        "usage_over_time": {
            "used_percent": used_percent,
            "period_started_at": period_started_at,
            "period_ends_at": period_ends_at,
        },
    }
    usage_over_time = payload["usage_over_time"]
    assert isinstance(usage_over_time, dict)
    if period_duration_mins is not None:
        usage_over_time["period_duration_mins"] = period_duration_mins
    if resets_at is not None:
        usage_over_time["resets_at"] = resets_at
    if provider_limit is not None:
        payload["provider_limit"] = provider_limit
    return payload


def _usage_over_time_data(limit_payload: dict[str, object]) -> dict[str, object]:
    payload = limit_payload["usage_over_time"]
    assert isinstance(payload, dict)
    return payload


def _write_global_config(
    path: Path,
    *,
    provider_instances: list[dict[str, object]] | None = None,
    accounts_usage_total: dict[str, object] | None = None,
) -> None:
    chat_payload: dict[str, object] = {
        "provider_instances": provider_instances or [],
    }
    if accounts_usage_total is not None:
        chat_payload["accounts_usage_total"] = accounts_usage_total
    _write(
        path,
        json.dumps(
            {
                "class": "agentos.global.config",
                "schema_version": 1,
                "chat": chat_payload,
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
    assert codex_account["summary"] == "Logged in using ChatGPT; Burst 0%, Weekly 99%"
    assert codex_account["logged_in"] is True
    assert codex_account["auth_method"] == "ChatGPT"
    assert codex_account["plan"] == "plus"
    assert codex_account["usage_status"] == "ok"
    assert codex_account["usage_summary"] == "Burst 0%, Weekly 99%"
    assert codex_account["usage_source"] == "app-server"
    codex_limits = codex_account["usage"]["limits"]
    assert codex_limits[0]["limit_class"] == "usage_over_time"
    assert codex_limits[0]["limit_name"] == "burst"
    assert _usage_over_time_data(codex_limits[0])["period_duration_mins"] == 300
    assert _usage_over_time_data(codex_limits[0])["period_started_at"] == "2026-03-26T00:40:41Z"
    assert _usage_over_time_data(codex_limits[0])["period_ends_at"] == "2026-03-26T05:40:41Z"
    assert codex_limits[1]["limit_name"] == "weekly"
    assert _usage_over_time_data(codex_limits[1])["period_duration_mins"] == 10_080
    assert _usage_over_time_data(codex_limits[1])["period_started_at"] == "2026-03-19T21:10:27Z"
    assert _usage_over_time_data(codex_limits[1])["period_ends_at"] == "2026-03-26T21:10:27Z"

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
                "provider": "copilot-cli",
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
    assert copilot_account["provider"] == "copilot-cli"
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
    assert [limit["limit_name"] for limit in copilot_limits] == ["premium", "chat"]
    assert [_usage_over_time_data(limit)["used_percent"] for limit in copilot_limits] == [10, 50]
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
                "provider": "copilot-cli",
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
            "usage_summary": "Burst 1%, Weekly 100%",
            "usage_refresh_cost_usd": 0.023,
            "usage": {
                "kind": "subscription_rate_limit",
                "limits": [
                    _usage_over_time_limit_payload(
                        limit_name="burst",
                        limit_label="Burst",
                        used_percent=1,
                        provider_limit={"limit_type": "five_hour"},
                    ),
                    _usage_over_time_limit_payload(
                        limit_name="weekly",
                        limit_label="Weekly",
                        used_percent=100,
                        provider_limit={"limit_type": "seven_day"},
                    ),
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
    assert claude_account["summary"] == "Logged in via claude.ai (pro); Burst 1%, Weekly 100%"
    assert claude_account["usage_status"] == "ok"
    assert claude_account["usage_summary"] == "Burst 1%, Weekly 100%"
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
    monkeypatch.setattr(chat_accounts, "load_chat_accounts_usage_total_config", lambda start_path=".": None)
    monkeypatch.setattr(chat_accounts, "_persist_chat_account_stats_payload", lambda payload: {"status": "ok"})
    monkeypatch.setattr(chat_accounts, "_utc_now_iso", lambda: "2026-03-25T12:00:00Z")

    payload = chat_accounts.chat_account_stats()

    assert max_in_flight >= 2
    assert [provider["provider"] for provider in payload["providers"]] == ["alpha", "beta"]
    assert [account["id"] for account in payload["providers"][0]["accounts"]] == ["alpha-1", "alpha-2"]
    assert [account["id"] for account in payload["providers"][1]["accounts"]] == ["beta-1"]


def test_iter_chat_account_stats_refresh_payloads_yields_partial_updates_as_accounts_finish(
    monkeypatch,
) -> None:
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
    )

    release_alpha = threading.Event()

    def collect(instance: chat_accounts.AccountProviderContext, refresh_usage: bool) -> dict[str, object]:
        assert refresh_usage is False
        if instance.instance_id == "alpha-1":
            assert release_alpha.wait(timeout=1.0)
        return {
            "id": instance.instance_id,
            "label": instance.label,
            "provider": instance.provider,
            "check_status": "ok",
            "summary": f"{instance.instance_id} ready",
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
    monkeypatch.setattr(chat_accounts, "load_chat_accounts_usage_total_config", lambda start_path=".": None)
    monkeypatch.setattr(chat_accounts, "_persist_chat_account_stats_payload", lambda payload: {"status": "ok"})

    payloads = chat_accounts.iter_chat_account_stats_refresh_payloads()

    initial_payload = next(payloads)
    assert initial_payload["pending_count"] == 2
    assert [account["check_status"] for account in initial_payload["providers"][0]["accounts"]] == ["pending"]
    assert [account["check_status"] for account in initial_payload["providers"][1]["accounts"]] == ["pending"]

    partial_payload_ready = threading.Event()
    partial_payload_holder: list[dict[str, object]] = []

    def load_partial_payload() -> None:
        partial_payload_holder.append(next(payloads))
        partial_payload_ready.set()

    partial_thread = threading.Thread(target=load_partial_payload)
    partial_thread.start()
    assert partial_payload_ready.wait(timeout=1.0)
    partial_payload = partial_payload_holder[0]
    assert partial_payload["pending_count"] == 1
    assert [account["check_status"] for account in partial_payload["providers"][0]["accounts"]] == ["pending"]
    assert [account["check_status"] for account in partial_payload["providers"][1]["accounts"]] == ["ok"]

    release_alpha.set()
    partial_thread.join(timeout=1.0)

    final_payload = next(payloads)
    assert "pending_count" not in final_payload
    assert final_payload["history"]["status"] == "ok"
    assert [account["check_status"] for account in final_payload["providers"][0]["accounts"]] == ["ok"]
    assert [account["check_status"] for account in final_payload["providers"][1]["accounts"]] == ["ok"]

    with pytest.raises(StopIteration):
        next(payloads)


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
                "usage_summary": "Burst 10%, Weekly 20%",
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

    def fake_wait(interval_sec: float, input_stream) -> bool:  # type: ignore[no-untyped-def]
        del input_stream
        wait_calls.append(interval_sec)
        if len(wait_calls) >= 2:
            raise KeyboardInterrupt()
        return False

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
    assert wait_calls == [60.0, 61.0]
    assert "snapshot-1" in rendered
    assert "snapshot-2" in rendered
    assert rendered.count(chat_commands._CHAT_ACCOUNTS_LOOP_REFRESHING_MESSAGE) == 1
    assert "[loop] refreshes every 60s; press Enter to refresh now; Ctrl-C to stop" in rendered
    assert "[loop] refreshes every 61s; press Enter to refresh now; Ctrl-C to stop" in rendered


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

    def fake_render_progressive(
        loop_args: argparse.Namespace,
        *,
        frame,
        renderer,
        interval_sec: float,
    ) -> None:  # type: ignore[no-untyped-def]
        del interval_sec
        assert loop_args is args
        assert frame is not None
        assert renderer is not None
        events.append("render")

    def fake_wait(interval_sec: float, input_stream) -> bool:  # type: ignore[no-untyped-def]
        del interval_sec, input_stream
        raise KeyboardInterrupt()

    class FakeTTYOutput(io.StringIO):
        def isatty(self) -> bool:
            return True

        def write(self, text: str) -> int:
            return super().write(text)

    monkeypatch.setattr(chat_commands, "_render_chat_accounts_stats_progressive_tty", fake_render_progressive)

    exit_code = chat_commands._loop_chat_accounts_stats(
        args,
        input_stream=io.StringIO(),
        output_stream=FakeTTYOutput(),
        interval_sec=60.0,
        wait_for_trigger=fake_wait,
    )

    assert exit_code == 0
    assert events == ["render"]


def test_loop_chat_accounts_stats_shows_refreshing_feedback_before_next_tty_fetch(monkeypatch) -> None:
    args = argparse.Namespace(
        instance_ids=[],
        providers=None,
        refresh_usage=False,
        full_output=False,
        output_format="json",
        loop=True,
    )

    events: list[str] = []
    wait_calls = 0

    def fake_render_progressive(
        loop_args: argparse.Namespace,
        *,
        frame,
        renderer,
        interval_sec: float,
    ) -> None:  # type: ignore[no-untyped-def]
        del interval_sec
        assert loop_args is args
        assert frame is not None
        assert renderer is not None
        events.append(f"render:{len([event for event in events if event.startswith('render:')]) + 1}")

    def fake_wait(interval_sec: float, input_stream) -> bool:  # type: ignore[no-untyped-def]
        nonlocal wait_calls
        del interval_sec, input_stream
        wait_calls += 1
        events.append(f"wait:{wait_calls}")
        if wait_calls >= 2:
            raise KeyboardInterrupt()
        return False

    class FakeTTYOutput(io.StringIO):
        def isatty(self) -> bool:
            return True

        def write(self, text: str) -> int:
            return super().write(text)

    monkeypatch.setattr(chat_commands, "_render_chat_accounts_stats_progressive_tty", fake_render_progressive)

    exit_code = chat_commands._loop_chat_accounts_stats(
        args,
        input_stream=io.StringIO(),
        output_stream=FakeTTYOutput(),
        interval_sec=60.0,
        wait_for_trigger=fake_wait,
    )

    assert exit_code == 0
    assert events == [
        "render:1",
        "wait:1",
        "render:2",
        "wait:2",
    ]


def test_chat_accounts_stats_loop_frame_renders_progress_body_and_countdown() -> None:
    frame = chat_commands._ChatAccountsStatsLoopFrame(
        interval_sec=60.0,
        body_text="snapshot-final",
        refresh_progress_text="[refresh] 1/2 complete; 1 pending",
        next_refresh_at_monotonic=65.0,
    )

    rendered = frame.render_text(now_monotonic=5.0)

    assert "[refresh] 1/2 complete; 1 pending" in rendered
    assert "snapshot-final" in rendered
    assert "next refresh in 01:00" in rendered


def test_inline_progress_text_styles_fill_and_track_spans() -> None:
    label = "    resets | Mon | 3d"
    geometry = chat_commands._InlineBarGroupGeometry(prefix_width=0, main_width=40, suffix_width=0)
    rendered = chat_commands._inline_progress_text(label, 25, geometry)
    expected_fill_spans = _offset_gradient_runs(
        0,
        0,
        10,
        width=40,
        palette=chat_commands._CHAT_ACCOUNTS_RESET_BAR_PALETTE,
    )

    assert rendered.plain == label.ljust(40)
    assert _span_tuples(rendered) == [
        (0, 40, chat_commands._CHAT_ACCOUNTS_RESET_PROGRESS_TRACK_STYLE),
        *expected_fill_spans,
    ]

    full = chat_commands._inline_progress_text(label, 100, geometry)
    full_fill_spans = _offset_gradient_runs(
        0,
        0,
        40,
        width=40,
        palette=chat_commands._CHAT_ACCOUNTS_RESET_BAR_PALETTE,
    )
    assert full_fill_spans[0] in _span_tuples(full)
    assert full_fill_spans[-1] in _span_tuples(full)

    empty = chat_commands._inline_progress_text(label, 0, geometry)
    assert _span_tuples(empty) == [
        (0, 40, chat_commands._CHAT_ACCOUNTS_RESET_PROGRESS_TRACK_STYLE),
    ]


def test_inline_usage_time_text_styles_usage_fill_only() -> None:
    label = "  usage/time | 70% / 50% = 1.4 | Burst"
    geometry = chat_commands._InlineBarGroupGeometry(prefix_width=0, main_width=48, suffix_width=0)

    rendered = chat_commands._inline_usage_time_text(
        label,
        used_percent=70,
        geometry=geometry,
    )
    spans = _span_tuples(rendered)
    expected_fill_spans = _offset_gradient_runs(
        0,
        0,
        33,
        width=48,
        palette=chat_commands._CHAT_ACCOUNTS_USAGE_BAR_PALETTE,
    )

    assert rendered.plain == label.ljust(48)
    assert chat_commands._usage_time_line_data(label) == chat_commands._UsageTimeLineData(
        used_percent=70,
        elapsed_percent=50,
        ratio=1.4,
    )
    assert (0, 48, chat_commands._CHAT_ACCOUNTS_USAGE_TIME_TRACK_STYLE) in spans
    assert expected_fill_spans[0] in spans
    assert expected_fill_spans[-1] in spans


def test_inline_bar_palette_cell_styles_are_interpolated() -> None:
    assert chat_commands._cell_gradient_style(
        0,
        width=5,
        palette=chat_commands._CHAT_ACCOUNTS_USAGE_BAR_PALETTE,
    ) == "bright_white on #14b8a6"
    assert chat_commands._cell_gradient_style(
        2,
        width=5,
        palette=chat_commands._CHAT_ACCOUNTS_USAGE_BAR_PALETTE,
    ) == "bright_white on #facc15"
    assert chat_commands._cell_gradient_style(
        4,
        width=5,
        palette=chat_commands._CHAT_ACCOUNTS_USAGE_BAR_PALETTE,
    ) == "bright_white on #dc2626"
    assert chat_commands._cell_gradient_style(
        1,
        width=3,
        palette=chat_commands._CHAT_ACCOUNTS_RESET_BAR_PALETTE,
    ) == "bright_white on #0891b2"
    assert chat_commands._cell_gradient_style(
        1,
        width=3,
        palette=chat_commands._CHAT_ACCOUNTS_RATIO_SLOW_BAR_PALETTE,
    ) == "bright_white on #3b82f6"
    assert chat_commands._cell_gradient_style(
        1,
        width=3,
        palette=chat_commands._CHAT_ACCOUNTS_RATIO_FAST_BAR_PALETTE,
    ) == "bright_white on #f59e0b"
    assert chat_commands._sample_hex_palette(("#000000", "#ffffff"), 0.5) == "#808080"


def test_inline_bar_row_places_emoji_suffix_outside_bar_main_text() -> None:
    line = "  usage/time | 20% /  7% = 2.9 | Weekly 🔥🔥"
    main_text, suffix_text = chat_commands._split_usage_time_main_suffix(line)
    geometry = chat_commands._InlineBarGroupGeometry(
        prefix_width=0,
        main_width=cell_len(main_text),
        suffix_width=cell_len(suffix_text),
    )
    row = chat_commands._InlineBarRow(
        group_id="usage",
        prefix_text="",
        main_text=main_text,
        suffix_text=suffix_text,
        bar=chat_commands._InlineUsageTimeBar(used_percent=20),
    )

    rendered = chat_commands._render_inline_bar_row(row, geometry)
    spans = _span_tuples(rendered)
    track_span = (0, len(main_text), chat_commands._CHAT_ACCOUNTS_USAGE_TIME_TRACK_STYLE)
    fill_cells = math.floor(geometry.main_width * 0.2)
    usage_spans = _offset_gradient_runs(
        0,
        0,
        fill_cells,
        width=geometry.main_width,
        palette=chat_commands._CHAT_ACCOUNTS_USAGE_BAR_PALETTE,
    )

    assert main_text == "  usage/time | 20% /  7% = 2.9 | Weekly"
    assert suffix_text == " 🔥🔥"
    assert rendered.plain == line
    assert track_span in spans
    assert usage_spans[0] in spans
    assert usage_spans[-1] in spans
    assert usage_spans[0][0] == 0
    assert cell_len(rendered.plain[: len(main_text)]) == geometry.main_width
    assert usage_spans[-1][1] == fill_cells


def test_loop_rich_text_aligns_usage_time_and_reset_bars_to_shared_geometry() -> None:
    first_usage = "  usage/time | 75% / 50% = 1.5 | Weekly Account 🔥"
    second_usage = "  usage/time | 25% / 50% = 0.5 | Burst ❄️"
    first_usage_main = "  usage/time | 75% / 50% = 1.5 | Weekly Account"
    second_usage_main = "  usage/time | 25% / 50% = 0.5 | Burst"
    first_reset = "      resets | Mon 04-20 12:01 | 3d 11h 43m"
    second_reset = "      resets | Fri 04-17 22:00 | 10h"
    frame = chat_commands._ChatAccountsStatsLoopFrame(
        interval_sec=60.0,
        body_text=(
            "# Chat Accounts Usage\n"
            "\n"
            f"{first_usage}\n"
            f"{first_reset}\n"
            f"{second_usage}\n"
            f"{second_reset}"
        ),
        next_refresh_at_monotonic=65.0,
    )

    rendered = chat_commands._render_chat_accounts_stats_loop_rich_text(
        frame,
        now_monotonic=5.0,
        width=48,
    )
    shared_width = max(
        cell_len(first_usage_main),
        cell_len(second_usage_main),
        cell_len(first_reset),
        cell_len(second_reset),
    )
    first_usage_start = rendered.plain.index(first_usage_main)
    second_usage_start = rendered.plain.index(second_usage_main)
    first_reset_start = rendered.plain.index("      resets | Mon 04-20")
    second_reset_start = rendered.plain.index("      resets | Fri 04-17")
    first_suffix_start = rendered.plain.index("🔥")
    second_suffix_start = rendered.plain.index("❄️")
    spans = _span_tuples(rendered)
    first_usage_spans = _offset_gradient_runs(
        first_usage_start,
        0,
        math.floor(shared_width * 0.75),
        width=shared_width,
        palette=chat_commands._CHAT_ACCOUNTS_USAGE_BAR_PALETTE,
    )
    second_usage_spans = _offset_gradient_runs(
        second_usage_start,
        0,
        math.floor(shared_width * 0.25),
        width=shared_width,
        palette=chat_commands._CHAT_ACCOUNTS_USAGE_BAR_PALETTE,
    )
    first_reset_spans = _offset_gradient_runs(
        first_reset_start,
        0,
        math.floor(shared_width * 0.5),
        width=shared_width,
        palette=chat_commands._CHAT_ACCOUNTS_RESET_BAR_PALETTE,
    )
    second_reset_spans = _offset_gradient_runs(
        second_reset_start,
        0,
        math.floor(shared_width * 0.5),
        width=shared_width,
        palette=chat_commands._CHAT_ACCOUNTS_RESET_BAR_PALETTE,
    )

    assert first_usage_main in rendered.plain
    assert (
        first_usage_start,
        first_usage_start + shared_width,
        chat_commands._CHAT_ACCOUNTS_USAGE_TIME_TRACK_STYLE,
    ) in spans
    assert first_usage_spans[0] in spans
    assert first_usage_spans[-1] in spans
    assert second_usage_spans[0] in spans
    assert second_usage_spans[-1] in spans
    assert (
        first_reset_start,
        first_reset_start + shared_width,
        chat_commands._CHAT_ACCOUNTS_RESET_PROGRESS_TRACK_STYLE,
    ) in spans
    assert first_reset_spans[0] in spans
    assert first_reset_spans[-1] in spans
    assert (
        second_reset_start,
        second_reset_start + shared_width,
        chat_commands._CHAT_ACCOUNTS_RESET_PROGRESS_TRACK_STYLE,
    ) in spans
    assert second_reset_spans[0] in spans
    assert second_reset_spans[-1] in spans
    assert first_suffix_start == first_usage_start + shared_width + 1
    assert second_suffix_start == second_usage_start + shared_width + 1


def test_loop_rich_text_keeps_ratio_bar_only_for_selected_accounts_aggregate() -> None:
    aggregate_usage = "  usage/time | 30% / 86% = 0.3 | Weekly ❄️❄️"
    aggregate_usage_main = "  usage/time | 30% / 86% = 0.3 | Weekly"
    account_usage = "  usage/time | 75% / 50% = 1.5 | Weekly 🔥"
    account_usage_main = "  usage/time | 75% / 50% = 1.5 | Weekly"
    reset = "      resets | Mon 04-20 12:01 | 3d 11h 43m"
    frame = chat_commands._ChatAccountsStatsLoopFrame(
        interval_sec=60.0,
        body_text=(
            "Selected accounts aggregate:\n"
            f"{aggregate_usage}\n"
            "  coverage | 2/3 accounts\n"
            "\n"
            "⬢ codex-a (Codex A):\n"
            f"{account_usage}\n"
            f"{reset}"
        ),
        next_refresh_at_monotonic=65.0,
    )

    rendered = chat_commands._render_chat_accounts_stats_loop_rich_text(
        frame,
        now_monotonic=5.0,
        width=48,
    )
    shared_width = max(cell_len(aggregate_usage_main), cell_len(account_usage_main), cell_len(reset))
    center = shared_width // 2
    aggregate_start = rendered.plain.index(aggregate_usage_main)
    account_start = rendered.plain.index(account_usage_main)
    spans = _span_tuples(rendered)
    ratio_range = chat_commands._ratio_cell_range(
        0.3,
        chat_commands._InlineBarGroupGeometry(prefix_width=0, main_width=shared_width, suffix_width=0),
    )
    assert ratio_range is not None
    ratio_start, ratio_end, ratio_palette = ratio_range
    aggregate_ratio_spans = _offset_gradient_runs(
        aggregate_start,
        ratio_start,
        ratio_end,
        width=shared_width,
        palette=ratio_palette,
    )
    account_usage_spans = _offset_gradient_runs(
        account_start,
        0,
        math.floor(shared_width * 0.75),
        width=shared_width,
        palette=chat_commands._CHAT_ACCOUNTS_USAGE_BAR_PALETTE,
    )
    account_row_spans = [
        span for span in spans if account_start <= span[0] and span[1] <= account_start + shared_width
    ]

    assert center == shared_width // 2
    assert ratio_start == center - math.floor(center * 0.7)
    assert ratio_end == center
    assert aggregate_ratio_spans[0] in spans
    assert aggregate_ratio_spans[-1] in spans
    assert account_row_spans == [
        (
            account_start,
            account_start + shared_width,
            chat_commands._CHAT_ACCOUNTS_USAGE_TIME_TRACK_STYLE,
        ),
        *account_usage_spans,
    ]


def test_render_chat_accounts_stats_progressive_tty_repaints_each_partial_snapshot(monkeypatch) -> None:
    args = argparse.Namespace(
        instance_ids=[],
        providers=None,
        refresh_usage=False,
        full_output=False,
        output_format="json",
        loop=True,
    )

    monkeypatch.setattr(
        chat_commands,
        "iter_chat_account_stats_refresh_payloads",
        lambda **kwargs: iter(
            (
                {"account_count": 2, "pending_count": 2, "completed_count": 0, "providers": []},
                {"account_count": 2, "providers": []},
            )
        ),
    )

    def fake_format(loop_args: argparse.Namespace, payload: dict[str, object]) -> str:
        assert loop_args is args
        pending_count = payload.get("pending_count")
        if pending_count is not None:
            return f"snapshot-pending-{pending_count}"
        return "snapshot-final"

    class FakeLive:
        def __init__(self, renderable, **kwargs) -> None:  # type: ignore[no-untyped-def]
            self.initial_renderable = renderable
            self.kwargs = kwargs
            self.started_with_refresh: list[bool] = []
            self.updated_frames: list[str] = []

        def start(self, *, refresh: bool = False) -> None:
            self.started_with_refresh.append(refresh)

        def update(self, renderable, *, refresh: bool = False) -> None:  # type: ignore[no-untyped-def]
            assert refresh is True
            self.updated_frames.append(renderable.plain)

        def stop(self) -> None:
            pass

    live_instances: list[FakeLive] = []

    def fake_live_factory(renderable, **kwargs) -> FakeLive:  # type: ignore[no-untyped-def]
        live = FakeLive(renderable, **kwargs)
        live_instances.append(live)
        return live

    monkeypatch.setattr(chat_commands, "_format_chat_accounts_stats_payload_output", fake_format)

    frame = chat_commands._ChatAccountsStatsLoopFrame(interval_sec=60.0)
    renderer = chat_commands._ChatAccountsStatsLoopTTYRenderer(
        output_stream=io.StringIO(),
        now_monotonic=lambda: 0.0,
        live_factory=fake_live_factory,
    )

    chat_commands._render_chat_accounts_stats_progressive_tty(
        args,
        frame=frame,
        renderer=renderer,
        interval_sec=60.0,
    )

    assert len(live_instances) == 1
    live = live_instances[0]
    assert live.kwargs["screen"] is True
    assert live.kwargs["auto_refresh"] is False
    assert live.kwargs["transient"] is False
    assert live.started_with_refresh == [True]
    rendered_frames = live.updated_frames
    assert len(rendered_frames) == 3
    assert rendered_frames[0].startswith(chat_commands._CHAT_ACCOUNTS_LOOP_REFRESHING_MESSAGE)
    assert "snapshot-pending-2" in rendered_frames[1]
    assert "[refresh] 0/2 complete; 2 pending" in rendered_frames[1]
    assert "snapshot-final" in rendered_frames[2]
    assert "next refresh in" not in rendered_frames[2]


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
        triggered_by_user = chat_commands._wait_for_chat_accounts_loop_trigger(1.0, FakeTTYInput(read_stream))
        elapsed = time.perf_counter() - start
    finally:
        read_stream.close()
        write_stream.close()

    assert triggered_by_user is True
    assert elapsed < 0.5


def test_wait_for_chat_accounts_loop_trigger_with_tty_countdown_repaints_full_frame(monkeypatch) -> None:
    wait_times = iter((0.0, 1.0))
    renderer_times = iter((1.0, 2.0))
    monkeypatch.setattr(chat_commands.time, "monotonic", lambda: next(wait_times))
    monkeypatch.setattr(chat_commands.time, "sleep", lambda seconds: None)

    class FakeLive:
        def __init__(self, renderable, **kwargs) -> None:  # type: ignore[no-untyped-def]
            del renderable
            self.kwargs = kwargs
            self.updated_frames: list[str] = []

        def start(self, *, refresh: bool = False) -> None:
            assert refresh is True

        def update(self, renderable, *, refresh: bool = False) -> None:  # type: ignore[no-untyped-def]
            assert refresh is True
            self.updated_frames.append(renderable.plain)

        def stop(self) -> None:
            pass

    live_instances: list[FakeLive] = []

    def fake_live_factory(renderable, **kwargs) -> FakeLive:  # type: ignore[no-untyped-def]
        live = FakeLive(renderable, **kwargs)
        live_instances.append(live)
        return live

    frame = chat_commands._ChatAccountsStatsLoopFrame(
        interval_sec=2.0,
        body_text="snapshot-final",
    )
    frame.finish_refresh(next_refresh_at_monotonic=2.0)
    renderer = chat_commands._ChatAccountsStatsLoopTTYRenderer(
        output_stream=io.StringIO(),
        now_monotonic=lambda: next(renderer_times),
        live_factory=fake_live_factory,
    )

    triggered_by_user = chat_commands._wait_for_chat_accounts_loop_trigger_with_tty_countdown(
        frame,
        renderer,
        io.StringIO(),
    )

    assert len(live_instances) == 1
    assert live_instances[0].kwargs["screen"] is True
    rendered = "\n".join(live_instances[0].updated_frames)
    assert triggered_by_user is False
    assert rendered.count("snapshot-final") == 2
    assert "next refresh in 00:01" in rendered
    assert "next refresh in 00:00" in rendered


def test_loop_chat_accounts_stats_uses_tty_countdown_between_refreshes(monkeypatch) -> None:
    args = argparse.Namespace(
        instance_ids=[],
        providers=None,
        refresh_usage=False,
        full_output=False,
        output_format="json",
        loop=True,
    )

    events: list[str] = []

    def fake_render_progressive(
        loop_args: argparse.Namespace,
        *,
        frame,
        renderer,
        interval_sec: float,
    ) -> None:  # type: ignore[no-untyped-def]
        assert loop_args is args
        assert frame is not None
        assert renderer is not None
        events.append(f"render:{interval_sec}")

    def fake_wait_with_countdown(
        frame,
        renderer,
        input_stream,
        *,
        tick_sec: float = 1.0,
    ) -> bool:  # type: ignore[no-untyped-def]
        del input_stream, tick_sec
        assert frame is not None
        assert renderer is not None
        assert frame.refreshing is False
        assert frame.next_refresh_at_monotonic is not None
        events.append(f"countdown:{frame.interval_sec}")
        raise KeyboardInterrupt()

    class FakeTTYOutput(io.StringIO):
        def isatty(self) -> bool:
            return True

    monkeypatch.setattr(chat_commands, "_render_chat_accounts_stats_progressive_tty", fake_render_progressive)
    monkeypatch.setattr(
        chat_commands,
        "_wait_for_chat_accounts_loop_trigger_with_tty_countdown",
        fake_wait_with_countdown,
    )

    exit_code = chat_commands._loop_chat_accounts_stats(
        args,
        input_stream=io.StringIO(),
        output_stream=FakeTTYOutput(),
        interval_sec=60.0,
    )

    assert exit_code == 0
    assert events == ["render:60.0", "countdown:60.0"]


def test_loop_chat_accounts_stats_resets_interval_after_enter(monkeypatch) -> None:
    args = argparse.Namespace(
        instance_ids=[],
        providers=None,
        refresh_usage=False,
        full_output=False,
        output_format="json",
        loop=True,
    )

    outputs = iter(("snapshot-1", "snapshot-2", "snapshot-3"))
    monkeypatch.setattr(
        chat_commands,
        "_render_chat_accounts_stats_output",
        lambda loop_args: next(outputs),
    )

    wait_calls: list[float] = []

    def fake_wait(interval_sec: float, input_stream) -> bool:  # type: ignore[no-untyped-def]
        del input_stream
        wait_calls.append(interval_sec)
        if len(wait_calls) == 1:
            return False
        if len(wait_calls) == 2:
            return True
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
    assert wait_calls == [60.0, 61.0, 60.0]
    assert "[loop] refreshes every 60s; press Enter to refresh now; Ctrl-C to stop" in rendered
    assert "[loop] refreshes every 61s; press Enter to refresh now; Ctrl-C to stop" in rendered


def test_loop_chat_accounts_stats_caps_interval_at_ten_minutes(monkeypatch) -> None:
    args = argparse.Namespace(
        instance_ids=[],
        providers=None,
        refresh_usage=False,
        full_output=False,
        output_format="json",
        loop=True,
    )

    monkeypatch.setattr(
        chat_commands,
        "_render_chat_accounts_stats_output",
        lambda loop_args: "snapshot",
    )

    wait_calls: list[float] = []

    def fake_wait(interval_sec: float, input_stream) -> bool:  # type: ignore[no-untyped-def]
        del input_stream
        wait_calls.append(interval_sec)
        if len(wait_calls) >= 3:
            raise KeyboardInterrupt()
        return False

    output_stream = io.StringIO()
    exit_code = chat_commands._loop_chat_accounts_stats(
        args,
        input_stream=io.StringIO(),
        output_stream=output_stream,
        interval_sec=599.0,
        wait_for_trigger=fake_wait,
    )

    assert exit_code == 0
    assert wait_calls == [599.0, 600.0, 600.0]


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
    assert [provider["provider"] for provider in payload["providers"]] == ["codex", "claude-code", "copilot-cli"]
    assert all(provider["account_count"] == 0 for provider in payload["providers"])

    assert main(["chat", "accounts", "stats", "--full-output", "--output", "markdown"]) == 0
    output = capsys.readouterr().out
    assert "# Chat Accounts Stats" in output
    assert "- Recorded at: LOCAL_TIME" in output
    assert "- History: ok" in output
    assert "- History segment: " in output
    assert "## codex" in output
    assert "## claude-code" in output
    assert "## copilot-cli" in output


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
                "usage_progression_limit": "Burst",
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
    assert "⬢ codex-tk (Codex tk):" in output
    assert "  usage/time | 64% /  0% = n/a | Burst" in output
    assert "      resets | Wed 03-26 01:40 | 17h 40m" in output
    assert "  usage/time | 20% / 80% = 0.2 | Weekly" in output
    assert "      resets | Wed 03-26 17:10 | 1d 9h 10m" in output
    assert "✺ claude-main (Claude main):" in output
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
                            "provider": "codex",
                            "usage": {
                                "limits": [
                                    {
                                        **_usage_over_time_limit_payload(
                                            limit_name="burst",
                                            limit_label="Burst",
                                            used_percent=70,
                                            period_started_at="2026-03-25T04:30:00Z",
                                            period_ends_at="2026-03-25T14:30:00Z",
                                        ),
                                    }
                                ]
                            },
                        },
                        {
                            "id": "burst-high",
                            "label": "Burst high",
                            "provider": "copilot-cli",
                            "usage": {
                                "limits": [
                                    {
                                        **_usage_over_time_limit_payload(
                                            limit_name="burst",
                                            limit_label="Burst",
                                            used_percent=20,
                                            period_started_at="2026-03-25T09:30:00Z",
                                            period_ends_at="2026-03-25T14:30:00Z",
                                        ),
                                    },
                                    {
                                        **_usage_over_time_limit_payload(
                                            limit_name="weekly",
                                            limit_label="Weekly",
                                            used_percent=100,
                                            period_started_at="2026-03-19T12:00:00Z",
                                            period_ends_at="2026-03-26T12:00:00Z",
                                        ),
                                    },
                                ]
                            },
                        },
                    ]
                }
            ],
        }
    )

    assert "🤖 burst-high (Burst high):" in output
    assert "⬢ steady-low (Steady low):" in output
    assert output.index("burst-high (Burst high):") < output.index("steady-low (Steady low):")
    assert "  usage/time | 100% / 86% = 1.2 | Weekly 🔥 ☠️" in output
    assert "  usage/time | 70% / 75% = 0.9 | Burst ❄️" in output


def test_format_chat_account_stats_usage_shows_pending_refresh_accounts() -> None:
    output = chat_accounts.format_chat_account_stats_usage(
        {
            "providers": [
                {
                    "accounts": [
                        {
                            "id": "pending-account",
                            "label": "Pending account",
                            "provider": "codex",
                            "check_status": "pending",
                            "summary": "Refreshing account status...",
                            "usage_status": "pending",
                            "usage_message": "Waiting for provider response.",
                        }
                    ]
                }
            ]
        }
    )

    assert "⬢ pending-account (Pending account):" in output
    assert "  refresh | pending" in output
    assert "Waiting for provider response." in output


def test_format_chat_account_stats_usage_shows_cold_marker_only_on_most_active_limit() -> None:
    output = chat_accounts.format_chat_account_stats_usage(
        {
            "recorded_at": "2026-03-25T12:00:00Z",
            "providers": [
                {
                    "accounts": [
                        {
                            "id": "all-cold",
                            "label": "All cold",
                            "provider": "codex",
                            "usage": {
                                "limits": [
                                    {
                                        **_usage_over_time_limit_payload(
                                            limit_name="burst",
                                            limit_label="Burst",
                                            used_percent=20,
                                            period_started_at="2026-03-25T09:30:00Z",
                                            period_ends_at="2026-03-25T14:30:00Z",
                                        ),
                                    },
                                    {
                                        **_usage_over_time_limit_payload(
                                            limit_name="weekly",
                                            limit_label="Weekly",
                                            used_percent=70,
                                            period_started_at="2026-03-19T12:00:00Z",
                                            period_ends_at="2026-03-26T12:00:00Z",
                                        ),
                                    },
                                ]
                            },
                        }
                    ]
                }
            ],
        }
    )

    assert "  usage/time | 20% / 50% = 0.4 | Burst" in output
    assert "  usage/time | 70% / 86% = 0.8 | Weekly ❄️" in output


def test_usage_peak_ratio_marker_gradient() -> None:
    assert chat_accounts._usage_peak_ratio_marker(1.62) == "🔥🔥"
    assert chat_accounts._usage_peak_ratio_marker(1.22) == "🔥"
    assert chat_accounts._usage_peak_ratio_marker(1.05) is None
    assert chat_accounts._usage_peak_ratio_marker(1.00) is None
    assert chat_accounts._usage_peak_ratio_marker(0.95) is None
    assert chat_accounts._usage_peak_ratio_marker(0.74) == "❄️"
    assert chat_accounts._usage_peak_ratio_marker(0.31) == "❄️❄️"
    assert chat_accounts._usage_peak_ratio_marker(0.0) is None
    assert chat_accounts._usage_peak_ratio_marker(None) is None


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


def test_chat_accounts_stats_usage_compacts_codex_token_expired_errors(
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
                message=(
                    "failed to fetch codex rate limits: GET "
                    "https://chatgpt.com/backend-api/wham/usage failed: 401 Unauthorized; "
                    'content-type=text/plain; body={\n  "error": {\n    "message": '
                    '"Provided authentication token is expired. Please try signing in again.",\n'
                    '    "type": null,\n    "code": "token_expired",\n    "param": null\n  },\n'
                    '  "status": 401\n}'
                ),
            )
        ),
    )

    assert main(["chat", "accounts", "stats", "--output", "usage"]) == 0
    output = capsys.readouterr().out

    assert "codex-main (Codex main):" in output
    assert "  usage | error" in output
    assert "     | command_failed: Codex authentication token expired" in output
    assert "     | 401 Unauthorized | token_expired" in output
    assert "     | Provided authentication token is expired. Please try signing in again." in output
    assert "     | Sign in again with the configured Codex CLI and refresh." in output
    assert "backend-api/wham/usage" not in output
    assert "body={" not in output


def test_chat_accounts_stats_usage_shows_top_level_selected_accounts_aggregate(
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
                "id": "codex-a",
                "label": "Codex A",
                "cli_command": ["codex"],
            },
            {
                "provider": "codex",
                "id": "codex-b",
                "label": "Codex B",
                "cli_command": ["codex"],
            },
            {
                "provider": "claude-code",
                "id": "claude-main",
                "label": "Claude main",
                "cli_command": ["claude"],
            },
        ],
        accounts_usage_total={
            "label": "Selected accounts aggregate",
            "instance_ids": ["codex-a", "codex-b", "claude-main"],
            "limit_class": "usage_over_time",
            "limit_name": "weekly",
        },
    )

    monkeypatch.setattr(chat_accounts, "_utc_now_iso", lambda: "2026-03-25T12:00:00Z")

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

    def fake_codex_usage(instance: chat_accounts.AccountProviderContext) -> dict[str, object]:
        used_percent = 20 if instance.instance_id == "codex-a" else 40
        return {
            "rateLimits": {
                "limitId": "codex",
                "primary": {
                    "usedPercent": 0,
                    "windowDurationMins": 300,
                    "resetsAt": 1_774_526_400,
                },
                "secondary": {
                    "usedPercent": used_percent,
                    "windowDurationMins": 10_080,
                    "resetsAt": 1_774_526_400,
                },
            }
        }

    monkeypatch.setattr(chat_accounts.subprocess, "run", fake_run)
    monkeypatch.setattr(chat_accounts, "_read_codex_account_rate_limits", fake_codex_usage)

    assert main(["chat", "accounts", "stats", "--output", "usage"]) == 0
    output = capsys.readouterr().out

    assert "Selected accounts aggregate:" in output
    assert "  usage/time | 30% / 86% = 0.3 | Weekly ❄️❄️" in output
    assert "  coverage | 2/3 accounts" in output
    assert "--------------------------" in output
    assert output.index("Selected accounts aggregate:") < output.index("⬢ codex-b (Codex B):")


def test_chat_accounts_stats_usage_total_rejects_unknown_instance_ids(
    tmp_path: Path,
    monkeypatch,
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
                "id": "codex-a",
                "label": "Codex A",
                "cli_command": ["codex"],
            }
        ],
        accounts_usage_total={
            "instance_ids": ["missing-account"],
            "limit_class": "usage_over_time",
            "limit_name": "weekly",
        },
    )

    with pytest.raises(chat_accounts.CliError, match="chat.accounts_usage_total.instance_ids references unknown"):
        chat_accounts.chat_account_stats()


def test_chat_accounts_stats_usage_compacts_claude_authentication_failures(
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
        "_collect_claude_code_live_usage",
        lambda instance: (_ for _ in ()).throw(
            chat_accounts.AccountCommandError(
                error_type="command_failed",
                message="\n".join(
                    [
                        json.dumps(
                            {
                                "type": "system",
                                "subtype": "init",
                                "session_id": "session-123",
                                "model": "claude-haiku-4-5-20251001",
                            }
                        ),
                        json.dumps(
                            {
                                "type": "assistant",
                                "message": {
                                    "content": [
                                        {
                                            "type": "text",
                                            "text": (
                                                "Failed to authenticate. API Error: 403\n"
                                                '{"error":{"type":"forbidden","message":"Request not allowed"}}'
                                            ),
                                        }
                                    ]
                                },
                                "error": "authentication_failed",
                            }
                        ),
                        json.dumps(
                            {
                                "type": "result",
                                "subtype": "success",
                                "is_error": True,
                                "result": (
                                    "Failed to authenticate. API Error: 403\n"
                                    '{"error":{"type":"forbidden","message":"Request not allowed"}}'
                                ),
                            }
                        ),
                    ]
                ),
            )
        ),
    )

    assert main(["chat", "accounts", "stats", "--output", "usage", "--refresh-usage"]) == 0
    output = capsys.readouterr().out

    assert "claude-main (Claude main):" in output
    assert "  usage | error" in output
    assert "     | command_failed: Claude Code authentication failed" in output
    assert "     | 403 Forbidden | authentication_failed | forbidden" in output
    assert "     | Request not allowed" in output
    assert "     | Sign in again with the configured Claude Code CLI and refresh." in output
    assert '"subtype":"init"' not in output
    assert '"session_id":"session-123"' not in output


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


def test_format_chat_account_usage_error_detail_lines_wrap_long_messages() -> None:
    detail_lines = chat_accounts._format_chat_account_usage_error_detail_lines(
        {
            "type": "command_failed",
            "message": (
                "provider command returned unexpectedly verbose output that should wrap cleanly "
                "instead of overflowing the compact usage interface"
            ),
            "detail_lines": [
                (
                    "Additional context should also wrap to the same width so secondary detail "
                    "lines stay readable in loop mode."
                )
            ],
        }
    )

    assert detail_lines is not None
    assert len(detail_lines) >= 3
    assert detail_lines[0].startswith("command_failed:")
    assert all(len(line) <= chat_accounts.CHAT_ACCOUNT_USAGE_ERROR_DETAIL_WIDTH for line in detail_lines)


def test_usage_progression_marker_evolves_with_usage_percent() -> None:
    assert chat_accounts._usage_progression_marker(10) is None
    assert chat_accounts._usage_progression_marker(40) is None
    assert chat_accounts._usage_progression_marker(99) is None
    assert chat_accounts._usage_progression_marker(100) == "☠️"


def test_usage_time_progression_marker_only_appears_above_ninety_percent() -> None:
    assert chat_accounts._usage_time_progression_marker(90) is None
    assert chat_accounts._usage_time_progression_marker(91) == "🕒"


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
    assert payload["usage_summary"] == "Weekly 42%"
    assert payload["usage_refresh_cost_usd"] == 0.004
    limit_payload = payload["usage"]["limits"][0]
    assert limit_payload["limit_class"] == "usage_over_time"
    assert limit_payload["limit_name"] == "weekly"
    assert _usage_over_time_data(limit_payload)["period_duration_mins"] == 10_080
    assert _usage_over_time_data(limit_payload)["period_started_at"] == "2026-03-19T21:10:27Z"
    assert _usage_over_time_data(limit_payload)["period_ends_at"] == "2026-03-26T21:10:27Z"
    assert _usage_over_time_data(limit_payload)["resets_at"] == "2026-03-26T21:10:27Z"


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
            _usage_over_time_limit_payload(
                limit_name="hourly",
                limit_label="Hourly",
                used_percent=0,
                period_started_at="2026-03-25T12:00:00Z",
                period_ends_at="2026-03-25T13:00:00Z",
            ),
            recorded_at=recorded_at,
        )
        == 50
    )
    assert (
        chat_accounts._format_usage_limit_elapsed_percent(
            _usage_over_time_limit_payload(
                limit_name="hourly",
                limit_label="Hourly",
                used_percent=0,
                period_ends_at="2026-03-25T13:00:00Z",
                period_duration_mins=60,
            ),
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
    assert [limit["limit_name"] for limit in limits] == ["premium", "chat"]
    assert [_usage_over_time_data(limit)["used_percent"] for limit in limits] == [75, 75]
    assert [_usage_over_time_data(limit)["period_duration_mins"] for limit in limits] == [44_640, 44_640]
    assert [_usage_over_time_data(limit)["period_started_at"] for limit in limits] == [
        "2026-03-01T00:00:00Z",
        "2026-03-01T00:00:00Z",
    ]
    assert [_usage_over_time_data(limit)["period_ends_at"] for limit in limits] == [
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
    assert payload["usage_summary"] == "Burst 1%, Weekly 100%"
    assert payload["usage_refresh_cost_usd"] == 0.02309745
    assert payload["usage"]["refresh_model"] == "claude-haiku-4-5-20251001"
    assert payload["usage"]["refresh_session_id"] == "session-123"
    limits = payload["usage"]["limits"]
    assert [limit["limit_name"] for limit in limits] == ["burst", "weekly"]
    assert [limit["provider_limit"]["limit_type"] for limit in limits] == ["five_hour", "seven_day"]
    assert _usage_over_time_data(limits[0])["period_duration_mins"] == 300
    assert _usage_over_time_data(limits[0])["period_started_at"] == "2026-03-26T10:00:00Z"
    assert _usage_over_time_data(limits[0])["period_ends_at"] == "2026-03-26T15:00:00Z"
    assert _usage_over_time_data(limits[1])["period_duration_mins"] == 10_080
    assert _usage_over_time_data(limits[1])["period_started_at"] == "2026-03-20T10:00:00Z"
    assert _usage_over_time_data(limits[1])["period_ends_at"] == "2026-03-27T10:00:00Z"


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
            "usage_summary": "Weekly 42%",
        },
    )

    payload = chat_accounts._collect_claude_code_live_usage(instance)
    assert payload["usage_status"] == "ok"
    assert payload["usage_source"] == "live-refresh"
    assert payload["usage_summary"] == "Weekly 42%"


def test_terminate_pty_process_ignores_repeated_wait_timeouts(monkeypatch) -> None:
    class FakeProcess:
        def __init__(self) -> None:
            self.wait_calls = 0
            self.kill_calls = 0
            self.terminate_calls = 0

        def poll(self) -> None:
            return None

        def terminate(self) -> None:
            self.terminate_calls += 1

        def wait(self, timeout: float) -> int:
            del timeout
            self.wait_calls += 1
            raise subprocess.TimeoutExpired(["claude"], chat_accounts.CLAUDE_REFRESH_TERMINATE_WAIT_SEC)

        def kill(self) -> None:
            self.kill_calls += 1

    closed_fds: list[int] = []
    monkeypatch.setattr(chat_accounts, "_write_pty", lambda master_fd, payload: None)
    monkeypatch.setattr(chat_accounts.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(chat_accounts.os, "close", lambda master_fd: closed_fds.append(master_fd))

    process = FakeProcess()
    chat_accounts._terminate_pty_process(process, 123)

    assert process.terminate_calls == 1
    assert process.kill_calls == 1
    assert process.wait_calls == 2
    assert closed_fds == [123]


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
