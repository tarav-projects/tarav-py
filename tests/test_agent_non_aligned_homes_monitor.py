from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from agentos.testing import AgentosTestEnvironment


@pytest.fixture(autouse=True)
def _no_keychain(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")  # force .credentials.json path


def _env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    AgentosTestEnvironment.create(tmp_path).apply_environment(monkeypatch.setenv)
    from agentos._core.project import agentos_home_dir

    return agentos_home_dir()


def _claude_home(root: Path, name: str, *, uuid: str, token: str) -> Path:
    home = root / name
    home.mkdir(parents=True, exist_ok=True)
    (home / ".claude.json").write_text(
        json.dumps({"oauthAccount": {"accountUuid": uuid, "emailAddress": f"{name}@e.com", "displayName": name}})
    )
    (home / ".credentials.json").write_text(
        json.dumps({"claudeAiOauth": {"accessToken": token}})
    )
    return home


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


def _profile(home_root: Path, pid: str, homes: list[Path], accounts: list[str]) -> None:
    (home_root / "profiles").mkdir(parents=True, exist_ok=True)
    (home_root / "profiles" / f"{pid}.json").write_text(
        json.dumps({"id": pid, "provider": "claude-code", "homes": [str(h) for h in homes], "accounts": accounts})
    )


UUID = "973c403b-615a-47da-bc34-32ddc13a2e65"


def _scenario(home_root: Path, homes_dir: Path) -> tuple[Path, Path, Path]:
    """One aligned home, one drifted home, one foreign (error:unlisted-account) home."""
    aligned = _claude_home(homes_dir, "om", uuid=UUID, token="LIVE")
    drifted = _claude_home(homes_dir, "om-drift", uuid=UUID, token="OLD")
    foreign = _claude_home(homes_dir, "om-foreign", uuid="ffffffff-0000-0000-0000-000000000000", token="X")

    _settings(home_root, account="om", uuid=UUID)
    _profile(home_root, "claude-om", [aligned, drifted], ["om/browser"])
    _profile(home_root, "claude-foreign", [foreign], ["om/browser"])

    # active artifact == the aligned home's live secret → aligned aligns, drifted drifts
    from agentos.agent import auth_registry as R
    from agentos.claude.auth_method import ClaudeAuthMethod

    auth = ClaudeAuthMethod().read_auth_data(aligned)
    artifact_id = R.store_artifact("claude-code", auth)
    R.set_active("claude-code", "om", "browser", artifact_id)
    return aligned, drifted, foreign


def test_collect_non_aligned_homes_keeps_only_drift(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home_root = _env(monkeypatch, tmp_path)
    aligned, drifted, foreign = _scenario(home_root, tmp_path / "homes")

    from agentos.agent.monitor.account_rotation import collect_non_aligned_homes

    entries = collect_non_aligned_homes()
    homes = {e["home"]: e for e in entries}

    # only the drifted home survives the drift-only filter
    assert str(drifted.resolve()) in homes
    assert str(aligned.resolve()) not in homes      # aligned excluded
    assert str(foreign.resolve()) not in homes      # error:unlisted-account excluded
    assert homes[str(drifted.resolve())]["status"].startswith("drift")
    assert homes[str(drifted.resolve())]["provider"] == "claude-code"


def test_non_aligned_block_rows_render_label_and_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home_root = _env(monkeypatch, tmp_path)
    _aligned, drifted, _foreign = _scenario(home_root, tmp_path / "homes")

    from agentos.agent.monitor.account_rotation import (
        collect_non_aligned_homes,
        non_aligned_block_rows,
    )

    rows = non_aligned_block_rows(collect_non_aligned_homes())
    text = " ".join(r.text for r in rows)
    assert "drift" in text
    assert str(drifted.resolve()) in text
    assert "om/browser" in text


def _render_frame() -> object:
    from agentos.agent.monitor.clock import MONITOR_STARTUP_ALARM, MonitorClockSnapshot
    from agentos.agent.monitor.models import MonitorFrame, MonitorState
    from agentos.agent.monitor.workflows import AccountRotationWorkflow

    wf = AccountRotationWorkflow()
    state = MonitorState()
    frame = MonitorFrame()
    frame.prepare(tick=1)
    snapshot = MonitorClockSnapshot(tick=1, alarms={}, fired_alarm_names=(MONITOR_STARTUP_ALARM,))
    wf.loop(state, frame, snapshot)
    return frame


def _titles(frame: object) -> set[str]:
    return {b.get("title") for b in frame.blocks}


def test_workflow_shows_non_aligned_block_when_drift_present(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home_root = _env(monkeypatch, tmp_path)
    _scenario(home_root, tmp_path / "homes")  # includes a drifted home

    frame = _render_frame()
    assert "non-aligned homes" in _titles(frame)


def test_workflow_omits_non_aligned_block_when_all_aligned(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home_root = _env(monkeypatch, tmp_path)
    aligned = _claude_home(tmp_path / "homes", "om", uuid=UUID, token="LIVE")
    _settings(home_root, account="om", uuid=UUID)
    _profile(home_root, "claude-om", [aligned], ["om/browser"])
    from agentos.agent import auth_registry as R
    from agentos.claude.auth_method import ClaudeAuthMethod

    artifact_id = R.store_artifact("claude-code", ClaudeAuthMethod().read_auth_data(aligned))
    R.set_active("claude-code", "om", "browser", artifact_id)

    frame = _render_frame()
    titles = _titles(frame)
    assert "account-rotation" in titles          # the log block is always present
    assert "non-aligned homes" not in titles     # but no drift block when all aligned
