from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, Mapping

import pytest

from agentos._core.errors import CliError
from agentos.agent.account_status import (
    AccountLimit,
    AccountStatusError,
    AgentAccountContext,
    UsageOverTimeLimitData,
)
from agentos.agent.account_usage_fallback import account_usage_registry_fallback
from agentos.agent.usage_registry import append_usage_record
from agentos.cli import main
from agentos.codex.agent import CodexAgent

from _helpers import captured_json, read_jsonl_file, set_fake_agentos_home, write_text_file


def _limit(used_percent: int = 42) -> AccountLimit:
    return AccountLimit(
        limit_class="usage_over_time",
        limit_id="burst",
        limit_name="burst",
        limit_label="Burst",
        usage_over_time=UsageOverTimeLimitData(
            used_percent=used_percent,
            period_started_at=None,
            period_ends_at=None,
        ),
    )


def _live_error() -> AccountStatusError:
    return AccountStatusError(error_type="timeout", message="live read timed out")


def test_account_usage_registry_fallback_returns_cached_limits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_fake_agentos_home(monkeypatch, tmp_path / "agentos")
    home = tmp_path / "provider-home"
    home.mkdir()
    payload = {"used_percent": 17}
    append_usage_record(
        provider="provider",
        account="acct",
        home=home,
        source="test_source",
        payload=payload,
    )

    limits, errors, usage_payload, record_payload, metadata = account_usage_registry_fallback(
        provider="provider",
        account="acct",
        home=home,
        source="test_source",
        parser=lambda value: (_limit(int(value["used_percent"])),),
        live_error=_live_error(),
        fallback_to_usage_registry=True,
    )

    assert errors == ()
    assert [limit.summary() for limit in limits] == [_limit(17).summary()]
    assert usage_payload == payload
    assert record_payload is None
    assert metadata is not None
    assert metadata["status"] == "registry_fallback"
    assert metadata["source"] == "test_source"
    assert metadata["live_error"]["type"] == "timeout"


def test_account_usage_registry_fallback_reports_parser_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_fake_agentos_home(monkeypatch, tmp_path / "agentos")
    home = tmp_path / "provider-home"
    home.mkdir()
    append_usage_record(
        provider="provider",
        account="acct",
        home=home,
        source="test_source",
        payload={"bad": "payload"},
    )

    def fail_parser(payload: Mapping[str, Any]) -> tuple[AccountLimit, ...]:
        del payload
        raise CliError("bad registry payload")

    limits, errors, usage_payload, record_payload, metadata = account_usage_registry_fallback(
        provider="provider",
        account="acct",
        home=home,
        source="test_source",
        parser=fail_parser,
        live_error=_live_error(),
        fallback_to_usage_registry=True,
    )

    assert limits == ()
    assert [error.error_type for error in errors] == ["timeout", "invalid_registry_payload"]
    assert usage_payload is None
    assert record_payload is None
    assert metadata is None


def test_account_usage_registry_fallback_disabled_returns_live_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_fake_agentos_home(monkeypatch, tmp_path / "agentos")
    home = tmp_path / "provider-home"
    home.mkdir()
    append_usage_record(
        provider="provider",
        account="acct",
        home=home,
        source="test_source",
        payload={"used_percent": 17},
    )

    limits, errors, usage_payload, record_payload, metadata = account_usage_registry_fallback(
        provider="provider",
        account="acct",
        home=home,
        source="test_source",
        parser=lambda value: (_limit(int(value["used_percent"])),),
        live_error=_live_error(),
        fallback_to_usage_registry=False,
    )

    assert limits == ()
    assert [error.error_type for error in errors] == ["timeout"]
    assert usage_payload is None
    assert record_payload is None
    assert metadata is None


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


def _auth_json(*, account_id: str = "acc_123", email: str = "person@example.com") -> str:
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


def _codex_usage_payload(*, burst_percent: int = 20, weekly_percent: int = 54) -> dict[str, Any]:
    return {
        "rateLimits": {
            "limitId": "gpt-5",
            "primary": {
                "usedPercent": burst_percent,
                "windowDurationMins": 300,
                "resetsAt": 1_776_010_000,
            },
            "secondary": {
                "usedPercent": weekly_percent,
                "windowDurationMins": 10080,
                "resetsAt": 1_776_600_000,
            },
        }
    }


