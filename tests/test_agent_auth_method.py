from __future__ import annotations

from pathlib import Path

from tarav.l1.agent.account_status import AccountIdentity
from tarav.l1.agent.auth_method import AuthData, AuthMethod


class _FakeAuthMethod(AuthMethod):
    name = "fake-auth"
    provider = "fake"
    materializable = True

    def read_auth_data(self, home: Path) -> AuthData | None:
        source = home / "auth"
        if not source.exists():
            return None
        return AuthData(payload={"id": source.read_text(encoding="utf-8")})

    def extract_identity(self, auth_data: AuthData) -> AccountIdentity | None:
        account_id = auth_data.payload.get("id")
        if not isinstance(account_id, str):
            return None
        return AccountIdentity(provider_account_id=account_id)

    def materialize(self, auth_data: AuthData, home: Path) -> None:
        home.mkdir(parents=True, exist_ok=True)
        (home / "auth").write_text(str(auth_data.payload.get("id", "")), encoding="utf-8")

    def ref_id(self, auth_data: AuthData) -> str:
        return auth_data.content_id()


def test_auth_data_content_id_is_deterministic_and_dedups() -> None:
    a = AuthData(payload={"b": 1, "a": 2})
    b = AuthData(payload={"a": 2, "b": 1})
    assert a.content_id() == b.content_id()
    assert AuthData(payload={"a": 3}).content_id() != a.content_id()


def test_fake_method_capability_surface(tmp_path: Path) -> None:
    method = _FakeAuthMethod()
    assert method.name == "fake-auth"
    assert method.materializable is True

    # extract identity
    identity = method.extract_identity(AuthData(payload={"id": "acct-1"}))
    assert identity is not None
    assert identity.provider_account_id == "acct-1"

    # read from a home, then materialize into another home — round-trip
    source_home = tmp_path / "src"
    source_home.mkdir()
    (source_home / "auth").write_text("acct-1", encoding="utf-8")
    auth_data = method.read_auth_data(source_home)
    assert auth_data is not None

    target_home = tmp_path / "dst"
    method.materialize(auth_data, target_home)
    assert (target_home / "auth").read_text(encoding="utf-8") == "acct-1"


def test_read_auth_data_returns_none_when_absent(tmp_path: Path) -> None:
    assert _FakeAuthMethod().read_auth_data(tmp_path) is None
