from __future__ import annotations

import argparse
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

from agentos.chatlas.index_query import chatlas_index_row_matches_logical


def _row(days_idle: float) -> dict[str, object]:
    stamp = datetime.now(timezone.utc) - timedelta(days=days_idle)
    return {
        "identity_hash": "a" * 64,
        "last_activity_at": stamp.isoformat().replace("+00:00", "Z"),
    }


def _matches(row: dict[str, object], **kwargs: object) -> bool:
    base: dict[str, object] = {
        "identity_hash": None,
        "project": None,
        "project_base": None,
        "providers": None,
        "session_id": None,
        "display_name": None,
        "extractable_only": False,
        "active_after": None,
    }
    base.update(kwargs)
    return chatlas_index_row_matches_logical(row, **base)  # type: ignore[arg-type]


def test_active_before_keeps_only_settled_rows() -> None:
    cutoff = (
        (datetime.now(timezone.utc) - timedelta(days=2))
        .isoformat()
        .replace("+00:00", "Z")
    )
    assert _matches(_row(5), active_before=cutoff) is True
    assert _matches(_row(0.5), active_before=cutoff) is False


def test_active_before_composes_with_active_after() -> None:
    now = datetime.now(timezone.utc)
    after = (now - timedelta(days=10)).isoformat().replace("+00:00", "Z")
    before = (now - timedelta(days=2)).isoformat().replace("+00:00", "Z")
    assert _matches(_row(5), active_after=after, active_before=before) is True
    assert _matches(_row(20), active_after=after, active_before=before) is False
    assert _matches(_row(1), active_after=after, active_before=before) is False


def test_active_before_drops_rows_without_a_usable_timestamp() -> None:
    cutoff = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    assert _matches({"last_activity_at": None}, active_before=cutoff) is False
    assert _matches({"last_activity_at": "not-a-time"}, active_before=cutoff) is False


def test_idle_for_flag_becomes_an_active_before_cutoff() -> None:
    from agentos.chatlas.commands import (
        _chatlas_query_selector_kwargs,
        register_chatlas_commands,
    )

    parser = argparse.ArgumentParser(prog="agentos")
    register_chatlas_commands(parser.add_subparsers(dest="cmd"))
    args = parser.parse_args(["chatlas", "query", "--idle-for", "2d"])
    kwargs = _chatlas_query_selector_kwargs(args)
    cutoff = kwargs["active_before"]
    assert isinstance(cutoff, str)
    parsed = datetime.fromisoformat(cutoff.replace("Z", "+00:00"))
    delta = (datetime.now(timezone.utc) - parsed).total_seconds()
    assert 2 * 86400 - 60 <= delta <= 2 * 86400 + 60

    bare = parser.parse_args(["chatlas", "query"])
    assert _chatlas_query_selector_kwargs(bare)["active_before"] is None


def test_idle_for_rejects_a_bad_duration() -> None:
    from agentos._core.errors import CliError
    from agentos.chatlas.commands import (
        _chatlas_query_selector_kwargs,
        register_chatlas_commands,
    )

    parser = argparse.ArgumentParser(prog="agentos")
    register_chatlas_commands(parser.add_subparsers(dest="cmd"))
    args = parser.parse_args(["chatlas", "query", "--idle-for", "banana"])
    with pytest.raises(CliError):
        _chatlas_query_selector_kwargs(args)


def test_run_produce_runs_sessions_concurrently_and_keeps_input_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agentos.chatlas import products

    started = threading.Barrier(3, timeout=5)
    order: list[str] = []
    lock = threading.Lock()

    def fake_run_one(**kwargs: object) -> dict[str, object]:
        row = kwargs["row"]
        assert isinstance(row, dict)
        name = str(row["identity_hash"])
        started.wait()  # deadlocks unless three run at once
        with lock:
            order.append(name)
        return {"identity_hash": name, "exit_code": 0}

    monkeypatch.setattr(products, "_run_product_for_row", fake_run_one)

    rows = [{"identity_hash": f"h{i}"} for i in range(3)]
    payload = products.chatlas_products_run_produce(
        product="zip-transcript-summary",
        provider="codex",
        rows=rows,
        concurrency=3,
    )
    assert payload["run_count"] == 3
    assert [run["identity_hash"] for run in payload["runs"]] == ["h0", "h1", "h2"]
    assert sorted(order) == ["h0", "h1", "h2"]


def test_run_produce_reports_failures_with_their_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agentos.chatlas import products

    def fake_run_one(**kwargs: object) -> dict[str, object]:
        row = kwargs["row"]
        assert isinstance(row, dict)
        name = str(row["identity_hash"])
        if name == "bad":
            return {
                "identity_hash": name,
                "exit_code": 1,
                "error": "agent exited non-zero",
            }
        return {"identity_hash": name, "exit_code": 0}

    monkeypatch.setattr(products, "_run_product_for_row", fake_run_one)

    payload = products.chatlas_products_run_produce(
        product="zip-transcript-summary",
        provider="codex",
        rows=[{"identity_hash": "good"}, {"identity_hash": "bad"}],
    )
    assert payload["status"] == "error"
    assert payload["failed_count"] == 1
    assert payload["failures"] == [
        {"identity_hash": "bad", "error": "agent exited non-zero"}
    ]


def test_run_produce_is_serial_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    from agentos.chatlas import products

    live = 0
    peak = 0
    lock = threading.Lock()

    def fake_run_one(**kwargs: object) -> dict[str, object]:
        nonlocal live, peak
        with lock:
            live += 1
            peak = max(peak, live)
        time.sleep(0.01)
        with lock:
            live -= 1
        return {"identity_hash": str(kwargs["row"]["identity_hash"]), "exit_code": 0}

    monkeypatch.setattr(products, "_run_product_for_row", fake_run_one)
    products.chatlas_products_run_produce(
        product="zip-transcript-summary",
        provider="codex",
        rows=[{"identity_hash": f"h{i}"} for i in range(4)],
    )
    assert peak == 1
