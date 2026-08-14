from __future__ import annotations

import json
from pathlib import Path

from tarav.chatlas.ping import chatlas_ping, ping_state_path
from tarav.chatlas.time_interface import format_local_timestamp


def _run_ping(tmp_path: Path, *, query_fn, lines=2, rounds=2, **kwargs):
    updates: list[dict] = []

    def update_fn(**update_kwargs):
        updates.append(update_kwargs)
        return {}

    payload = chatlas_ping(
        lines=lines,
        interval_seconds=0.0,
        rounds=rounds,
        window_seconds=300,
        chatlas_root=tmp_path,
        update_fn=update_fn,
        query_fn=query_fn,
        sleep=lambda _seconds: None,
        **kwargs,
    )
    return payload, updates


def _no_match(**_kwargs):
    return {"rows": [], "returned_row_count": 0}


def test_ping_no_visibility_leaves_pending_state(tmp_path, capsys):
    payload, updates = _run_ping(tmp_path, query_fn=_no_match)

    assert payload["self_visible"] is False
    assert payload["previous_resolved"] == []
    assert payload["pending_count"] == 4  # 2 lines x 2 rounds
    assert len(updates) == 2  # one update per round

    state = json.loads(ping_state_path(tmp_path).read_text())
    assert len(state["pending"]) == 4
    for record in state["pending"]:
        assert record["run_id"] == payload["run_id"]

    emitted = capsys.readouterr().out
    for record in state["pending"]:
        assert record["marker"] in emitted
        assert format_local_timestamp(record["emitted_at"]) in emitted


def test_ping_resolves_previous_run_markers(tmp_path):
    first, _ = _run_ping(tmp_path, query_fn=_no_match)

    def match_first_run(*, tool_contains, **_kwargs):
        marker = tool_contains[0]
        if first["run_id"] in marker:
            return {
                "rows": [{"session_id": "S1", "identity_hash": "H1"}],
                "returned_row_count": 1,
            }
        return {"rows": [], "returned_row_count": 0}

    second, _ = _run_ping(tmp_path, query_fn=match_first_run, rounds=1)

    resolved = second["previous_resolved"]
    assert len(resolved) == 4
    for entry in resolved:
        assert entry["run_id"] == first["run_id"]
        assert entry["session_id"] == "S1"
        assert entry["latency_seconds"] >= 0

    state = json.loads(ping_state_path(tmp_path).read_text())
    pending_run_ids = {record["run_id"] for record in state["pending"]}
    assert pending_run_ids == {second["run_id"]}


def test_ping_sees_own_markers(tmp_path):
    def match_everything(**_kwargs):
        return {
            "rows": [{"session_id": "SELF", "identity_hash": "HSELF"}],
            "returned_row_count": 1,
        }

    payload, _ = _run_ping(tmp_path, query_fn=match_everything, rounds=1)

    assert payload["self_visible"] is True
    assert all(m["session_id"] == "SELF" for m in payload["self_resolved"])
    state = json.loads(ping_state_path(tmp_path).read_text())
    assert state["pending"] == []
