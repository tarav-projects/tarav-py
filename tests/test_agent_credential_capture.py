from __future__ import annotations

from pathlib import Path

import pytest

from agentos.agent.account_model import (
    method_artifact_ids,
    upsert_account_identity,
)
from agentos.agent.account_status import AccountIdentity
from agentos.agent.auth_method import AuthData, AuthMethod
from agentos.agent.credential_capture import (
    UNKNOWN_ACCOUNT,
    capture_from_home,
    capture_from_home_safe,
)
from agentos.testing import AgentosTestEnvironment


class _FakeMethod(AuthMethod):
    name = "auth-json"
    provider = "codex"
    materializable = True

    def read_auth_data(self, home: Path) -> AuthData | None:
        source = home / "auth"
        return AuthData(payload={"id": source.read_text(encoding="utf-8")}) if source.exists() else None

    def extract_identity(self, auth_data: AuthData) -> AccountIdentity | None:
        account_id = auth_data.payload.get("id")
        if not isinstance(account_id, str) or not account_id:
            return None
        return AccountIdentity(provider_account_id=account_id)

    def materialize(self, auth_data: AuthData, home: Path) -> None:  # pragma: no cover - unused here
        raise NotImplementedError


class _RaisingMethod(_FakeMethod):
    def read_auth_data(self, home: Path) -> AuthData | None:
        raise RuntimeError("boom")


def _home(tmp_path: Path, name: str, identity: str) -> Path:
    home = tmp_path / name
    home.mkdir()
    (home / "auth").write_text(identity, encoding="utf-8")
    return home


def _env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)


def test_capture_known_account_appends_then_dedups(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    upsert_account_identity("codex", "tk", provider_account_id="uuid-tk")

    home = _home(tmp_path, "h", "uuid-tk")
    first = capture_from_home(_FakeMethod(), home)
    second = capture_from_home(_FakeMethod(), home)

    assert first.status == "known"
    assert first.account == "tk"
    assert second.status == "known"
    assert method_artifact_ids("codex", "tk", "auth-json") == [first.artifact_id]


def test_capture_unknown_account_lands_in_bucket_with_identity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)

    home = _home(tmp_path, "h", "uuid-orphan")
    result = capture_from_home(_FakeMethod(), home)

    assert result.status == "unknown"
    assert result.account == UNKNOWN_ACCOUNT
    assert result.provider_account_id == "uuid-orphan"
    assert result.artifact_id in method_artifact_ids("codex", UNKNOWN_ACCOUNT, "auth-json")


def test_capture_unrecognized_credential_is_parked_not_stored(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    home = _home(tmp_path, "h", "")  # empty id -> extract_identity returns None

    result = capture_from_home(_FakeMethod(), home)
    assert result.status == "unrecognized"
    assert result.artifact_id is None


def test_capture_error_is_swallowed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    home = _home(tmp_path, "h", "uuid-tk")

    result = capture_from_home_safe(_RaisingMethod(), home)
    assert result.status == "error"  # never raises into the host command
