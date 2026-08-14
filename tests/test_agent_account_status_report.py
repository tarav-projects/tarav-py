from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from tarav.agent.auth_method import AuthData
from tarav.testing import TaravTestEnvironment


@pytest.fixture(autouse=True)
def _no_keychain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")


def _env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    TaravTestEnvironment.create(tmp_path).apply_environment(monkeypatch.setenv)
    from tarav._core.project import tarav_home_dir

    return tarav_home_dir()


def _claude_home(root: Path, name: str, *, uuid: str, logged_in: bool) -> Path:
    home = root / name
    home.mkdir(parents=True, exist_ok=True)
    (home / ".claude.json").write_text(
        json.dumps({"oauthAccount": {"accountUuid": uuid, "emailAddress": f"{name}@e.com", "displayName": name}})
    )
    if logged_in:
        (home / ".credentials.json").write_text(
            json.dumps({"claudeAiOauth": {"accessToken": f"tok-{name}"}})
        )
    return home


def _profile(home_root: Path, pid: str, homes: list[Path], accounts: list[str]) -> None:
    (home_root / "profiles").mkdir(parents=True, exist_ok=True)
    (home_root / "profiles" / f"{pid}.json").write_text(
        json.dumps({"id": pid, "provider": "claude-code", "homes": [str(h) for h in homes], "accounts": accounts})
    )


def _settings(home_root: Path, *, account: str, uuid: str) -> None:
    prov = home_root / "accounts" / "claude-code"
    prov.mkdir(parents=True, exist_ok=True)
    (prov / "accounts.json").write_text(
        json.dumps({
            "provider": "claude-code",
            "accounts": {account: {"identity": {"account_uuid": uuid},
                                   "auth_methods": {"browser": {"class": "ambient-browser-login"}}}},
        })
    )


def test_status_reports_aligned_drift_undeterminable_and_unlisted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home_root = _env(monkeypatch, tmp_path)
    homes_dir = tmp_path / "homes"
    UUID = "973c403b-615a-47da-bc34-32ddc13a2e65"

    # aligned home, a logged-out home, and a home holding a foreign identity
    aligned = _claude_home(homes_dir, "om", uuid=UUID, logged_in=True)
    loggedout = _claude_home(homes_dir, "om-managed", uuid=UUID, logged_in=False)
    foreign = _claude_home(homes_dir, "om-foreign", uuid="ffffffff-0000-0000-0000-000000000000", logged_in=True)

    _settings(home_root, account="om", uuid=UUID)
    _profile(home_root, "claude-om", [aligned, loggedout], ["om/browser"])
    _profile(home_root, "claude-foreign", [foreign], ["om/browser"])

    # make the aligned home's live Auth.Data the active artifact
    from tarav.agent import auth_registry as R
    from tarav.agent.providers.claude_code.auth_method import ClaudeAuthMethod

    auth = ClaudeAuthMethod().read_auth_data(aligned)
    artifact_id = R.store_artifact("claude-code", auth)
    R.set_active("claude-code", "om", "browser", artifact_id)

    from tarav.agent.account_status_report import build_status_report

    report = build_status_report("claude-code")
    by_home = {item["home"]: item for item in report["homes"]}

    assert by_home[str(aligned.resolve())]["status"] == "aligned"
    assert by_home[str(aligned.resolve())]["account"] == "om"
    assert by_home[str(loggedout.resolve())]["status"] == "undeterminable"
    assert by_home[str(foreign.resolve())]["status"] == "error:unlisted-account"


