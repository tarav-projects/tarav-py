# $kw: ^test-event-query-refs --from Chatlas.Session.Model.Tests --from Session.Event.Tape --note [CT] scan and disposable SQLite backends agree on stable event addresses and public Event.Ref results ^c20260807-16u
from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

from agentos.chatlas import event_query
from agentos.chatlas.event_pattern import EventPattern
from agentos.chatlas.event_ref import event_ref
from agentos.chatlas.event_query import (
    NormalModelScanBackend,
    SQLiteCandidateBackend,
    corpus_fingerprint,
    query_event_models,
    query_turn_models,
    rebuild_sqlite_event_index,
)
from agentos.chatlas.normalization.session_model.events import compute_event_hash


def _event(sequence: int, role: str, text: str) -> dict[str, object]:
    event: dict[str, object] = {
        "event_address": f"{sequence:064x}",
        "sequence": sequence,
        "kind": "message",
        "producer": {"type": "human" if role == "user" else "assistant"},
        "payload": {"role": role, "content": [{"type": "text", "text": text}]},
        "timestamp": f"2026-07-28T10:00:{sequence:02d}.000Z",
        "annotations": {"normal_turn": {"id": f"turn-{sequence}", "kind": role}},
    }
    event["event_hash"] = compute_event_hash(event)
    return event


def _model(identity: str, approval: str = "::approve POI.Class") -> dict[str, object]:
    return {
        "schema_version": 5,
        "session": {"identity_hash": identity},
        "chat": {
            "events": [
                _event(1, "assistant", "candidate: POI.Class"),
                _event(2, "user", approval),
            ]
        },
    }


def _pattern() -> EventPattern:
    return EventPattern.from_dict(
        {
            "steps": [
                {"role": "assistant", "text_contains": "candidate:"},
                {"role": "user", "text_exact": "::approve POI.Class"},
            ]
        }
    )


def test_sqlite_and_scan_discover_the_same_coordinates(tmp_path: Path) -> None:
    models = {"session-a": _model("session-a")}
    fingerprint = corpus_fingerprint([{"identity_hash": "session-a", "version": 1}])
    database = tmp_path / "events.sqlite3"
    rebuild_sqlite_event_index(database, models, fingerprint=fingerprint)

    scan = NormalModelScanBackend(models)
    sqlite = SQLiteCandidateBackend(database, expected_fingerprint=fingerprint)

    assert sqlite.find_candidates(_pattern()) == scan.find_candidates(_pattern())


def test_sqlite_and_scan_agree_on_material_producer_and_time_predicates(
    tmp_path: Path,
) -> None:
    models = {"session-a": _model("session-a")}
    fingerprint = corpus_fingerprint([{"identity_hash": "session-a", "version": 1}])
    database = tmp_path / "events.sqlite3"
    rebuild_sqlite_event_index(database, models, fingerprint=fingerprint)
    pattern = EventPattern.from_dict(
        {
            "steps": [
                {
                    "role": "user",
                    "producer_type": "human",
                    "text_alphanumeric_contains": "approve, POI class!",
                    "text_regex": r"approve\s+POI\.Class",
                    "timestamp_after": "2026-07-28T10:00:01Z",
                    "timestamp_before": "2026-07-28T10:00:03Z",
                }
            ]
        }
    )

    scan = NormalModelScanBackend(models).find_candidates(pattern)
    sqlite = SQLiteCandidateBackend(
        database, expected_fingerprint=fingerprint
    ).find_candidates(pattern)

    assert sqlite == scan
    assert len(scan.candidates) == 1


def test_sqlite_and_scan_agree_on_normalized_turn_kind(tmp_path: Path) -> None:
    models = {"session-a": _model("session-a")}
    fingerprint = corpus_fingerprint([{"identity_hash": "session-a"}])
    database = tmp_path / "events.sqlite3"
    rebuild_sqlite_event_index(database, models, fingerprint=fingerprint)
    pattern = EventPattern.from_dict({"steps": [{"turn_kind": "user"}]})

    scan = NormalModelScanBackend(models).find_candidates(pattern)
    sqlite = SQLiteCandidateBackend(
        database, expected_fingerprint=fingerprint
    ).find_candidates(pattern)

    assert sqlite == scan
    assert len(scan.candidates) == 1


