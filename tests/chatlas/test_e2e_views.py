from __future__ import annotations

from pathlib import Path

import pytest

from tarav.cli.cli import main
from ._e2e_helpers import (
    _configure_chatlas,
    _isolate_chatlas,
    _inline_selection_events,
    _selection_fixture,
    _write_codex_rollout,
    _write_codex_rollout_script,
)
from ._helpers import captured_json


def test_chatlas_views_are_named_disposable_projections(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment, codex_home = _isolate_chatlas(monkeypatch, tmp_path)
    home = environment.home
    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    _write_codex_rollout(
        codex_home / "sessions" / "2026" / "03" / "25" / f"rollout-{session_id}.jsonl",
        session_id=session_id,
    )
    _configure_chatlas(environment, codex_home)
    assert (
        main(
            [
                "chatlas",
                "index",
                "update",
                "--provider",
                "codex",
                "--json",
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert main(["chatlas", "session-views", "list", "--json"]) == 0
    assert {"full", "transcript", "user", "replay", "events", "zip-transcript"} == {
        view["name"] for view in captured_json(capsys)["views"]
    }

    assert (
        main(
            [
                "chatlas",
                "session-views",
                "get",
                "--view",
                "zip-transcript",
                "--session-id",
                session_id,
                "--json",
            ]
        )
        == 0
    )
    payload = captured_json(capsys)
    assert payload["class"] == "agentos_chatlas.zip_transcript"
    assert payload["view"] == "zip-transcript"
    assert payload["turns"]
    assert not (home / "Documents" / "chatlas" / "views").exists()


def test_chatlas_views_inline_ranges_zip_transcript_turns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment, codex_home = _isolate_chatlas(monkeypatch, tmp_path)
    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    _write_codex_rollout(
        codex_home / "sessions" / "2026" / "03" / "25" / f"rollout-{session_id}.jsonl",
        session_id=session_id,
        messages=[
            ("user", "turn zero"),
            ("assistant", "turn one"),
            ("user", "turn two"),
            ("assistant", "turn three"),
        ],
    )
    _configure_chatlas(environment, codex_home)
    assert (
        main(
            [
                "chatlas",
                "index",
                "update",
                "--provider",
                "codex",
                "--json",
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert (
        main(
            [
                "chatlas",
                "session-views",
                "get",
                "--session-id",
                session_id,
                "--view",
                "zip-transcript",
                "--range",
                "1:3",
                "--json",
            ]
        )
        == 0
    )
    payload = captured_json(capsys)

    assert payload["class"] == "agentos_chatlas.zip_transcript"
    assert payload["turns"] == [
        {"role": "assistant", "text": "turn one"},
        {"role": "user", "text": "turn two"},
    ]
    assert payload["range"] == {
        "target": "turns",
        "start": 1,
        "stop": 3,
        "total": 4,
    }


def test_chatlas_views_inline_events_clears_non_event_payloads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment, codex_home = _isolate_chatlas(monkeypatch, tmp_path)
    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    _write_codex_rollout(
        codex_home / "sessions" / "2026" / "03" / "25" / f"rollout-{session_id}.jsonl",
        session_id=session_id,
    )
    _configure_chatlas(environment, codex_home)
    assert (
        main(
            [
                "chatlas",
                "index",
                "update",
                "--provider",
                "codex",
                "--json",
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert (
        main(
            [
                "chatlas",
                "session-views",
                "get",
                "--session-id",
                session_id,
                "--view",
                "events",
                "--json",
            ]
        )
        == 0
    )
    payload = captured_json(capsys)

    chat = payload["chat"]
    assert payload["view"] == "events"
    assert len(chat["events"]) >= 2
    assert [
        event["kind"] for event in chat["events"] if event["kind"] == "message"
    ] == [
        "message",
        "message",
    ]
    assert chat["messages"] == []
    assert chat["model_runs"] == []
    assert chat["tool_invocations"] == []
    assert chat["usage"] == []


def test_chatlas_views_inline_range_errors_are_reported(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment, codex_home = _isolate_chatlas(monkeypatch, tmp_path)
    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675fd5"
    _write_codex_rollout(
        codex_home / "sessions" / "2026" / "03" / "25" / f"rollout-{session_id}.jsonl",
        session_id=session_id,
    )
    _configure_chatlas(environment, codex_home)
    assert (
        main(
            [
                "chatlas",
                "index",
                "update",
                "--provider",
                "codex",
                "--json",
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert (
        main(
            [
                "chatlas",
                "session-views",
                "get",
                "--session-id",
                session_id,
                "--view",
                "zip-transcript",
                "--range",
                "1:2:3",
                "--json",
            ]
        )
        == 1
    )
    assert "step syntax is not supported" in capsys.readouterr().err

    assert (
        main(
            [
                "chatlas",
                "session-views",
                "get",
                "--session-id",
                session_id,
                "--view",
                "full",
                "--range",
                "0:1",
                "--json",
            ]
        )
        == 1
    )
    assert "--range is not supported for view 'full'" in capsys.readouterr().err


def _event_texts(events: list[dict[str, object]]) -> list[str]:
    texts: list[str] = []
    for event in events:
        payload = event.get("payload")
        collected: list[str] = []
        _collect_payload_texts(payload, collected)
        texts.append(" ".join(collected))
    return texts


def _collect_payload_texts(value: object, out: list[str]) -> None:
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, dict):
        for item in value.values():
            _collect_payload_texts(item, out)
    elif isinstance(value, list):
        for item in value:
            _collect_payload_texts(item, out)


def test_chatlas_views_inline_contains_filters_events(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    session_id = _selection_fixture(tmp_path, monkeypatch, capsys)
    events = _inline_selection_events(
        capsys,
        [
            "chatlas",
            "session-views",
            "get",
            "--session-id",
            session_id,
            "--view",
            "events",
            "--contains",
            "beta question",
        ],
    )
    assert len(events) == 1
    assert "beta question" in _event_texts(events)[0]


def test_chatlas_views_inline_role_filters_message_events(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    session_id = _selection_fixture(tmp_path, monkeypatch, capsys)
    events = _inline_selection_events(
        capsys,
        [
            "chatlas",
            "session-views",
            "get",
            "--session-id",
            session_id,
            "--view",
            "events",
            "--role",
            "user",
        ],
    )
    texts = _event_texts(events)
    assert len(events) == 2
    assert any("alpha question" in text for text in texts)
    assert any("beta question" in text for text in texts)


def test_chatlas_views_inline_around_orders_chronologically(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    session_id = _selection_fixture(tmp_path, monkeypatch, capsys)
    events = _inline_selection_events(
        capsys,
        [
            "chatlas",
            "session-views",
            "get",
            "--session-id",
            session_id,
            "--view",
            "events",
            "--around",
            "2026-03-08T01:09:04Z",
        ],
    )
    timestamps = [str(event["timestamp"]) for event in events]
    assert timestamps == sorted(timestamps)
    assert any(value.startswith("2026-03-08T01:09:04") for value in timestamps)


def test_chatlas_views_inline_radius_counts_filter_surviving_events(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    environment, codex_home = _isolate_chatlas(monkeypatch, tmp_path)
    session_id = "019ccafa-7835-7fc3-ac17-0e0a0f675bbb"
    _write_codex_rollout_script(
        codex_home / "sessions" / "2026" / "03" / "08" / f"rollout-{session_id}.jsonl",
        session_id=session_id,
        script=[
            ("user", "u1 opening"),
            ("assistant", "a1 proposal"),
            *[("tool", f"noise-{index}") for index in range(10)],
            ("user", "u2 approval"),
            ("assistant", "a2 landed"),
        ],
    )
    _configure_chatlas(environment, codex_home)
    assert (
        main(
            [
                "chatlas",
                "index",
                "update",
                "--provider",
                "codex",
                "--json",
            ]
        )
        == 0
    )
    capsys.readouterr()
    approval_timestamp = "2026-03-08T01:09:14.000Z"
    events = _inline_selection_events(
        capsys,
        [
            "chatlas",
            "session-views",
            "get",
            "--session-id",
            session_id,
            "--around",
            approval_timestamp,
            "--radius",
            "1",
            "--filter",
            "turns",
        ],
    )
    texts = _event_texts(events)
    assert len(events) == 3
    assert "a1 proposal" in texts[0]
    assert "u2 approval" in texts[1]
    assert "a2 landed" in texts[2]


def test_chatlas_views_inline_around_radius_window_is_chronological(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    session_id = _selection_fixture(tmp_path, monkeypatch, capsys)
    events = _inline_selection_events(
        capsys,
        [
            "chatlas",
            "session-views",
            "get",
            "--session-id",
            session_id,
            "--view",
            "events",
            "--around",
            "2026-03-08T01:09:04Z",
            "--radius",
            "1",
        ],
    )
    timestamps = [str(event["timestamp"]) for event in events]
    assert len(events) == 3
    assert timestamps == sorted(timestamps)
    assert timestamps[1].startswith("2026-03-08T01:09:04")


def test_chatlas_views_inline_selection_filters_compose(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    session_id = _selection_fixture(tmp_path, monkeypatch, capsys)
    events = _inline_selection_events(
        capsys,
        [
            "chatlas",
            "session-views",
            "get",
            "--session-id",
            session_id,
            "--view",
            "events",
            "--contains",
            "alpha",
            "--role",
            "user",
        ],
    )
    assert len(events) == 1
    assert "alpha question" in _event_texts(events)[0]


def test_chatlas_views_inline_selection_empty_result_is_well_formed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    session_id = _selection_fixture(tmp_path, monkeypatch, capsys)
    events = _inline_selection_events(
        capsys,
        [
            "chatlas",
            "session-views",
            "get",
            "--session-id",
            session_id,
            "--view",
            "events",
            "--contains",
            "zzz-no-match",
        ],
    )
    assert events == []


def test_chatlas_views_inline_explicit_full_with_selection_still_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    session_id = _selection_fixture(tmp_path, monkeypatch, capsys)
    assert (
        main(
            [
                "chatlas",
                "session-views",
                "get",
                "--session-id",
                session_id,
                "--view",
                "full",
                "--contains",
                "alpha",
                "--json",
            ]
        )
        == 1
    )
    assert "projected view" in capsys.readouterr().err


def test_chatlas_views_inline_filter_slim_strips_plumbing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    session_id = _selection_fixture(tmp_path, monkeypatch, capsys)
    assert (
        main(
            [
                "chatlas",
                "session-views",
                "get",
                "--session-id",
                session_id,
                "--view",
                "events",
                "--filter",
                "slim",
                "--json",
            ]
        )
        == 0
    )
    payload = captured_json(capsys)
    assert "normalization" not in payload
    assert "sources" not in payload
    events = payload["chat"]["events"]
    assert events
    for event in events:
        assert not (_SLIM_EVENT_DROPPED & set(event))
        assert "timestamp" in event and "payload" in event


def test_chatlas_views_inline_filter_messages_keeps_only_message_events(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    session_id = _selection_fixture(tmp_path, monkeypatch, capsys)
    assert (
        main(
            [
                "chatlas",
                "session-views",
                "get",
                "--session-id",
                session_id,
                "--view",
                "events",
                "--filter",
                "messages",
                "--json",
            ]
        )
        == 0
    )
    payload = captured_json(capsys)
    events = payload["chat"]["events"]
    assert events
    assert all(event["kind"] == "message" for event in events)
    assert len(payload["chat"]["messages"]) == len(events)


def test_chatlas_views_inline_filter_turns_equals_messages_then_slim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    session_id = _selection_fixture(tmp_path, monkeypatch, capsys)
    base = [
        "chatlas",
        "session-views",
        "get",
        "--session-id",
        session_id,
        "--view",
        "events",
    ]
    assert main(base + ["--filter", "turns", "--json"]) == 0
    turns_payload = captured_json(capsys)
    assert main(base + ["--filter", "messages", "--filter", "slim", "--json"]) == 0
    composed_payload = captured_json(capsys)
    assert turns_payload == composed_payload


def test_chatlas_views_inline_unknown_filter_errors_listing_names(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    session_id = _selection_fixture(tmp_path, monkeypatch, capsys)
    assert (
        main(
            [
                "chatlas",
                "session-views",
                "get",
                "--session-id",
                session_id,
                "--view",
                "events",
                "--filter",
                "nonsense",
                "--json",
            ]
        )
        == 1
    )
    err = capsys.readouterr().err
    assert "nonsense" in err
    assert "slim" in err and "messages" in err and "turns" in err


_SLIM_EVENT_DROPPED = {
    "native",
    "source_refs",
    "lineage",
    "producer",
    "surfaces",
    "model_run_ref",
}
