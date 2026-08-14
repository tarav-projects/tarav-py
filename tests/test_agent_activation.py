from __future__ import annotations

import json
from pathlib import Path

import pytest

from tarav.testing import TaravTestEnvironment


def _env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    TaravTestEnvironment.create(tmp_path).apply_environment(monkeypatch.setenv)
    from tarav._core.project import tarav_home_dir

    prov = tarav_home_dir() / "accounts" / "codex"
    prov.mkdir(parents=True, exist_ok=True)
    (prov / "accounts.json").write_text(json.dumps({
        "provider": "codex",
        "accounts": {"br": {"identity": {"provider_account_id": "acc"},
                            "auth_methods": {"file": {"class": "auth-json"}}}},
    }))


def _seed(ref: str, ts: str = "2026-06-01T00:00:00Z") -> None:
    from tarav.agent import auth_registry as R

    path = R.captures_path("codex")
    path.parent.mkdir(parents=True, exist_ok=True)
    rec = {"ts": ts, "account": "br", "method": "file", "class": "auth-json",
           "auth_ref": {}, "ref_id": ref, "artifact_id": ref}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")


def test_activate_sets_active_for_unique_prefix(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    from tarav.agent import auth_registry as R
    from tarav.agent.account_status import AccountIdentity
    from tarav.agent.activation import activate
    from tarav.agent.auth_method import AuthData

    ref = R.store_artifact("codex", AuthData(payload={"tokens": {"account_id": "acc"}}))
    R.append_capture("codex", account="br", method="file", auth_class="auth-json",
                     auth_ref=AccountIdentity(), ref_id=ref, artifact_id=ref)

    result = activate("codex", "br", "file", ref[:8])
    assert result.ref_id == ref
    assert R.active_ref("codex", "br", "file") == ref


def test_activate_ambiguous_and_missing_raise(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    from tarav._core.errors import CliError
    from tarav.agent.activation import activate

    _seed("abcd0001")
    _seed("abcd0002")

    with pytest.raises(CliError):  # ambiguous prefix
        activate("codex", "br", "file", "abcd")
    with pytest.raises(CliError):  # no match
        activate("codex", "br", "file", "zzzz")
