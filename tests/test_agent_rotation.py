from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentos.agent.auth_method import AuthData
from agentos.testing import AgentosTestEnvironment


def _env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    AgentosTestEnvironment.create(tmp_path).apply_environment(monkeypatch.setenv)
    from agentos._core.project import agentos_home_dir

    prov = agentos_home_dir() / "accounts" / "codex"
    prov.mkdir(parents=True, exist_ok=True)
    (prov / "accounts.json").write_text(json.dumps({
        "provider": "codex",
        "accounts": {"br": {"identity": {"provider_account_id": "acc"},
                            "auth_methods": {"file": {"class": "auth-json"}}}},
    }))


def _seed_artifact(account: str, method: str, payload: dict[str, object]) -> str:
    """Store an artifact and record a capture for codex br/<method>, return its id."""
    from agentos.agent import auth_registry as R
    from agentos.agent.account_status import AccountIdentity

    auth = AuthData(payload=payload)
    artifact_id = R.store_artifact("codex", auth)
    R.append_capture("codex", account=account, method=method, auth_class="auth-json",
                     auth_ref=AccountIdentity(provider_account_id="acc"), ref_id=artifact_id, artifact_id=artifact_id)
    return artifact_id


def test_captures_for_returns_account_method_records(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    from agentos.agent import auth_registry as R

    a = _seed_artifact("br", "file", {"v": 1})
    _seed_artifact("br", "file", {"v": 2})
    _seed_artifact("jp", "file", {"v": 3})  # different account

    records = R.captures_for("codex", "br", "file")
    assert {r["artifact_id"] for r in records} == {a, AuthData(payload={"v": 2}).content_id()}


def test_rotation_rank_default_is_capture_time(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # the ABC default ranks by capture time; both real providers override it, so
    # exercise the default through a minimal stub.
    from agentos.agent.auth_method import AuthData, AuthMethod

    class _Stub(AuthMethod):
        name = "stub"
        provider = "stub"
        materializable = False

        def read_auth_data(self, home):  # pragma: no cover - unused
            return None

        def extract_identity(self, auth_data):  # pragma: no cover - unused
            return None

        def materialize(self, auth_data, home):  # pragma: no cover - unused
            return None

        def ref_id(self, auth_data):  # pragma: no cover - unused
            return auth_data.content_id()

    assert _Stub().rotation_rank(AuthData(payload={}), captured_at=123.0) == 123.0


def test_rotate_activates_head_by_rank(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    from agentos.agent import auth_registry as R
    from agentos.agent.rotation import rotate

    old = _seed_artifact("br", "file", _codex_payload(exp=1_000_000_000))
    new = _seed_artifact("br", "file", _codex_payload(exp=2_000_000_000))  # higher exp → head
    R.set_active("codex", "br", "file", old)

    result = rotate("codex", "br", "file")
    assert result.changed is True
    assert result.previous_active == old and result.new_active == new
    assert R.active_ref("codex", "br", "file") == new

    # idempotent: second rotate changes nothing
    assert rotate("codex", "br", "file").changed is False


def test_rotate_tie_break_prefers_later_capture(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # equal rank (same exp) → the later-captured artifact wins (capture sequence).
    _env(monkeypatch, tmp_path)
    from agentos.agent import auth_registry as R
    from agentos.agent.rotation import rotate

    first = _seed_artifact("br", "file", {**_codex_payload(exp=1_500_000_000), "n": 1})
    last = _seed_artifact("br", "file", {**_codex_payload(exp=1_500_000_000), "n": 2})
    R.set_active("codex", "br", "file", first)

    assert rotate("codex", "br", "file").new_active == last


def test_rotate_dry_run_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    from agentos.agent import auth_registry as R
    from agentos.agent.rotation import rotate

    old = _seed_artifact("br", "file", _codex_payload(exp=1_000_000_000))
    new = _seed_artifact("br", "file", _codex_payload(exp=2_000_000_000))
    R.set_active("codex", "br", "file", old)

    result = rotate("codex", "br", "file", dry_run=True)
    assert result.changed is True and result.new_active == new
    assert R.active_ref("codex", "br", "file") == old  # unchanged on disk


def test_rotate_skips_empty_pool(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    from agentos.agent.rotation import rotate

    result = rotate("codex", "br", "file")
    assert result.skipped is True and result.changed is False


def _codex_payload(exp: int) -> dict[str, object]:
    import base64

    def seg(obj: dict[str, object]) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")

    access = f"{seg({'alg': 'none'})}.{seg({'exp': exp})}.sig"
    return {"tokens": {"access_token": access, "account_id": "acc"}}


def test_codex_rotation_rank_prefers_later_token_exp_over_capture_order(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    from agentos.agent import auth_registry as R
    from agentos.agent.rotation import rotate

    fresher = _seed_artifact("br", "file", _codex_payload(exp=2_000_000_000))  # captured FIRST
    staler = _seed_artifact("br", "file", _codex_payload(exp=1_000_000_000))   # captured LAST
    R.set_active("codex", "br", "file", staler)

    result = rotate("codex", "br", "file")
    # later capture order would pick `staler`; the token exp must win → `fresher`
    assert result.new_active == fresher and result.changed is True


def test_drift_against_active_directions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    from agentos.agent import auth_registry as R
    from agentos.agent.rotation import drift_against_active
    from agentos.agent.providers.codex.auth_method import CodexAuthMethod

    active = _seed_artifact("br", "file", _codex_payload(exp=1_500_000_000))
    R.set_active("codex", "br", "file", active)
    method = CodexAuthMethod()

    newer = AuthData(payload=_codex_payload(exp=2_000_000_000))
    older = AuthData(payload=_codex_payload(exp=1_000_000_000))
    same = AuthData(payload=_codex_payload(exp=1_500_000_000))

    assert drift_against_active("codex", "br", "file", method, newer) == "newer"
    assert drift_against_active("codex", "br", "file", method, older) == "older"
    assert drift_against_active("codex", "br", "file", method, same) is None  # tie → unorderable


def test_drift_against_active_none_when_no_active(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    from agentos.agent.rotation import drift_against_active
    from agentos.agent.providers.codex.auth_method import CodexAuthMethod

    home = AuthData(payload=_codex_payload(exp=2_000_000_000))
    # nothing activated for br/file → no basis to compare against
    assert drift_against_active("codex", "br", "file", CodexAuthMethod(), home) is None


def _claude_seed(account: str, expires_at: int) -> str:
    from agentos.agent import auth_registry as R
    from agentos.agent.account_status import AccountIdentity

    payload = {"claudeAiOauth": {"accessToken": "t", "expiresAt": expires_at},
               "oauthAccount": {"accountUuid": "u"}}
    artifact_id = R.store_artifact("claude-code", AuthData(payload=payload))
    R.append_capture("claude-code", account=account, method="browser",
                     auth_class="ambient-browser-login",
                     auth_ref=AccountIdentity(provider_account_id="u"), ref_id=artifact_id, artifact_id=artifact_id)
    return artifact_id


def test_claude_rotation_rank_prefers_later_expiresat(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    from agentos._core.project import agentos_home_dir
    prov = agentos_home_dir() / "accounts" / "claude-code"
    prov.mkdir(parents=True, exist_ok=True)
    (prov / "accounts.json").write_text(json.dumps({
        "provider": "claude-code",
        "accounts": {"om": {"identity": {"account_uuid": "u"},
                            "auth_methods": {"browser": {"class": "ambient-browser-login"}}}},
    }))

    from agentos.agent import auth_registry as R
    from agentos.agent.rotation import rotate

    fresher = _claude_seed("om", 1782476057402)  # captured FIRST, later expiry
    staler = _claude_seed("om", 1000000000000)   # captured LAST, earlier expiry
    R.set_active("claude-code", "om", "browser", staler)

    assert rotate("claude-code", "om", "browser").new_active == fresher
