from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from agentos.cli import main
from agentos.agent.monitor.config import load_monitor_workflow_configs
from _helpers import (
    captured_json,
    read_json_file,
    read_jsonl_file,
    set_fake_agentos_home,
    write_text_file,
)


def _jwt(payload: dict[str, object]) -> str:
    raw_header = json.dumps({"alg": "none"}, separators=(",", ":")).encode("utf-8")
    raw_payload = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return ".".join(
        [
            base64.urlsafe_b64encode(raw_header).decode("ascii").rstrip("="),
            base64.urlsafe_b64encode(raw_payload).decode("ascii").rstrip("="),
            "signature",
        ]
    )


def _auth_json(
    *, account_id: str = "acc_123", email: str = "person@example.com"
) -> str:
    return (
        json.dumps(
            {
                "auth_mode": "chatgpt",
                "OPENAI_API_KEY": None,
                "tokens": {
                    "id_token": _jwt({"email": email, "iat": 1_776_000_000}),
                    "access_token": _jwt({"iat": 1_776_000_000}),
                    "refresh_token": "secret-refresh-token",
                    "account_id": account_id,
                },
                "last_refresh": "2026-05-12T17:00:07Z",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def _register_codex(auth_file: Path, *, account: str = "br") -> list[str]:
    return [
        "agent",
        "accounts",
        "register",
        "--provider",
        "codex",
        "--account",
        account,
        "--auth-file",
        str(auth_file),
    ]


def _write_monitor_config(agentos_home: Path, monitor: list[dict[str, object]]) -> None:
    write_text_file(
        agentos_home / "config.json",
        json.dumps(
            {
                "class": "agentos.global.config",
                "schema_version": 1,
                "agent": {"accounts": {"monitor": monitor}},
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )


def test_agent_accounts_register_link_and_status_codex(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    agentos_home = set_fake_agentos_home(monkeypatch, tmp_path / "home")
    auth_file = tmp_path / "auth.json"
    codex_home = tmp_path / "codex-home"
    auth_text = _auth_json()
    write_text_file(auth_file, auth_text)

    assert main(_register_codex(auth_file)) == 0
    register_payload = captured_json(capsys)
    assert register_payload["artifact_appended"] is True
    assert register_payload["account_record"]["account_id"] == "acc_123"
    assert "secret-refresh-token" not in json.dumps(register_payload)

    provider_root = agentos_home / "accounts" / "codex"
    accounts = read_json_file(provider_root / "accounts.json")
    artifact_id = accounts["accounts"]["br"]["active_artifact_id"]
    assert (provider_root / "artifacts" / f"{artifact_id}.auth.json").read_text(
        encoding="utf-8"
    ) == auth_text

    assert (
        main(
            [
                "agent",
                "accounts",
                "link",
                "--provider",
                "codex",
                "--account",
                "br",
                "--home",
                str(codex_home),
                "--json",
            ]
        )
        == 0
    )
    link_payload = captured_json(capsys)
    assert link_payload["kind"] == "artifact"
    assert link_payload["copied_auth"]["artifact_id"] == artifact_id
    assert (codex_home / "auth.json").read_text(encoding="utf-8") == auth_text

    links = read_json_file(provider_root / "links.json")
    assert links["links"][str(codex_home.resolve())]["account"] == "br"

    assert (
        main(
            [
                "agent",
                "accounts",
                "status",
                "--provider",
                "codex",
                "--home",
                str(codex_home),
                "--json",
            ]
        )
        == 0
    )
    status_payload = captured_json(capsys)
    assert status_payload["classification"] == "matching-active"
    assert status_payload["link_consistency"] == "verified"
    assert status_payload["auth"]["email"] == "person@example.com"


def test_agent_accounts_register_is_idempotent_and_rejects_identity_mismatch(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    agentos_home = set_fake_agentos_home(monkeypatch, tmp_path / "home")
    first = tmp_path / "first.json"
    mismatch = tmp_path / "mismatch.json"
    write_text_file(first, _auth_json(account_id="acc_123"))
    write_text_file(mismatch, _auth_json(account_id="acc_999"))

    assert main(_register_codex(first)) == 0
    assert captured_json(capsys)["artifact_appended"] is True
    assert main(_register_codex(first)) == 0
    assert captured_json(capsys)["artifact_appended"] is False

    assert main(_register_codex(mismatch)) == 1
    assert "is already registered for account_id acc_123" in capsys.readouterr().err
    artifacts = read_jsonl_file(agentos_home / "accounts" / "codex" / "artifacts.jsonl")
    assert len(artifacts) == 1


def test_agent_accounts_link_protects_existing_unknown_auth(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    set_fake_agentos_home(monkeypatch, tmp_path / "home")
    source = tmp_path / "source.json"
    target_home = tmp_path / "codex"
    unknown_auth = _auth_json(account_id="acc_unknown")
    write_text_file(source, _auth_json(account_id="acc_123"))
    write_text_file(target_home / "auth.json", unknown_auth)

    assert main(_register_codex(source)) == 0
    capsys.readouterr()
    assert (
        main(
            [
                "agent",
                "accounts",
                "link",
                "--provider",
                "codex",
                "--account",
                "br",
                "--home",
                str(target_home),
            ]
        )
        == 1
    )
    assert "refusing to replace unregistered codex auth" in capsys.readouterr().err
    assert (target_home / "auth.json").read_text(encoding="utf-8") == unknown_auth

    assert (
        main(
            [
                "agent",
                "accounts",
                "link",
                "--provider",
                "codex",
                "--account",
                "br",
                "--home",
                str(target_home),
                "--force",
                "--json",
            ]
        )
        == 0
    )
    assert captured_json(capsys)["target_before_link"]["classification"] == "unknown"


def test_agent_accounts_register_provider_specific_claims(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    agentos_home = set_fake_agentos_home(monkeypatch, tmp_path / "home")

    assert (
        main(
            [
                "agent",
                "accounts",
                "register",
                "--provider",
                "claude-code",
                "--account",
                "main",
                "--email",
                "person@example.com",
                "--label",
                "Claude",
            ]
        )
        == 0
    )
    claude_payload = captured_json(capsys)
    assert claude_payload["account_record"]["email"] == "person@example.com"
    assert claude_payload["account_record"]["label"] == "Claude"

    assert (
        main(
            [
                "agent",
                "accounts",
                "register",
                "--provider",
                "copilot-cli",
                "--account",
                "jp",
                "--account-id",
                "josePereiro",
            ]
        )
        == 0
    )
    copilot_payload = captured_json(capsys)
    assert copilot_payload["account_record"]["account_id"] == "josePereiro"

    registry = read_json_file(
        agentos_home / "accounts" / "copilot-cli" / "accounts.json"
    )
    assert registry["accounts"]["jp"]["provider"] == "copilot-cli"
    assert registry["accounts"]["jp"]["account_id"] == "josePereiro"

    assert (
        main(
            [
                "agent",
                "accounts",
                "register",
                "--provider",
                "claude-code",
                "--account",
                "bad",
            ]
        )
        == 1
    )
    assert "requires --email" in capsys.readouterr().err


def test_agent_accounts_monitor_reports_configuration_errors(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    agentos_home = set_fake_agentos_home(monkeypatch, tmp_path / "home")

    _write_monitor_config(
        agentos_home, [{"workflow": "limits-tracking", "targets": []}]
    )
    assert main(["agent", "accounts", "monitor", "--once"]) == 1
    assert (
        "agent.accounts.monitor[0].targets must not be empty" in capsys.readouterr().err
    )

    _write_monitor_config(
        agentos_home,
        [
            {
                "workflow": "limits-tracking",
                "targets": [{"provider": "codex", "account": "missing"}],
            }
        ],
    )
    assert main(["agent", "accounts", "monitor", "--once"]) == 1
    assert "agent account is not registered: codex.missing" in capsys.readouterr().err

    _write_monitor_config(
        agentos_home,
        [
            {
                "workflow": "future-workflow",
                "targets": [{"provider": "codex", "account": "missing"}],
            }
        ],
    )
    assert main(["agent", "accounts", "monitor", "--once"]) == 1
    assert "unknown monitor workflow 'future-workflow'" in capsys.readouterr().err


def test_agent_accounts_monitor_auto_prime_trigger_config(
    tmp_path: Path,
    monkeypatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    agentos_home = set_fake_agentos_home(monkeypatch, tmp_path / "home")
    auth_file = tmp_path / "auth.json"
    write_text_file(auth_file, _auth_json())
    assert main(_register_codex(auth_file)) == 0
    capsys.readouterr()

    _write_monitor_config(
        agentos_home,
        [
            {
                "workflow": "auto-prime-zero-limits",
                "targets": [{"provider": "codex", "account": "br"}],
            }
        ],
    )
    config = load_monitor_workflow_configs(start_path=tmp_path)[0]
    assert config.triggers["codex"] == (
        "zero_usage",
        "near_zero_full_window",
        "sliding_reset",
        "period_key_churn",
    )

    _write_monitor_config(
        agentos_home,
        [
            {
                "workflow": "auto-prime-zero-limits",
                "triggers": {"codex": ["zero_usage", "sliding_reset"]},
                "targets": [{"provider": "codex", "account": "br"}],
            }
        ],
    )
    config = load_monitor_workflow_configs(start_path=tmp_path)[0]
    assert config.triggers["codex"] == ("zero_usage", "sliding_reset")

    _write_monitor_config(
        agentos_home,
        [
            {
                "workflow": "auto-prime-zero-limits",
                "triggers": {"codex": ["made_up"]},
                "targets": [{"provider": "codex", "account": "br"}],
            }
        ],
    )
    assert main(["agent", "accounts", "monitor", "--once"]) == 1
    assert (
        "agent.accounts.monitor[0].triggers.codex[0] is not supported"
        in capsys.readouterr().err
    )

    _write_monitor_config(
        agentos_home,
        [
            {
                "workflow": "auto-prime-zero-limits",
                "triggers": {"copilot-cli": ["zero_usage"]},
                "targets": [{"provider": "codex", "account": "br"}],
            }
        ],
    )
    assert main(["agent", "accounts", "monitor", "--once"]) == 1
    assert (
        "agent.accounts.monitor[0].triggers.copilot-cli is not supported"
        in capsys.readouterr().err
    )
