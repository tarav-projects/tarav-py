from __future__ import annotations

import base64
import json
from pathlib import Path

from tarav.agent.auth_method import AuthData
from tarav.agent.providers.codex.auth_method import CodexAuthMethod


def _jwt(payload: dict[str, object]) -> str:
    def seg(obj: dict[str, object]) -> str:
        raw = json.dumps(obj).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    return f"{seg({'alg': 'none'})}.{seg(payload)}.sig"


def _auth_json(*, account_id_claim: str, tokens_account_id: str, email: str) -> dict[str, object]:
    access_token = _jwt(
        {
            "https://api.openai.com/auth": {"chatgpt_account_id": account_id_claim},
            "email": email,
        }
    )
    # id_token carries a DIFFERENT, stale id — extraction must ignore it.
    id_token = _jwt({"https://api.openai.com/auth": {"chatgpt_account_id": "STALE-FROM-ID-TOKEN"}})
    return {
        "tokens": {"access_token": access_token, "id_token": id_token, "account_id": tokens_account_id},
        "last_refresh": "2026-06-20T02:00:38Z",
    }


def test_codex_method_extracts_identity_from_access_token_claim() -> None:
    method = CodexAuthMethod()
    assert method.name == "auth-json"
    assert method.provider == "codex"
    assert method.materializable is True

    payload = _auth_json(account_id_claim="uuid-tk", tokens_account_id="uuid-tk", email="tk@example.com")
    identity = method.extract_identity(AuthData(payload=payload))
    assert identity is not None
    assert identity.provider_account_id == "uuid-tk"  # from access_token, not "STALE-FROM-ID-TOKEN"
    assert identity.email == "tk@example.com"


def test_codex_method_reads_and_materializes_auth_json(tmp_path: Path) -> None:
    method = CodexAuthMethod()
    payload = _auth_json(account_id_claim="uuid-tk", tokens_account_id="uuid-tk", email="tk@example.com")

    source = tmp_path / "src"
    source.mkdir()
    (source / "auth.json").write_text(json.dumps(payload), encoding="utf-8")

    auth_data = method.read_auth_data(source)
    assert auth_data is not None
    assert auth_data.payload == payload

    target = tmp_path / "managed"
    method.materialize(auth_data, target)
    assert json.loads((target / "auth.json").read_text(encoding="utf-8")) == payload


def test_codex_method_returns_none_when_no_auth(tmp_path: Path) -> None:
    assert CodexAuthMethod().read_auth_data(tmp_path) is None


def test_codex_method_unrecognized_without_account_id() -> None:
    method = CodexAuthMethod()
    # tokens present but no chatgpt_account_id claim and no tokens.account_id
    payload = {"tokens": {"access_token": _jwt({"email": "x@y.com"})}}
    assert method.extract_identity(AuthData(payload=payload)) is None


def test_codex_ref_id_is_content_id() -> None:
    method = CodexAuthMethod()
    auth = AuthData(payload=_auth_json(
        account_id_claim="uuid-x", tokens_account_id="uuid-x", email="x@e.com"))
    assert method.ref_id(auth) == auth.content_id()
