from __future__ import annotations

import argparse
import io
import json
from pathlib import Path

import pytest

from agentos.agent.commands.accounts import _cmd_agent_accounts_usage_report
from agentos.testing import AgentosTestEnvironment

from _helpers import read_jsonl_file


def _env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    AgentosTestEnvironment.create(tmp_path).apply_environment(monkeypatch.setenv)
    from agentos._core.project import agentos_home_dir

    home_root = agentos_home_dir()
    prov = home_root / "accounts" / "claude-code"
    prov.mkdir(parents=True, exist_ok=True)
    (prov / "accounts.json").write_text(
        json.dumps(
            {
                "provider": "claude-code",
                "accounts": {
                    "br": {
                        "identity": {"account_uuid": "u-br"},
                        "auth_methods": {"browser": {"class": "oauth"}},
                    }
                },
            }
        )
    )
    return home_root


def _args(**overrides: object) -> argparse.Namespace:
    base = {
        "provider": "claude-code",
        "home": "/tmp/claude-home",
        "account": None,
        "source": None,
        "payload_stdin": True,
        "min_interval_sec": None,
        "sample_raw_context": True,
        "sample_max_records": 50,
        "json": False,
        "quiet": False,
        "_agentos_argv": [],
    }
    base.update(overrides)
    return argparse.Namespace(**base)


def test_usage_report_command_samples_stdin_context_as_json(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    home_root = _env(monkeypatch, tmp_path)
    provider_home = tmp_path / "claude-home"
    raw_context = {"hook_event_name": "Stop", "session_id": "s1"}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(raw_context)))

    rc = _cmd_agent_accounts_usage_report(
        _args(home=str(provider_home), account="br", json=True)
    )

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"] == "agent accounts usage-report"
    assert payload["status"] == "no_usage"
    assert payload["sample"]["status"] == "sampled"

    sample_path = Path(payload["sample"]["path"])
    records = read_jsonl_file(sample_path)
    assert sample_path.parent == home_root / "agent" / "usage-report-hook-samples"
    assert records[0]["provider"] == "claude-code"
    assert records[0]["account"] == "br"
    assert records[0]["raw_context"] == raw_context


def test_usage_report_command_quiet_samples_without_output(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _env(monkeypatch, tmp_path)
    monkeypatch.setattr("sys.stdin", io.StringIO('{"hook_event_name":"Stop"}'))

    rc = _cmd_agent_accounts_usage_report(_args(quiet=True))

    assert rc == 0
    assert capsys.readouterr().out == ""


def test_usage_report_command_rejects_invalid_stdin_json(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _env(monkeypatch, tmp_path)
    from agentos._core.errors import CliError

    monkeypatch.setattr("sys.stdin", io.StringIO("not-json"))

    with pytest.raises(CliError, match="usage-report stdin must be a JSON object"):
        _cmd_agent_accounts_usage_report(_args(json=True))


def test_usage_report_command_validates_supplied_account(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _env(monkeypatch, tmp_path)
    from agentos._core.errors import CliError

    monkeypatch.setattr("sys.stdin", io.StringIO('{"hook_event_name":"Stop"}'))

    with pytest.raises(
        CliError,
        match="agent accounts usage-report --account references unknown account",
    ):
        _cmd_agent_accounts_usage_report(_args(account="missing"))