def _register_linked_codex_agent(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> tuple[Path, Path, CodexAgent]:
    auth_file = tmp_path / "auth.json"
    codex_home = tmp_path / "codex-home"
    write_text_file(auth_file, _auth_json())

    assert main(
        [
            "agent",
            "accounts",
            "register",
            "--provider",
            "codex",
            "--account",
            "br",
            "--auth-file",
            str(auth_file),
        ]
    ) == 0
    captured_json(capsys)
    assert main(
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
    ) == 0
    captured_json(capsys)
    agent = CodexAgent(
        home=codex_home,
        account=AgentAccountContext(provider="codex", account="br"),
    )
    return codex_home, auth_file, agent


def test_codex_account_status_records_fresh_app_server_usage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    agentos_home = set_fake_agentos_home(monkeypatch, tmp_path / "agentos")
    codex_home, _auth_file, agent = _register_linked_codex_agent(tmp_path, capsys)

    monkeypatch.setattr(
        "agentos.codex.account_status._fetch_account_usage_app_server_payload",
        lambda agent: _codex_usage_payload(burst_percent=11, weekly_percent=22),
    )

    status = agent.account_status()

    assert status.usage_status == "ok"
    assert status.auth_summary == "Codex rate limits read"
    assert status.usage_summary == "Burst 11%, Weekly 22%"
    usage_record = status.raw["usage_record"]
    assert isinstance(usage_record, dict)
    assert usage_record["status"] == "fresh"
    records = read_jsonl_file(
        next((agentos_home / "agent" / "usage-registry").glob("*-usage.jsonl"))
    )
    assert len(records) == 1
    assert records[0]["provider"] == "codex"
    assert records[0]["account"] == "br"
    assert records[0]["home"] == str(codex_home.resolve())
    assert records[0]["source"] == "app_server"
    assert records[0]["payload"]["rateLimits"]["primary"]["usedPercent"] == 11


def test_codex_account_status_falls_back_to_usage_registry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    agentos_home = set_fake_agentos_home(monkeypatch, tmp_path / "agentos")
    codex_home, _auth_file, agent = _register_linked_codex_agent(tmp_path, capsys)

    append_usage_record(
        provider="codex",
        account="br",
        home=codex_home,
        source="app_server",
        payload=_codex_usage_payload(burst_percent=12, weekly_percent=34),
    )
    usage_record_path = agentos_home / "agent" / "usage-registry" / "202605-usage.jsonl"
    assert len(read_jsonl_file(usage_record_path)) == 1

    def fail_app_server(agent: object):
        del agent
        return (
            (),
            (AccountStatusError(error_type="command_failed", message="forced app-server failure"),),
            None,
            None,
            None,
        )

    monkeypatch.setattr("agentos.codex.account_status._account_usage_app_server", fail_app_server)

    status = agent.account_status()

    assert status.usage_status == "ok"
    assert status.usage_errors == ()
    assert status.auth_summary == "Codex usage registry fallback"
    assert status.usage_summary == "Burst 12%, Weekly 34%"
    assert [limit.usage_over_time.used_percent for limit in status.limits if limit.usage_over_time] == [12, 34]
    usage_record = status.raw["usage_record"]
    assert isinstance(usage_record, dict)
    assert usage_record["status"] == "registry_fallback"
    assert usage_record["source"] == "app_server"
    assert usage_record["live_error"]["type"] == "command_failed"
    assert usage_record["live_error"]["message"] == "forced app-server failure"
    assert len(read_jsonl_file(usage_record_path)) == 1


def test_codex_account_status_without_cached_usage_stays_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    set_fake_agentos_home(monkeypatch, tmp_path / "agentos")
    _codex_home, _auth_file, agent = _register_linked_codex_agent(tmp_path, capsys)

    def fail_app_server(agent: object):
        del agent
        return (
            (),
            (AccountStatusError(error_type="command_failed", message="forced app-server failure"),),
            None,
            None,
            None,
        )

    monkeypatch.setattr("agentos.codex.account_status._account_usage_app_server", fail_app_server)

    status = agent.account_status()

    assert status.usage_status == "error"
    assert [error.error_type for error in status.usage_errors] == ["command_failed"]
    assert status.auth_summary is None
    assert status.raw["usage"] is None
    assert status.raw["usage_record"] is None
