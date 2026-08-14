from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from tarav.agent.auth_method import AuthData
from tarav.testing import TaravTestEnvironment

ACC = "acc"


def _jwt(payload: dict[str, object]) -> str:
    def seg(obj: dict[str, object]) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")

    return f"{seg({'alg': 'none'})}.{seg(payload)}.sig"


def _codex_payload(exp: int) -> dict[str, object]:
    access = _jwt({"https://api.openai.com/auth": {"chatgpt_account_id": ACC}, "exp": exp})
    return {"tokens": {"access_token": access, "account_id": ACC}}


def _env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    TaravTestEnvironment.create(tmp_path).apply_environment(monkeypatch.setenv)
    from tarav._core.project import tarav_home_dir

    home_root = tarav_home_dir()
    prov = home_root / "accounts" / "codex"
    prov.mkdir(parents=True, exist_ok=True)
    (prov / "accounts.json").write_text(json.dumps({
        "provider": "codex",
        "accounts": {"br": {"identity": {"provider_account_id": ACC},
                            "auth_methods": {"file": {"class": "auth-json"}}}},
    }))
    return home_root


def _seed_capture(payload: dict[str, object]) -> str:
    from tarav.agent import auth_registry as R
    from tarav.agent.account_status import AccountIdentity

    ref = R.store_artifact("codex", AuthData(payload=payload))
    R.append_capture("codex", account="br", method="file", auth_class="auth-json",
                     auth_ref=AccountIdentity(provider_account_id=ACC), ref_id=ref, artifact_id=ref)
    return ref


def _home(tmp_path: Path, payload: dict[str, object]) -> Path:
    h = tmp_path / "codex-br"
    h.mkdir()
    (h / "auth.json").write_text(json.dumps(payload))
    return h


def _empty_home(tmp_path: Path) -> Path:
    h = tmp_path / "codex-empty"
    h.mkdir()
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
    from tarav.agent import auth_registry as R
    from tarav.agent.accounts_log import read_recent_events
    from tarav.agent.monitor.account_rotation import sweep_rotations

    stale_payload = _codex_payload(exp=1_000_000_000)
    home = _home(tmp_path, stale_payload)
    _profile(home_root, [home])
    stale = _seed_capture(stale_payload)
    fresher = _seed_capture(_codex_payload(exp=2_000_000_000))  # not in any home
    R.set_active("codex", "br", "file", stale)

    sweep_rotations(materialize=False)

    assert R.active_ref("codex", "br", "file") == fresher
    assert json.loads((home / "auth.json").read_text()) == stale_payload  # home untouched
    # the rotation is recorded in the durable accounts-log (the new source of truth)
    events = read_recent_events(event="rotate")
    assert len(events) == 1
    assert (events[0]["account"], events[0]["method"]) == ("br", "file")
    assert events[0]["payload"] == {"previous_active": stale, "new_active": fresher}


def test_sweep_materialize_writes_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home_root = _env(monkeypatch, tmp_path)
    from tarav.agent import auth_registry as R
    from tarav.agent.monitor.account_rotation import sweep_rotations

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
    from tarav.agent import auth_registry as R
    from tarav.agent.monitor.clock import ACCOUNT_ROTATION_PERIODIC_ALARM, MonitorClockSnapshot
    from tarav.agent.monitor.models import MonitorFrame, MonitorState
    from tarav.agent.monitor.workflows import AccountRotationWorkflow

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
    block = next(b for b in frame.blocks if b.title == "account-rotation")
    row_text = " ".join(r.text for r in block.rows)
    assert "br/file" in row_text and fresher[:12] in row_text