def test_turn_query_returns_authoritative_normal_turn_and_turn_ref(
    tmp_path: Path,
) -> None:
    model = _model("session-a")
    user_event = model["chat"]["events"][1]
    user_event["event_hash"] = "authoritative-hash"
    models = {"session-a": model}
    fingerprint = corpus_fingerprint([{"identity_hash": "session-a"}])
    database = tmp_path / "events.sqlite3"
    rebuild_sqlite_event_index(database, models, fingerprint=fingerprint)
    pattern = EventPattern.from_dict(
        {"steps": [{"role": "user", "text_contains": "approve"}]}
    )

    result = query_turn_models(
        models,
        pattern,
        requested_backend="sqlite",
        sqlite_database=database,
        corpus_fingerprint=fingerprint,
        sort="oldest",
        limit=10,
        detail="turn",
    )

    assert result["backend_used"] == "sqlite"
    assert result["match_count"] == 1
    turn = result["turns"][0]
    assert turn["session_identity"] == "session-a"
    assert turn["member_ref"] == "session-a:turn-2"
    assert turn["turn_ref"] == {
        "session": "session-a",
        "turn_id": "turn-2",
        "turn_hash": turn["turn_ref"]["turn_hash"],
        "at": user_event["timestamp"],
    }
    assert turn["normal_turn"] == {
        "turn_id": "turn-2",
        "events": [user_event],
    }


def test_turn_query_summary_identifies_exact_matching_event(tmp_path: Path) -> None:
    model = _model("session-a")
    user_event = model["chat"]["events"][1]
    models = {"session-a": model}
    fingerprint = corpus_fingerprint([{"identity_hash": "session-a"}])
    database = tmp_path / "events.sqlite3"
    rebuild_sqlite_event_index(database, models, fingerprint=fingerprint)

    result = query_turn_models(
        models,
        EventPattern.from_dict(
            {"steps": [{"role": "user", "text_contains": "approve"}]}
        ),
        requested_backend="scan",
        sqlite_database=database,
        corpus_fingerprint=fingerprint,
        detail="summary",
    )

    turn = result["turns"][0]
    assert turn["member_ref"] == "session-a:turn-2"
    assert "normal_turn" not in turn
    assert turn["matched_events"] == [
        {
            "event_ref": event_ref(user_event),
                "role": "user",
                "producer_type": "human",
                "turn_kind": "user",
                "text": "::approve POI.Class",
        }
    ]


def test_turn_query_summary_bounds_matching_text(tmp_path: Path) -> None:
    model = _model("session-a", approval="x" * 800)
    models = {"session-a": model}

    result = query_turn_models(
        models,
        EventPattern.from_dict(
            {"steps": [{"role": "user", "text_contains": "xxx"}]}
        ),
        requested_backend="scan",
        sqlite_database=tmp_path / "events.sqlite3",
        corpus_fingerprint="unused",
        detail="summary",
    )

    text = result["turns"][0]["matched_events"][0]["text"]
    assert len(text) == 500
    assert text.endswith("...")


def test_bounded_auto_turn_query_bypasses_sqlite(
    tmp_path: Path,
    monkeypatch,
) -> None:
    model = _model("session-a")
    rows = [{"identity_hash": "session-a"}]

    monkeypatch.setattr(
        event_query,
        "_load_session_models",
        lambda _rows, **_kwargs: {"session-a": model},
    )

    def fail_sqlite(*_args, **_kwargs):
        raise AssertionError("bounded auto query must not consult SQLite")

    monkeypatch.setattr(
        event_query.SQLiteCandidateBackend,
        "find_candidates",
        fail_sqlite,
    )

    result, models, candidate_count = event_query._query_selected_rows(
        rows,
        EventPattern.from_dict(
            {"steps": [{"role": "user", "text_contains": "approve"}]}
        ),
        requested_backend="auto",
        sqlite_database=tmp_path / "events.sqlite3",
        fingerprint="unused",
        chatlas_root=tmp_path,
    )

    assert result["backend_used"] == "scan"
    assert set(models) == {"session-a"}
    assert candidate_count == 1


