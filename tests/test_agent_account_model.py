from __future__ import annotations

from pathlib import Path

import pytest

from agentos.agent.account_model import (
    active_artifact_id,
    method_artifact_ids,
    read_artifact,
    set_active_artifact,
    store_artifact,
    upsert_account_identity,
)
from agentos.agent.auth_method import AuthData
from agentos.testing import AgentosTestEnvironment


def _env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)


def test_account_model_round_trips_nested_shape(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)

    upsert_account_identity("codex", "tk", provider_account_id="uuid-tk", metadata={"email": "tk@example.com"})
    artifact_id = store_artifact("codex", "tk", "auth-json", AuthData(payload={"token": "secret-xyz"}))
    set_active_artifact("codex", "tk", "auth-json", artifact_id)

    assert active_artifact_id("codex", "tk", "auth-json") == artifact_id
    assert method_artifact_ids("codex", "tk", "auth-json") == [artifact_id]

    from agentos.agent.account_registry import load_account

    record = load_account("codex", "tk")
    assert record["provider_account_id"] == "uuid-tk"
    assert "auth-json" in record["auth_methods"]


def test_store_artifact_dedups_by_content(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    upsert_account_identity("codex", "tk", provider_account_id="uuid-tk")

    first = store_artifact("codex", "tk", "auth-json", AuthData(payload={"a": 1, "b": 2}))
    same = store_artifact("codex", "tk", "auth-json", AuthData(payload={"b": 2, "a": 1}))
    other = store_artifact("codex", "tk", "auth-json", AuthData(payload={"a": 9}))

    assert first == same
    assert other != first
    assert method_artifact_ids("codex", "tk", "auth-json") == [first, other]
    # payload recoverable
    assert read_artifact("codex", first).payload == {"a": 1, "b": 2}


def test_activation_sets_and_rotates_pointer_without_touching_a_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    upsert_account_identity("codex", "tk", provider_account_id="uuid-tk")
    first = store_artifact("codex", "tk", "auth-json", AuthData(payload={"v": 1}))
    second = store_artifact("codex", "tk", "auth-json", AuthData(payload={"v": 2}))

    sentinel_home = tmp_path / "managed-home"
    sentinel_home.mkdir()
    (sentinel_home / "auth").write_text("untouched", encoding="utf-8")

    set_active_artifact("codex", "tk", "auth-json", first)
    assert active_artifact_id("codex", "tk", "auth-json") == first
    # rotate
    set_active_artifact("codex", "tk", "auth-json", second)
    assert active_artifact_id("codex", "tk", "auth-json") == second

    # activation is registry-only — the home is never touched
    assert (sentinel_home / "auth").read_text(encoding="utf-8") == "untouched"


def test_activation_rejects_unknown_artifact(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    upsert_account_identity("codex", "tk", provider_account_id="uuid-tk")
    from agentos._core.errors import CliError

    with pytest.raises(CliError, match="unknown artifact"):
        set_active_artifact("codex", "tk", "auth-json", "deadbeef")


def test_secrets_live_only_in_payload_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    from agentos._core.project import agentos_home_dir

    upsert_account_identity("codex", "tk", provider_account_id="uuid-tk")
    store_artifact("codex", "tk", "auth-json", AuthData(payload={"token": "TOPSECRET"}))

    provider_root = agentos_home_dir() / "accounts" / "codex"
    assert "TOPSECRET" not in (provider_root / "accounts.json").read_text(encoding="utf-8")
    assert "TOPSECRET" not in (provider_root / "artifacts.jsonl").read_text(encoding="utf-8")
    # but it IS in a payload file
    payloads = list((provider_root / "artifacts").glob("*.json"))
    assert any("TOPSECRET" in p.read_text(encoding="utf-8") for p in payloads)
