from __future__ import annotations

import base64
import datetime
import json
from pathlib import Path

import pytest

from agentos.agent.auth_method import AuthData
from agentos.testing import AgentosTestEnvironment

ACC = "3b74c6d3-b4a8-45ea-9d5b-852bdbd92899"


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


def _jwt(payload: dict[str, object]) -> str:
    def seg(obj: dict[str, object]) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")

    return f"{seg({'alg': 'none'})}.{seg(payload)}.sig"


def _codex_payload(exp: int) -> dict[str, object]:
    access = _jwt({"https://api.openai.com/auth": {"chatgpt_account_id": ACC}, "exp": exp})
    return {"tokens": {"access_token": access, "account_id": ACC}}


def _seed_capture(payload: dict[str, object]) -> str:
    from agentos.agent import auth_registry as R
    from agentos.agent.account_status import AccountIdentity

    ref = R.store_artifact("codex", AuthData(payload=payload))
    R.append_capture("codex", account="br", method="file", auth_class="auth-json",
                     auth_ref=AccountIdentity(provider_account_id=ACC), ref_id=ref, artifact_id=ref)
    return ref


def _codex_home(tmp_path: Path, payload: dict[str, object]) -> Path:
    h = tmp_path / "codex-br"
    h.mkdir(parents=True, exist_ok=True)
    (h / "auth.json").write_text(json.dumps(payload))
    return h


def _profile(home_root: Path, homes: list[Path]) -> None:
    (home_root / "profiles").mkdir(parents=True, exist_ok=True)
    (home_root / "profiles" / "p.json").write_text(json.dumps(
        {"id": "p", "provider": "codex", "homes": [str(h) for h in homes], "accounts": ["br/file"]}
    ))


def _events() -> list[dict[str, object]]:
    from agentos.agent.accounts_log import accounts_log_dir

    log_dir = accounts_log_dir()
    if not log_dir.exists():
        return []
    out: list[dict[str, object]] = []
    for path in sorted(log_dir.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line))
    return out