def test_sqlite_turn_query_loads_only_candidate_normal_models(
    tmp_path: Path,
    monkeypatch,
) -> None:
    models = {
        "session-a": _model("session-a"),
        "session-b": _model("session-b", approval="unrelated text"),
    }
    rows = [
        {"identity_hash": "session-a"},
        {"identity_hash": "session-b"},
    ]
    fingerprint = corpus_fingerprint(rows)
    database = tmp_path / "events.sqlite3"
    rebuild_sqlite_event_index(database, models, fingerprint=fingerprint)
    loaded: list[str] = []

    def load(candidate_rows, **_kwargs):
        identities = [row["identity_hash"] for row in candidate_rows]
        loaded.extend(identities)
        return {identity: models[identity] for identity in identities}

    monkeypatch.setattr(event_query, "_load_session_models", load)
    pattern = EventPattern.from_dict(
        {
            "steps": [
                {
                    "role": "user",
                    "text_alphanumeric_contains": "approve POI.Class",
                }
            ]
        }
    )

    result, loaded_models, candidate_count = event_query._query_selected_rows(
        rows,
        pattern,
        requested_backend="sqlite",
        sqlite_database=database,
        fingerprint=fingerprint,
        chatlas_root=tmp_path,
    )

    assert loaded == ["session-a"]
    assert set(loaded_models) == {"session-a"}
    assert candidate_count == 1
    assert result["match_count"] == 1


def test_events_index_streams_models_into_sqlite(tmp_path: Path, monkeypatch) -> None:
    rows = [{"identity_hash": "session-a"}, {"identity_hash": "session-b"}]
    trace: list[str] = []

    monkeypatch.setattr(
        event_query,
        "load_chatlas_session_index_rows",
        lambda **_kwargs: SimpleNamespace(rows=rows),
    )

    def load_model(row, **_kwargs):
        identity = row["identity_hash"]
        trace.append(f"load:{identity}")
        return _model(identity)

    def visible_events(model):
        identity = model["session"]["identity_hash"]
        trace.append(f"consume:{identity}")
        return model["chat"]["events"]

    monkeypatch.setattr(event_query, "load_chatlas_session_model", load_model)
    monkeypatch.setattr(event_query, "visible_turn_events", visible_events)

    result = event_query.chatlas_events_index(chatlas_root=tmp_path)

    assert result["session_count"] == 2
    assert trace == [
        "load:session-a",
        "consume:session-a",
        "load:session-b",
        "consume:session-b",
    ]


def test_sqlite_false_positive_is_rejected_by_authoritative_model(
    tmp_path: Path,
) -> None:
    models = {"session-a": _model("session-a", approval="not approved")}
    fingerprint = corpus_fingerprint([{"identity_hash": "session-a"}])
    database = tmp_path / "events.sqlite3"
    rebuild_sqlite_event_index(database, models, fingerprint=fingerprint)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE turns SET text = ? WHERE role = 'user'",
            ("::approve POI.Class",),
        )

    result = query_event_models(
        models,
        _pattern(),
        requested_backend="sqlite",
        sqlite_database=database,
        corpus_fingerprint=fingerprint,
    )

    assert result["backend_used"] == "sqlite"
    assert result["matches"] == []


def test_stale_sqlite_falls_back_to_scan_without_false_negative(
    tmp_path: Path,
) -> None:
    models = {"session-a": _model("session-a")}
    database = tmp_path / "events.sqlite3"
    rebuild_sqlite_event_index(
        database,
        models,
        fingerprint=corpus_fingerprint([{"identity_hash": "session-a", "version": 1}]),
    )

    result = query_event_models(
        models,
        _pattern(),
        requested_backend="sqlite",
        sqlite_database=database,
        corpus_fingerprint=corpus_fingerprint(
            [{"identity_hash": "session-a", "version": 2}]
        ),
    )

    assert result["backend_used"] == "scan"
    assert result["fallback_reason"] == "sqlite index is stale or incomplete"
    assert result["matches"][0]["event_refs"] == [
        event_ref(models["session-a"]["chat"]["events"][0]),
        event_ref(models["session-a"]["chat"]["events"][1]),
    ]
    assert result["matches"][0]["events"][1]["payload"]["role"] == "user"