def test_status_drift_when_active_differs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home_root = _env(monkeypatch, tmp_path)
    UUID = "973c403b-615a-47da-bc34-32ddc13a2e65"
    home = _claude_home(tmp_path / "homes", "om", uuid=UUID, logged_in=True)
    _settings(home_root, account="om", uuid=UUID)
    _profile(home_root, "claude-om", [home], ["om/browser"])

    # active points at a DIFFERENT artifact than what's live in the home
    from tarav.agent import auth_registry as R

    R.store_artifact("claude-code", AuthData(payload={"claudeAiOauth": {"accessToken": "OLD"}, "oauthAccount": {"accountUuid": UUID}}))
    R.set_active("claude-code", "om", "browser", "deadbeef")

    from tarav.agent.account_status_report import build_status_report

    item = build_status_report("claude-code")["homes"][0]
    assert item["status"] == "drift"
    assert item["account"] == "om"


def _claude_home_exp(root: Path, name: str, *, uuid: str, expires_at: int) -> Path:
    """A logged-in claude home whose secret carries a rotation-rankable expiry."""
    home = root / name
    home.mkdir(parents=True, exist_ok=True)
    (home / ".claude.json").write_text(
        json.dumps({"oauthAccount": {"accountUuid": uuid, "emailAddress": f"{name}@e.com", "displayName": name}})
    )
    (home / ".credentials.json").write_text(
        json.dumps({"claudeAiOauth": {"accessToken": f"tok-{name}", "expiresAt": expires_at}})
    )
    return home


def _activate_claude(*, uuid: str, expires_at: int) -> None:
    from tarav.agent import auth_registry as R
    artifact = R.store_artifact(
        "claude-code",
        AuthData(payload={"claudeAiOauth": {"accessToken": "active", "expiresAt": expires_at},
                          "oauthAccount": {"accountUuid": uuid}}),
    )
    R.set_active("claude-code", "om", "browser", artifact)


@pytest.mark.parametrize("home_exp, expected", [
    (2_000_000_000_000, "drift:home-newer"),   # home fresher than active → rotate
    (500_000_000_000, "drift:home-older"),     # active fresher than home → materialize
])
def test_status_drift_is_qualified_by_freshness(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, home_exp: int, expected: str
) -> None:
    home_root = _env(monkeypatch, tmp_path)
    UUID = "973c403b-615a-47da-bc34-32ddc13a2e65"
    home = _claude_home_exp(tmp_path / "homes", "om", uuid=UUID, expires_at=home_exp)
    _settings(home_root, account="om", uuid=UUID)
    _profile(home_root, "claude-om", [home], ["om/browser"])
    _activate_claude(uuid=UUID, expires_at=1_000_000_000_000)

    from tarav.agent.account_status_report import build_status_report

    assert build_status_report("claude-code")["homes"][0]["status"] == expected


def test_status_drift_no_active_when_nothing_registered(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home_root = _env(monkeypatch, tmp_path)
    UUID = "973c403b-615a-47da-bc34-32ddc13a2e65"
    home = _claude_home_exp(tmp_path / "homes", "om", uuid=UUID, expires_at=1_000_000_000_000)
    _settings(home_root, account="om", uuid=UUID)
    _profile(home_root, "claude-om", [home], ["om/browser"])
    # no set_active → nothing registered for om/browser

    from tarav.agent.account_status_report import build_status_report

    assert build_status_report("claude-code")["homes"][0]["status"] == "drift:no-active"


def test_account_limit_summary_estimated_flag() -> None:
    from tarav.agent.account_status import AccountLimit, UsageOverTimeLimitData

    usage = UsageOverTimeLimitData(
        used_percent=40,
        period_started_at="2026-07-15T10:00:00Z",
        period_ends_at="2026-07-15T15:00:00Z",
        period_duration_mins=300,
        resets_at="2026-07-15T15:00:00Z",
    )
    real = AccountLimit(
        limit_class="usage_over_time",
        limit_id="burst",
        limit_name="burst",
        limit_label="Burst",
        usage_over_time=usage,
    )
    estimated = AccountLimit(
        limit_class="usage_over_time",
        limit_id="burst",
        limit_name="burst",
        limit_label="Burst",
        usage_over_time=usage,
        estimated=True,
    )
    assert "estimated" not in real.summary()
    assert estimated.summary()["estimated"] is True
