from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agentos.agent.account_status import AccountStatusError, AgentAccountContext
from agentos.agent.usage_registry import append_usage_record
from agentos.codex.agent import CodexAgent
from agentos.testing import AgentosTestEnvironment
from agentos.testing import codex_auth_json, seed_codex_account
from _helpers import (
    read_jsonl_file,
    write_text_file,
)


def _codex_usage_payload(
    *, burst_percent: int = 20, weekly_percent: int = 54
) -> dict[str, Any]:
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
        },
    }


def _codex_weekly_primary_usage_payload(*, weekly_percent: int = 5) -> dict[str, Any]:
    return {
        "rateLimits": {
            "limitId": "codex",
            "primary": {
                "usedPercent": weekly_percent,
                "windowDurationMins": 10080,
                "resetsAt": 1_784_491_342,
            },
            "secondary": None,
        },
    }


def _failed_app_server_result(agent: object):
    del agent
    return (
        (),
        (
            AccountStatusError(
                error_type="command_failed", message="forced app-server failure"
            ),
        ),
        None,
        None,
        None,
    )


def _seeded_codex_agent(tmp_path: Path) -> tuple[Path, CodexAgent]:
    codex_home = tmp_path / "codex-home"
    seed_codex_account("br")
    write_text_file(codex_home / "auth.json", codex_auth_json())
    return codex_home, CodexAgent(
        home=codex_home,
        account=AgentAccountContext(provider="codex", account="br"),
    )


def test_agent_usage_records_fresh_codex_app_server_limits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path / "agentos")
    environment.apply_environment(monkeypatch.setenv)
    agentos_home = environment.agentos_home
    codex_home, agent = _seeded_codex_agent(tmp_path)

    monkeypatch.setattr(
        "agentos.codex.account_status._fetch_account_usage_app_server_payload",
        lambda agent: _codex_usage_payload(burst_percent=11, weekly_percent=22),
    )

    status = agent.account_status()

    assert status.usage_status == "ok"
    assert status.auth_summary == "Codex app-server usage read"
    assert status.usage_summary == "Burst 11%, Weekly 22%"
    assert status.raw["usage_record"]["status"] == "fresh"
    records = read_jsonl_file(
        next((agentos_home / "agent" / "usage-registry").glob("*-usage.jsonl"))
    )
    assert len(records) == 1
    assert records[0]["provider"] == "codex"
    assert records[0]["account"] == "br"
    assert records[0]["home"] == str(codex_home.resolve())
    assert records[0]["source"] == "app_server"
    assert records[0]["payload"]["rateLimits"]["primary"]["usedPercent"] == 11
    assert "tokenUsage" not in records[0]["payload"]


def test_agent_usage_falls_back_to_cached_codex_limits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path / "agentos")
    environment.apply_environment(monkeypatch.setenv)
    agentos_home = environment.agentos_home
    codex_home, agent = _seeded_codex_agent(tmp_path)
    append_usage_record(
        provider="codex",
        account="br",
        home=codex_home,
        source="app_server",
        payload=_codex_usage_payload(burst_percent=12, weekly_percent=34),
    )
    monkeypatch.setattr(
        "agentos.codex.account_status._account_usage_app_server",
        _failed_app_server_result,
    )

    status = agent.account_status()

    assert status.usage_status == "ok"
    assert status.usage_errors == ()
    assert status.auth_summary == "Codex usage registry fallback"
    assert status.usage_summary == "Burst 12%, Weekly 34%"
    assert [
        limit.usage_over_time.used_percent
        for limit in status.limits
        if limit.usage_over_time
    ] == [12, 34]
    usage_record = status.raw["usage_record"]
    assert usage_record["status"] == "registry_fallback"
    assert usage_record["source"] == "app_server"
    assert usage_record["live_error"]["type"] == "command_failed"
    assert usage_record["live_error"]["message"] == "forced app-server failure"
    usage_record_paths = list(
        (agentos_home / "agent" / "usage-registry").glob("*-usage.jsonl")
    )
    assert len(usage_record_paths) == 1
    assert len(read_jsonl_file(usage_record_paths[0])) == 1


def test_agent_usage_classifies_codex_primary_weekly_by_duration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path / "agentos")
    environment.apply_environment(monkeypatch.setenv)
    codex_home, agent = _seeded_codex_agent(tmp_path)

    monkeypatch.setattr(
        "agentos.codex.account_status._fetch_account_usage_app_server_payload",
        lambda agent: _codex_weekly_primary_usage_payload(weekly_percent=5),
    )

    status = agent.account_status()

    assert status.usage_status == "ok"
    assert status.usage_summary == "Weekly 5%"
    assert [(limit.limit_id, limit.limit_label) for limit in status.limits] == [
        ("weekly", "Weekly")
    ]
    assert status.limits[0].provider_limit == {
        "limit_id": "codex",
        "window_key": "primary",
        "window_duration_mins": 10080,
    }
    records = read_jsonl_file(
        next(
            (environment.agentos_home / "agent" / "usage-registry").glob(
                "*-usage.jsonl"
            )
        )
    )
    assert records[0]["home"] == str(codex_home.resolve())


def test_agent_usage_without_cached_codex_limits_stays_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path / "agentos")
    environment.apply_environment(monkeypatch.setenv)
    _codex_home, agent = _seeded_codex_agent(tmp_path)
    monkeypatch.setattr(
        "agentos.codex.account_status._account_usage_app_server",
        _failed_app_server_result,
    )

    status = agent.account_status()

    assert status.usage_status == "error"
    assert [error.error_type for error in status.usage_errors] == ["command_failed"]
    assert status.auth_summary is None
    assert status.raw["usage"] is None
    assert status.raw["usage_record"] is None
