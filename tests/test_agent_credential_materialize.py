from __future__ import annotations

from pathlib import Path

import pytest

from agentos.agent.account_model import (
    active_artifact_id,
    set_active_artifact,
    store_artifact,
    upsert_account_identity,
)
from agentos.agent.account_status import AccountIdentity
from agentos.agent.auth_method import AuthData, AuthMethod
from agentos.agent.credential_materialize import materialize_active
from agentos.testing import AgentosTestEnvironment


class _FakeMethod(AuthMethod):
    name = "auth-json"
    provider = "codex"
    materializable = True

    def read_auth_data(self, home: Path) -> AuthData | None:  # pragma: no cover - unused
        return None

    def extract_identity(self, auth_data: AuthData) -> AccountIdentity | None:  # pragma: no cover
        return None

    def materialize(self, auth_data: AuthData, home: Path) -> None:
        home.mkdir(parents=True, exist_ok=True)
        (home / "auth").write_text(str(auth_data.payload.get("token", "")), encoding="utf-8")


def test_materialize_active_writes_payload_and_nothing_else(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)

    upsert_account_identity("codex", "tk", provider_account_id="uuid-tk")
    artifact_id = store_artifact("codex", "tk", "auth-json", AuthData(payload={"token": "live-token"}))
    set_active_artifact("codex", "tk", "auth-json", artifact_id)

    target = tmp_path / "managed-home"
    written = materialize_active(_FakeMethod(), "tk", target)

    assert written == artifact_id
    assert (target / "auth").read_text(encoding="utf-8") == "live-token"
    # registry + active pointer unchanged by materialization
    assert active_artifact_id("codex", "tk", "auth-json") == artifact_id


def test_materialize_active_requires_an_active_artifact(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    environment = AgentosTestEnvironment.create(tmp_path)
    environment.apply_environment(monkeypatch.setenv)
    upsert_account_identity("codex", "tk", provider_account_id="uuid-tk")
    from agentos._core.errors import CliError

    with pytest.raises(CliError, match="no active artifact"):
        materialize_active(_FakeMethod(), "tk", tmp_path / "home")