def test_materialize_sweep_writes_home_and_records(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home_root = _env(monkeypatch, tmp_path)
    from tarav.agent import auth_registry as R
    from tarav.agent.accounts_log import read_recent_events
    from tarav.agent.monitor.account_rotation import materialize_sweep

    stale_payload = _codex_payload(exp=1_000_000_000)
    fresher_payload = _codex_payload(exp=2_000_000_000)
    home = _home(tmp_path, stale_payload)
    _profile(home_root, [home])
    stale = _seed_capture(stale_payload)
    fresher = _seed_capture(fresher_payload)
    R.set_active("codex", "br", "file", stale)

    materialize_sweep()

    # the `m` action rotated the active AND reconciled the home (writes homes)
    assert R.active_ref("codex", "br", "file") == fresher
    assert json.loads((home / "auth.json").read_text()) == fresher_payload
    # the rotation is recorded in the accounts-log
    assert read_recent_events(event="rotate")[0]["payload"]["new_active"] == fresher


def test_materialize_sweep_returns_skipped_results(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home_root = _env(monkeypatch, tmp_path)
    from tarav.agent.monitor.account_rotation import materialize_sweep

    home = _empty_home(tmp_path)
    _profile(home_root, [home])

    results = materialize_sweep()

    assert any(
        result.provider == "codex"
        and result.home == home
        and result.status == "skipped"
        for result in results
    )


def test_materialize_sweep_returns_provider_error_results(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    import tarav.agent.monitor.account_rotation as account_rotation

    monkeypatch.setattr(account_rotation, "providers_with_auth_methods", lambda: ("codex",))

    def fail_capture(provider: str) -> None:
        raise RuntimeError(f"{provider} failed")

    monkeypatch.setattr(account_rotation, "capture_all_homes", fail_capture)

    results = account_rotation.materialize_sweep()

    assert len(results) == 1
    assert results[0].provider == "codex"
    assert results[0].status == "error"
    assert results[0].error_type == "RuntimeError"
    assert results[0].message == "codex failed"


def test_workflow_materialize_alarm_writes_home_and_refreshes_block(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home_root = _env(monkeypatch, tmp_path)
    from tarav.agent import auth_registry as R
    from tarav.agent.monitor.clock import MONITOR_MATERIALIZE_ALARM, MonitorClockSnapshot
    from tarav.agent.monitor.models import MonitorFrame, MonitorState
    from tarav.agent.monitor.workflows import AccountRotationWorkflow

    stale_payload = _codex_payload(exp=1_000_000_000)
    fresher_payload = _codex_payload(exp=2_000_000_000)
    home = _home(tmp_path, stale_payload)
    _profile(home_root, [home])
    stale = _seed_capture(stale_payload)
    fresher = _seed_capture(fresher_payload)
    R.set_active("codex", "br", "file", stale)

    wf = AccountRotationWorkflow()
    state = MonitorState()
    frame = MonitorFrame()
    frame.prepare(tick=1)
    snapshot = MonitorClockSnapshot(
        tick=1, alarms={}, fired_alarm_names=(MONITOR_MATERIALIZE_ALARM,)
    )

    wf.loop(state, frame, snapshot)

    assert R.active_ref("codex", "br", "file") == fresher
    assert json.loads((home / "auth.json").read_text()) == fresher_payload
    block = next(b for b in frame.blocks if b.title == "account-rotation")
    row_text = " ".join(r.text for r in block.rows)
    assert "br/file" in row_text and fresher[:12] in row_text
    materialize_block = next(b for b in frame.blocks if b.title == "account-materialize")
    materialize_text = " ".join(r.text for r in materialize_block.rows)
    assert "done" in materialize_text
    assert "materialized: 1" in materialize_text
    assert "[aligned]" not in materialize_text


def test_materialize_status_block_omits_aligned_results() -> None:
    from tarav.agent.monitor.account_rotation import materialize_status_block_rows

    rows = materialize_status_block_rows(
        {
            "status": "done",
            "counts": {"materialized": 0, "aligned": 16, "skipped": 0, "error": 0},
            "results": [
                {
                    "provider": "codex",
                    "account": "br",
                    "method": "file",
                    "home": "/tmp/codex",
                    "status": "aligned",
                }
            ],
        }
    )

    text = " ".join(row.text for row in rows)
    assert "aligned:" not in text
    assert "[aligned]" not in text
    assert "no drifted homes" in text


def test_sweep_writes_no_monitor_log_rotation_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home_root = _env(monkeypatch, tmp_path)
    from tarav.agent import auth_registry as R
    from tarav.agent.monitor.account_rotation import sweep_rotations
    from tarav.agent.monitor_log import monitor_log_dir

    stale = _seed_capture(_codex_payload(exp=1_000_000_000))
    _seed_capture(_codex_payload(exp=2_000_000_000))
    _profile(home_root, [_home(tmp_path, _codex_payload(exp=1_000_000_000))])
    R.set_active("codex", "br", "file", stale)

    sweep_rotations(materialize=False)

    # monitor-log carries operational events only — no account_rotation line
    log_dir = monitor_log_dir()
    text = "".join(p.read_text() for p in log_dir.glob("*.jsonl")) if log_dir.exists() else ""
    assert "account_rotation" not in text


def test_rotation_block_rows_empty_and_populated() -> None:
    from tarav.agent.monitor.account_rotation import rotation_block_rows

    empty = rotation_block_rows([])
    assert len(empty) == 1 and "no rotations" in empty[0].text.lower()

    rows = rotation_block_rows([
        {"recorded_at": "t0", "provider": "codex", "account": "br", "method": "file",
         "payload": {"previous_active": "aaaaaaaaaaaa0000", "new_active": "bbbbbbbbbbbb1111"}},
    ])
    assert "codex" in rows[0].text and "br/file" in rows[0].text
    assert "aaaaaaaaaaaa" in rows[0].text and "bbbbbbbbbbbb" in rows[0].text
