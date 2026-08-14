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
    (prov / "accounts.json").write_text(json.dumps({"provider": "codex", "accounts": {}}))


def _seed_orphan(uuid: str | None, ref: str, ts: str, auth_class: str = "auth-json") -> None:
    """Append a raw `_unknown` capture record with a chosen identity/ref/ts."""
    from tarav.agent import auth_registry as R

    auth_ref = {"provider_account_id": uuid} if uuid is not None else {}
    rec = {"ts": ts, "account": R.UNKNOWN_ACCOUNT, "method": auth_class, "class": auth_class,
           "auth_ref": auth_ref, "ref_id": ref, "artifact_id": ref}
    path = R.captures_path("codex")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")


def test_orphan_groups_by_identity_distinct_refs_recency(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    from tarav.agent import auth_registry as R

    _seed_orphan("uuid-a", "aref1", "2026-06-01T00:00:00Z")
    _seed_orphan("uuid-a", "aref2", "2026-06-03T00:00:00Z")  # same identity, newer ref
    _seed_orphan("uuid-b", "bref1", "2026-06-02T00:00:00Z")

    groups = R.orphan_groups("codex")
    # two distinct identities, ordered by last_seen desc → A (06-03) then B (06-02)
    assert [g["identity"].get("provider_account_id") for g in groups] == ["uuid-a", "uuid-b"]
    a = groups[0]
    assert [r["ref_id"] for r in a["refs"]] == ["aref2", "aref1"]  # newest first
    assert a["last_seen"] == "2026-06-03T00:00:00Z"
    assert a["auth_class"] == "auth-json"
    assert [r["ref_id"] for r in groups[1]["refs"]] == ["bref1"]


def test_orphan_groups_anchorless_falls_into_null_identity(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    from tarav.agent import auth_registry as R

    _seed_orphan(None, "cref1", "2026-06-01T00:00:00Z")

    groups = R.orphan_groups("codex")
    assert len(groups) == 1
    assert groups[0]["identity"].get("provider_account_id") is None
    assert [r["ref_id"] for r in groups[0]["refs"]] == ["cref1"]


def _store_orphan(uuid: str, token: str) -> str:
    """Store a real orphan artifact (secret in payload) + capture it; return ref."""
    from tarav.agent import auth_registry as R
    from tarav.agent.account_status import AccountIdentity
    from tarav.agent.auth_method import AuthData

    payload = {"tokens": {"access_token": token, "account_id": uuid}}
    ref = R.store_artifact("codex", AuthData(payload=payload))
    R.append_capture("codex", account=R.UNKNOWN_ACCOUNT, method="auth-json", auth_class="auth-json",
                     auth_ref=AccountIdentity(provider_account_id=uuid), ref_id=ref, artifact_id=ref)
    return ref


def _ns(**kw: object) -> "object":
    import argparse
    base = dict(provider="codex", json=False, _agentos_argv=[])
    base.update(kw)
    return argparse.Namespace(**base)


def test_orphans_text_lists_identity_without_secret(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _env(monkeypatch, tmp_path)
    from tarav.agent.commands.accounts import _cmd_agent_accounts_orphans

    ref = _store_orphan("uuid-a", "SUPERSECRET")

    assert _cmd_agent_accounts_orphans(_ns()) == 0
    out = capsys.readouterr().out
    assert "uuid-a" in out and ref[:12] in out
    assert "SUPERSECRET" not in out  # text must never leak the secret


def test_orphans_json_dumps_full_auth_data(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _env(monkeypatch, tmp_path)
    from tarav.agent.commands.accounts import _cmd_agent_accounts_orphans

    _store_orphan("uuid-a", "SUPERSECRET")

    assert _cmd_agent_accounts_orphans(_ns(json=True)) == 0
    payload = json.loads(capsys.readouterr().out)
    group = payload["orphans"][0]
    assert group["identity"]["provider_account_id"] == "uuid-a"
    # --json is the adoption worksheet: the full Auth.Data payload is present
    assert group["refs"][0]["auth_data"] == {"tokens": {"access_token": "SUPERSECRET", "account_id": "uuid-a"}}


def test_orphans_empty_reports_cleanly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _env(monkeypatch, tmp_path)
    from tarav.agent.commands.accounts import _cmd_agent_accounts_orphans

    assert _cmd_agent_accounts_orphans(_ns(json=True)) == 0
    assert json.loads(capsys.readouterr().out)["orphans"] == []
