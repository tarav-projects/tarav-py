from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from agentos.chat import accounts as chat_accounts
from agentos.cli import main
from agentos.tara_tapes.core import load_tara_tape_manifest, read_tara_tape_segment_records


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


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

    assert observed_calls == [
        (["/opt/homebrew/bin/codex", "login", "status"], 9),
        (["claude", "auth", "status", "--json"], chat_accounts.DEFAULT_ACCOUNT_TIMEOUT_SEC),
    ]
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

    def fake_collect_live_usage(instance: chat_accounts.AccountProviderInstance) -> dict[str, object]:
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

    assert main(["chat", "accounts", "stats"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["provider_count"] == 0
    assert payload["account_count"] == 0
    assert payload["providers"] == []

    assert main(["chat", "accounts", "stats", "--full-output"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["provider_count"] == 2
    assert [provider["provider"] for provider in payload["providers"]] == ["codex", "claude-code"]
    assert all(provider["account_count"] == 0 for provider in payload["providers"])

    assert main(["chat", "accounts", "stats", "--full-output", "--output", "markdown"]) == 0
    output = capsys.readouterr().out
    assert "# Chat Accounts Stats" in output
    assert "- Recorded at: " in output
    assert "- History: ok" in output
    assert "- History segment: " in output
    assert "## codex" in output
    assert "## claude-code" in output


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
    assert "codex-tk (Codex tk):" in output
    assert "  5h [######----] 64% | resets 2026-03-26 05:40:41Z | in 17h 40m" in output
    assert "  7d [##--------] 20% | resets 2026-03-26 21:10:27Z | in 1d 9h 10m" in output
    assert "claude-main (Claude main):" in output
    assert "  Usage unavailable: " in output


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


def test_collect_claude_code_live_usage_falls_back_to_stream_json(monkeypatch) -> None:
    instance = chat_accounts.AccountProviderInstance(
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
