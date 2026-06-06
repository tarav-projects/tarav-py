from __future__ import annotations

from pathlib import Path

import pytest

from agentos.agent.account_status import AgentAccountContext
from agentos.codex.account_registry import (
    inspect_codex_account_home,
    read_codex_auth_info,
    register_codex_account_from_auth_file,
    link_codex_account_to_home,
)
from agentos.codex.account_reconcile import (
    discover_codex_reconcile_homes,
    reconcile_codex_accounts,
)
from agentos.codex.agent import CodexAgent
import agentos.codex.account_status as codex_account_status

from _helpers import (
    codex_auth_json,
    isolate_agentos,
    read_json_file,
    read_jsonl_file,
    write_global_config,
    write_text_file,
)


def test_codex_reconcile_registers_fresh_known_home_and_syncs_system_home(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _, agentos_home = isolate_agentos(monkeypatch, tmp_path)
    configured_home = tmp_path / "codex-br"
    system_home = agentos_home / "agent" / "homes" / "codex" / "br"
    old_auth = tmp_path / "old-auth.json"
    write_text_file(old_auth, codex_auth_json(account_id="acc_br", email="old@example.com"))
    write_text_file(
        configured_home / "auth.json",
        _newer_codex_auth_json(account_id="acc_br", email="fresh@example.com"),
    )
    write_global_config(
        agentos_home / "config.json",
        provider_profiles=[
            {"id": "codex-br", "provider": "codex", "home": str(configured_home)}
        ],
    )
    register_codex_account_from_auth_file(auth_file=old_auth, account="br")
    link_codex_account_to_home(home=system_home, account="br")
    fresh_info = read_codex_auth_info(configured_home / "auth.json")

    payload = reconcile_codex_accounts(start_path=tmp_path)

    actions = payload["actions"]
    assert isinstance(actions, list)
    assert {action["kind"] for action in actions if isinstance(action, dict)} == {
        "registered_artifact",
        "synced_home",
    }
    account_payload = read_json_file(agentos_home / "accounts" / "codex" / "accounts.json")
    assert account_payload["accounts"]["br"]["active_artifact_id"] == fresh_info.sha256
    artifacts = read_jsonl_file(agentos_home / "accounts" / "codex" / "artifacts.jsonl")
    assert {artifact["artifact_id"] for artifact in artifacts} >= {fresh_info.sha256}
    system_status = inspect_codex_account_home(home=system_home)
    assert system_status["classification"] == "matching-active"
    assert system_status["auth"]["artifact_id"] == fresh_info.sha256


def test_codex_reconcile_warns_and_skips_unknown_account_auth(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _, agentos_home = isolate_agentos(monkeypatch, tmp_path)
    configured_home = tmp_path / "codex-unknown"
    write_text_file(configured_home / "auth.json", codex_auth_json(account_id="acc_unknown"))
    write_global_config(
        agentos_home / "config.json",
        provider_profiles=[
            {"id": "codex-unknown", "provider": "codex", "home": str(configured_home)}
        ],
    )

    payload = reconcile_codex_accounts(start_path=tmp_path)

    assert payload["action_count"] == 0
    warnings = payload["warnings"]
    assert isinstance(warnings, list)
    assert [warning["kind"] for warning in warnings if isinstance(warning, dict)] == [
        "unknown_account_auth"
    ]
    assert not (agentos_home / "accounts" / "codex" / "artifacts.jsonl").exists()


def test_codex_reconcile_does_not_activate_older_stale_system_auth(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _, agentos_home = isolate_agentos(monkeypatch, tmp_path)
    system_home = agentos_home / "agent" / "homes" / "codex" / "br"
    active_auth = tmp_path / "active-auth.json"
    stale_auth = tmp_path / "stale-auth.json"
    write_text_file(
        active_auth,
        _newer_codex_auth_json(account_id="acc_br", email="active@example.com"),
    )
    write_text_file(stale_auth, codex_auth_json(account_id="acc_br", email="stale@example.com"))
    register_codex_account_from_auth_file(auth_file=active_auth, account="br")
    link_codex_account_to_home(home=system_home, account="br")
    write_text_file(system_home / "auth.json", stale_auth.read_text(encoding="utf-8"))
    active_info = read_codex_auth_info(active_auth)

    payload = reconcile_codex_accounts(start_path=tmp_path)

    account_payload = read_json_file(agentos_home / "accounts" / "codex" / "accounts.json")
    assert account_payload["accounts"]["br"]["active_artifact_id"] == active_info.sha256
    actions = payload["actions"]
    assert isinstance(actions, list)
    registered = [
        action
        for action in actions
        if isinstance(action, dict) and action["kind"] == "registered_artifact"
    ]
    assert registered[0]["detail"]["activated"] is False
    system_status = inspect_codex_account_home(home=system_home)
    assert system_status["auth"]["artifact_id"] == active_info.sha256


def test_codex_reconcile_check_does_not_mutate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _, agentos_home = isolate_agentos(monkeypatch, tmp_path)
    configured_home = tmp_path / "codex-br"
    old_auth = tmp_path / "old-auth.json"
    write_text_file(old_auth, codex_auth_json(account_id="acc_br", email="old@example.com"))
    write_text_file(
        configured_home / "auth.json",
        _newer_codex_auth_json(account_id="acc_br", email="fresh@example.com"),
    )
    write_global_config(
        agentos_home / "config.json",
        provider_profiles=[
            {"id": "codex-br", "provider": "codex", "home": str(configured_home)}
        ],
    )
    register_codex_account_from_auth_file(auth_file=old_auth, account="br")
    old_info = read_codex_auth_info(old_auth)

    payload = reconcile_codex_accounts(start_path=tmp_path, check=True)

    assert payload["check"] is True
    assert payload["action_count"] >= 2
    account_payload = read_json_file(agentos_home / "accounts" / "codex" / "accounts.json")
    assert account_payload["accounts"]["br"]["active_artifact_id"] == old_info.sha256


def test_codex_reconcile_discovers_only_known_homes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _, agentos_home = isolate_agentos(monkeypatch, tmp_path)
    configured_home = tmp_path / "configured-codex"
    old_auth = tmp_path / "auth.json"
    write_text_file(old_auth, codex_auth_json(account_id="acc_br"))
    write_global_config(
        agentos_home / "config.json",
        provider_profiles=[
            {"id": "codex-br", "provider": "codex", "home": str(configured_home)}
        ],
    )
    register_codex_account_from_auth_file(auth_file=old_auth, account="br")

    homes = discover_codex_reconcile_homes(start_path=tmp_path)

    discovered = {home["home"] for home in homes}
    assert discovered == {
        str(configured_home.resolve()),
        str((agentos_home / "agent" / "homes" / "codex" / "br").resolve()),
    }


def test_codex_account_status_runs_reconciliation_before_usage(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _, agentos_home = isolate_agentos(monkeypatch, tmp_path)
    configured_home = tmp_path / "codex-br"
    system_home = agentos_home / "agent" / "homes" / "codex" / "br"
    old_auth = tmp_path / "old-auth.json"
    write_text_file(old_auth, codex_auth_json(account_id="acc_br", email="old@example.com"))
    write_text_file(
        configured_home / "auth.json",
        _newer_codex_auth_json(account_id="acc_br", email="fresh@example.com"),
    )
    write_global_config(
        agentos_home / "config.json",
        provider_profiles=[
            {"id": "codex-br", "provider": "codex", "home": str(configured_home)}
        ],
    )
    register_codex_account_from_auth_file(auth_file=old_auth, account="br")
    link_codex_account_to_home(home=system_home, account="br")
    fresh_info = read_codex_auth_info(configured_home / "auth.json")

    monkeypatch.setattr(
        codex_account_status,
        "_account_usage_app_server",
        lambda agent: ((), (), {}, {}, {"status": "fresh", "source": "test"}),
    )

    status = CodexAgent(
        home=system_home,
        account=AgentAccountContext(provider="codex", account="br"),
    ).account_status(record_usage=False)

    assert status.check_status == "ok"
    assert status.raw["home_status"]["auth"]["artifact_id"] == fresh_info.sha256
    reconciliation = status.raw["reconciliation"]
    assert isinstance(reconciliation, dict)
    assert reconciliation["action_count"] >= 1


def _newer_codex_auth_json(*, account_id: str, email: str) -> str:
    return codex_auth_json(account_id=account_id, email=email).replace(
        "2026-05-12T17:00:07Z",
        "2026-05-23T17:00:07Z",
    )
