from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest

from tarav.l1.agent.commands.accounts import _cmd_agent_accounts_list
from tarav.l0.testing import TaravTestEnvironment


def _env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    TaravTestEnvironment.create(tmp_path).apply_environment(monkeypatch.setenv)
    from tarav.l0._core.project import tarav_home_dir

    prov = tarav_home_dir() / "accounts" / "codex"
    prov.mkdir(parents=True, exist_ok=True)
    (prov / "accounts.json").write_text(json.dumps({
        "provider": "codex",
        "accounts": {"br": {"identity": {"provider_account_id": "acc"},
                            "auth_methods": {"file": {"class": "auth-json"}}}},
    }))


def _seed(ref: str, ts: str) -> None:
    """Append a raw capture record with a chosen ref_id + ts."""
    from tarav.l1.agent import auth_registry as R
    path = R.captures_path("codex")
    path.parent.mkdir(parents=True, exist_ok=True)
    rec = {"ts": ts, "account": "br", "method": "file", "class": "auth-json",
           "auth_ref": {}, "ref_id": ref, "artifact_id": ref}
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")


def test_pool_for_distinct_refs_recency_ordered(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    from tarav.l1.agent import auth_registry as R

    _seed("aaaa", "2026-06-01T00:00:00Z")
    _seed("bbbb", "2026-06-03T00:00:00Z")
    _seed("aaaa", "2026-06-02T00:00:00Z")  # dup ref, later ts

    pool = R.pool_for("codex", "br", "file")
    assert [e["ref_id"] for e in pool] == ["bbbb", "aaaa"]  # newest first
    # the duplicated ref keeps its most recent ts
    assert next(e for e in pool if e["ref_id"] == "aaaa")["ts"] == "2026-06-02T00:00:00Z"


def test_list_marks_active_and_orders_by_recency(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _env(monkeypatch, tmp_path)
    from tarav.l1.agent import auth_registry as R

    _seed("aaaa1111", "2026-06-01T00:00:00Z")
    _seed("bbbb2222", "2026-06-03T00:00:00Z")
    R.set_active("codex", "br", "file", "aaaa1111")

    rc = _cmd_agent_accounts_list(argparse.Namespace(
        provider="codex", account="br/file", json=True, _agentos_argv=[]))
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    rows = out["pools"][0]["entries"]
    assert [r["ref_id"] for r in rows] == ["bbbb2222", "aaaa1111"]
    assert rows[1]["active"] is True and rows[0]["active"] is False


def test_resolve_ref_prefix_unique_ambiguous_and_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    from tarav.l0._core.errors import CliError
    from tarav.l1.agent import auth_registry as R

    _seed("abcd0001", "2026-06-01T00:00:00Z")
    _seed("abcd0002", "2026-06-02T00:00:00Z")
    _seed("ef120003", "2026-06-03T00:00:00Z")

    # unique prefix resolves to the full ref
    assert R.resolve_ref_prefix("codex", "br", "file", "ef12") == "ef120003"
    # full ref is the trivial unique case
    assert R.resolve_ref_prefix("codex", "br", "file", "abcd0001") == "abcd0001"
    # ambiguous prefix raises
    with pytest.raises(CliError):
        R.resolve_ref_prefix("codex", "br", "file", "abcd")
    # no match raises
    with pytest.raises(CliError):
        R.resolve_ref_prefix("codex", "br", "file", "zzzz")


def test_activate_accepts_unique_prefix(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    from tarav.l1.agent import auth_registry as R
    from tarav.l1.agent.account_status import AccountIdentity
    from tarav.l1.agent.auth_method import AuthData
    from tarav.l1.agent.commands.accounts import _cmd_agent_accounts_activate

    # store a real artifact so auth_data_for_ref resolves, and seed its capture
    auth = AuthData(payload={"tokens": {"account_id": "acc"}})
    ref = R.store_artifact("codex", auth)
    R.append_capture("codex", account="br", method="file", auth_class="auth-json",
                     auth_ref=AccountIdentity(), ref_id=ref, artifact_id=ref)

    rc = _cmd_agent_accounts_activate(argparse.Namespace(
        provider="codex", account="br/file", ref=ref[:8], json=False, _agentos_argv=[]))
    assert rc == 0
    assert R.active_ref("codex", "br", "file") == ref