def test_append_account_event_writes_dated_line(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    from agentos.agent.accounts_log import accounts_log_dir, append_account_event

    path = append_account_event(
        event="rotate", provider="codex", account="jp", method="file",
        payload={"previous_active": "a", "new_active": "b"},
    )

    assert path is not None
    today = datetime.datetime.now(tz=datetime.UTC).strftime("%Y%m%d")
    assert path == accounts_log_dir() / f"{today}.jsonl"

    events = _events()
    assert len(events) == 1
    rec = events[0]
    assert rec["event"] == "rotate"
    assert rec["provider"] == "codex"
    assert rec["account"] == "jp"
    assert rec["method"] == "file"
    assert rec["payload"] == {"previous_active": "a", "new_active": "b"}
    assert str(rec["recorded_at"]).endswith("Z")


def test_append_account_event_best_effort_on_bad_payload(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    from agentos.agent.accounts_log import append_account_event

    result = append_account_event(
        event="rotate", provider="codex", account="jp", method="file",
        payload={"x": object()},  # unserializable
    )

    assert result is None
    assert _events() == []  # no partial line written


def _events_of(event: str) -> list[dict[str, object]]:
    return [e for e in _events() if e["event"] == event]


# --- Slice 2: rotate emits -------------------------------------------------


def test_rotate_emits_on_real_change(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    from agentos.agent import auth_registry as R
    from agentos.agent.rotation import rotate

    stale = _seed_capture(_codex_payload(exp=1_000_000_000))
    fresher = _seed_capture(_codex_payload(exp=2_000_000_000))
    R.set_active("codex", "br", "file", stale)

    rotate("codex", "br", "file")

    events = _events_of("rotate")
    assert len(events) == 1
    assert events[0]["account"] == "br" and events[0]["method"] == "file"
    assert events[0]["payload"] == {"previous_active": stale, "new_active": fresher}


def test_rotate_dry_run_emits_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    from agentos.agent import auth_registry as R
    from agentos.agent.rotation import rotate

    stale = _seed_capture(_codex_payload(exp=1_000_000_000))
    _seed_capture(_codex_payload(exp=2_000_000_000))
    R.set_active("codex", "br", "file", stale)

    rotate("codex", "br", "file", dry_run=True)

    assert _events_of("rotate") == []  # preview never logs


# --- Slice 3: capture emits ------------------------------------------------


def test_capture_emits_on_new_capture_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home_root = _env(monkeypatch, tmp_path)
    from agentos.agent.capture import capture_home

    home = _codex_home(tmp_path, _codex_payload(exp=1_000_000_000))
    _profile(home_root, [home])

    capture_home("codex", home)
    assert len(_events_of("capture")) == 1

    capture_home("codex", home)  # already captured → no new event
    assert len(_events_of("capture")) == 1


def test_capture_dry_run_emits_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home_root = _env(monkeypatch, tmp_path)
    from agentos.agent.capture import capture_home

    home = _codex_home(tmp_path, _codex_payload(exp=1_000_000_000))
    _profile(home_root, [home])

    capture_home("codex", home, dry_run=True)
    assert _events_of("capture") == []


# --- Slice 4: activate emits -----------------------------------------------


def test_activate_emits(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    from agentos.agent.activation import activate

    ref = _seed_capture(_codex_payload(exp=1_000_000_000))

    activate("codex", "br", "file", ref)

    events = _events_of("activate")
    assert len(events) == 1
    assert events[0]["payload"] == {"ref_id": ref}


# --- Slice 5: materialize emits --------------------------------------------


def test_materialize_emits_on_write_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    from agentos.agent import auth_registry as R
    from agentos.agent.materialization import materialize_account

    active = _seed_capture(_codex_payload(exp=2_000_000_000))
    R.set_active("codex", "br", "file", active)
    home = _codex_home(tmp_path, _codex_payload(exp=1_000_000_000))  # drifted (older)

    materialize_account("codex", "br", "file", home)
    assert len(_events_of("materialize")) == 1
    assert _events_of("materialize")[0]["payload"]["active_ref"] == active

    # now aligned → no new event
    materialize_account("codex", "br", "file", home)
    assert len(_events_of("materialize")) == 1


def test_materialize_check_emits_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    from agentos.agent import auth_registry as R
    from agentos.agent.materialization import materialize_account

    active = _seed_capture(_codex_payload(exp=2_000_000_000))
    R.set_active("codex", "br", "file", active)
    home = _codex_home(tmp_path, _codex_payload(exp=1_000_000_000))

    materialize_account("codex", "br", "file", home, check=True)
    assert _events_of("materialize") == []


# --- reader: read_recent_events -------------------------------------------


def test_read_recent_events_filters_limits_and_orders_newest_first(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    from agentos.agent.accounts_log import append_account_event, read_recent_events

    for i in range(3):
        append_account_event(event="rotate", provider="codex", account="br", method="file",
                             payload={"new_active": f"r{i}"})
    append_account_event(event="capture", provider="codex", account="br", method="file",
                         payload={"ref_id": "c0"})

    recent = read_recent_events(event="rotate", limit=2)
    assert [e["payload"]["new_active"] for e in recent] == ["r2", "r1"]  # newest-first, limited
    assert all(e["event"] == "rotate" for e in recent)

    # unfiltered returns the most-recent of any kind, newest-first
    any_recent = read_recent_events(limit=1)
    assert any_recent[0]["event"] == "capture"


def test_read_recent_events_spans_day_files_and_empty_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _env(monkeypatch, tmp_path)
    from agentos.agent.accounts_log import accounts_log_dir, read_recent_events

    assert read_recent_events(event="rotate") == []  # no log dir yet

    # two dated files; "last 3" must cross the day boundary
    log_dir = accounts_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)

    def _line(ref: str) -> str:
        return json.dumps({"event": "rotate", "provider": "codex", "account": "br",
                           "method": "file", "payload": {"new_active": ref}}) + "\n"

    (log_dir / "20260101.jsonl").write_text(_line("old1") + _line("old2"))
    (log_dir / "20260102.jsonl").write_text(_line("new1"))

    recent = read_recent_events(event="rotate", limit=3)
    assert [e["payload"]["new_active"] for e in recent] == ["new1", "old2", "old1"]
