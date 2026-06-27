from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from agentos.agent.auth_method import AuthData
from agentos.testing import AgentosTestEnvironment

ACC = "acc"


def _jwt(payload: dict[str, object]) -> str:
    def seg(obj: dict[str, object]) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")

    return f"{seg({'alg': 'none'})}.{seg(payload)}.sig"


def _codex_payload(exp: int) -> dict[str, object]:
    access = _jwt({"https://api.openai.com/auth": {"chatgpt_account_id": ACC}, "exp": exp})
    return {"tokens": {"access_token": access, "account_id": ACC}}


def _env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    AgentosTestEnvironment.create(tmp_path).apply_environment(monkeypatch.setenv)
    from agentos._core.project import agentos_home_dir

    home_root = agentos_home_dir()
    prov = home_root / "accounts" / "codex"
    prov.mkdir(parents=True, exist_ok=True)
    (prov / "accounts.json").write_text(json.dumps({
        "provider": "codex",
        "accounts": {"br": {"identity": {"provider_account_id": ACC},
                            "auth_methods": {"file": {"class": "auth-json"}}}},
    }))
    return home_root


def _seed_capture(payload: dict[str, object]) -> str:
    from agentos.agent import auth_registry as R
    from agentos.agent.account_status import AccountIdentity

    ref = R.store_artifact("codex", AuthData(payload=payload))
    R.append_capture("codex", account="br", method="file", auth_class="auth-json",
                     auth_ref=AccountIdentity(provider_account_id=ACC), ref_id=ref, artifact_id=ref)
    return ref


def _home(tmp_path: Path, payload: dict[str, object]) -> Path:
    h = tmp_path / "codex-br"
    h.mkdir()
    (h / "auth.json").write_text(json.dumps(payload))
    return h


def _profile(home_root: Path, homes: list[Path]) -> None:
    (home_root / "profiles").mkdir(parents=True, exist_ok=True)
    (home_root / "profiles" / "p.json").write_text(json.dumps(
        {"id": "p", "provider": "codex", "homes": [str(h) for h in homes], "accounts": ["br/file"]}
    ))


def test_sweep_rotate_only_moves_active_not_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home_root = _env(monkeypatch, tmp_path)
    from agentos.agent import auth_registry as R
    from agentos.agent.monitor.account_rotation import sweep_rotations

    stale_payload = _codex_payload(exp=1_000_000_000)
    home = _home(tmp_path, stale_payload)
    _profile(home_root, [home])
    stale = _seed_capture(stale_payload)
    fresher = _seed_capture(_codex_payload(exp=2_000_000_000))  # not in any home
    R.set_active("codex", "br", "file", stale)

    events = sweep_rotations(materialize=False)

    assert len(events) == 1
    assert (events[0].account, events[0].method) == ("br", "file")
    assert events[0].prev == stale and events[0].new == fresher
    assert R.active_ref("codex", "br", "file") == fresher
    assert json.loads((home / "auth.json").read_text()) == stale_payload  # home untouched


def test_sweep_materialize_writes_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home_root = _env(monkeypatch, tmp_path)
    from agentos.agent import auth_registry as R
    from agentos.agent.monitor.account_rotation import sweep_rotations

    stale_payload = _codex_payload(exp=1_000_000_000)
    fresher_payload = _codex_payload(exp=2_000_000_000)
    home = _home(tmp_path, stale_payload)
    _profile(home_root, [home])
    stale = _seed_capture(stale_payload)
    _seed_capture(fresher_payload)
    R.set_active("codex", "br", "file", stale)

    sweep_rotations(materialize=True)

    assert json.loads((home / "auth.json").read_text()) == fresher_payload  # home reconciled


def test_workflow_loop_rotates_on_alarm_and_writes_block(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home_root = _env(monkeypatch, tmp_path)
    from agentos.agent import auth_registry as R
    from agentos.agent.monitor.clock import ACCOUNT_ROTATION_PERIODIC_ALARM, MonitorClockSnapshot
    from agentos.agent.monitor.models import MonitorFrame, MonitorState, monitor_block_rows
    from agentos.agent.monitor.workflows import AccountRotationWorkflow

    stale_payload = _codex_payload(exp=1_000_000_000)
    home = _home(tmp_path, stale_payload)
    _profile(home_root, [home])
    stale = _seed_capture(stale_payload)
    fresher = _seed_capture(_codex_payload(exp=2_000_000_000))
    R.set_active("codex", "br", "file", stale)

    wf = AccountRotationWorkflow()
    state = MonitorState()
    frame = MonitorFrame()
    frame.prepare(tick=1)
    snapshot = MonitorClockSnapshot(tick=1, alarms={}, fired_alarm_names=(ACCOUNT_ROTATION_PERIODIC_ALARM,))

    wf.loop(state, frame, snapshot)

    assert R.active_ref("codex", "br", "file") == fresher  # rotated
    assert json.loads((home / "auth.json").read_text()) == stale_payload  # home untouched
    block = next(b for b in frame.blocks if b.get("title") == "account-rotation")
    row_text = " ".join(r.text for r in monitor_block_rows(block))
    assert "br/file" in row_text and fresher[:12] in row_text


def test_materialize_sweep_writes_home_and_records(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home_root = _env(monkeypatch, tmp_path)
    from agentos.agent import auth_registry as R
    from agentos.agent.monitor.account_rotation import materialize_sweep, recent_from_state
    from agentos.agent.monitor.models import MonitorState

    stale_payload = _codex_payload(exp=1_000_000_000)
    fresher_payload = _codex_payload(exp=2_000_000_000)
    home = _home(tmp_path, stale_payload)
    _profile(home_root, [home])
    stale = _seed_capture(stale_payload)
    fresher = _seed_capture(fresher_payload)
    R.set_active("codex", "br", "file", stale)

    state = MonitorState()
    events = materialize_sweep(state)

    # the `m` action rotated the active AND reconciled the home (writes homes)
    assert R.active_ref("codex", "br", "file") == fresher
    assert json.loads((home / "auth.json").read_text()) == fresher_payload
    assert any(e.new == fresher for e in events)
    assert recent_from_state(state)[-1]["new"] == fresher  # recorded in the ring


def test_push_recent_truncates_to_five() -> None:
    from agentos.agent.monitor.account_rotation import RotationEvent, push_recent

    recent: list[dict[str, object]] = []
    for i in range(7):
        ev = RotationEvent(ts=f"t{i}", provider="codex", account="br", method="file",
                           prev="p", new=f"n{i}")
        recent = push_recent(recent, [ev], limit=5)
    assert len(recent) == 5
    assert [r["new"] for r in recent] == ["n2", "n3", "n4", "n5", "n6"]  # last 5, chronological


def test_rotation_block_rows_empty_and_populated() -> None:
    from agentos.agent.monitor.account_rotation import rotation_block_rows

    empty = rotation_block_rows([])
    assert len(empty) == 1 and "no rotations" in empty[0].text.lower()

    rows = rotation_block_rows([
        {"ts": "t0", "provider": "codex", "account": "br", "method": "file",
         "prev": "aaaaaaaaaaaa0000", "new": "bbbbbbbbbbbb1111"},
    ])
    assert "codex" in rows[0].text and "br/file" in rows[0].text
    assert "aaaaaaaaaaaa" in rows[0].text and "bbbbbbbbbbbb" in rows[0].text
