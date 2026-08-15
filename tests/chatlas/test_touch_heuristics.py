# $kw: --from Chatlas.Session.Model.Tests --from Chat.Touched.Index
from __future__ import annotations

from tarav.chatlas.normalization.session_model.events import compute_event_hash
from tarav.chatlas.touch_heuristics import quote_touch_evidence_from_session_model


def _event(
    sequence: int,
    role: str,
    text: str,
    *,
    turn_id: str | None = None,
    visible: bool = True,
) -> dict[str, object]:
    event: dict[str, object] = {
        "event_address": f"{sequence:064x}",
        "sequence": sequence,
        "kind": "message",
        "producer": {"type": "human" if role == "user" else "assistant"},
        "payload": {"role": role, "content": [{"type": "text", "text": text}]},
        "surfaces": {"transcript": "visible" if visible else "hidden"},
        "timestamp": f"2026-08-14T10:00:{sequence:02d}.000Z",
        "annotations": {
            "normal_turn": {
                "id": turn_id or f"turn-{sequence}",
                "kind": role,
            }
        },
    }
    event["event_hash"] = compute_event_hash(event)
    return event


def _model(*events: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": 5,
        "session": {"identity_hash": "session-a"},
        "chat": {"events": list(events)},
    }


def test_exact_normalized_substring_returns_touch_evidence_and_original_spans() -> None:
    assistant = _event(
        1,
        "assistant",
        "The assistant proposes a stable sequence alignment strategy for quoted passages.",
    )
    user = _event(
        2,
        "user",
        "You said:\n> THE assistant proposes a stable sequence alignment strategy "
        "for quoted passages!\nNice.",
    )

    payload = quote_touch_evidence_from_session_model(
        _model(assistant, user),
        min_length=40,
        threshold=0.75,
        lookback=5,
    )

    assert payload["finding_count"] == 1
    finding = payload["findings"][0]
    assert finding["class"] == "Touch.Evidence"
    assert finding["heuristic"] == "quotes"
    assert finding["match_kind"] == "exact"
    assert finding["alignment_score"] == 1.0
    assert finding["predecessor_distance"] == 1
    assert finding["assistant_turn_ref"]["turn_id"] == "turn-1"
    assert finding["user_turn_ref"]["turn_id"] == "turn-2"
    assert finding["assistant_span"]["text"] == (
        "The assistant proposes a stable sequence alignment strategy for quoted passages"
    )
    assert finding["user_span"]["text"] == (
        "THE assistant proposes a stable sequence alignment strategy for quoted passages"
    )
    assert finding["normalized_aligned_text"] == {
        "assistant": "the assistant proposes a stable sequence alignment strategy for quoted passages",
        "user": "the assistant proposes a stable sequence alignment strategy for quoted passages",
    }


def test_fuzzy_local_alignment_tolerates_an_edited_word() -> None:
    payload = quote_touch_evidence_from_session_model(
        _model(
            _event(
                1,
                "assistant",
                "Use a bounded sequence alignment over visible assistant turns for reliable quote discovery",
            ),
            _event(
                2,
                "user",
                "I kept this: use a bounded local alignment over visible system turns "
                "for reliable quote discovery.",
            ),
        ),
        min_length=40,
        threshold=0.8,
        lookback=5,
    )

    assert payload["finding_count"] == 1
    finding = payload["findings"][0]
    assert finding["match_kind"] == "fuzzy"
    assert finding["alignment_score"] == 0.846154
    assert finding["normalized_aligned_text"]["assistant"].startswith(
        "use a bounded sequence alignment"
    )
    assert finding["normalized_aligned_text"]["user"].startswith(
        "use a bounded local alignment"
    )


def test_length_and_threshold_are_independent_gates() -> None:
    model = _model(
        _event(1, "assistant", "quoted phrase"),
        _event(2, "user", "quoted phrase"),
    )
    assert (
        quote_touch_evidence_from_session_model(
            model, min_length=20, threshold=0.5, lookback=1
        )["findings"]
        == []
    )

    fuzzy = _model(
        _event(1, "assistant", "alpha beta gamma delta epsilon zeta eta theta"),
        _event(2, "user", "alpha beta changed delta epsilon altered eta theta"),
    )
    assert (
        quote_touch_evidence_from_session_model(
            fuzzy, min_length=20, threshold=0.9, lookback=1
        )["findings"]
        == []
    )


def test_lookback_counts_visible_assistant_turns() -> None:
    quoted = "the oldest assistant explanation contains enough distinctive material"
    model = _model(
        _event(1, "assistant", quoted),
        _event(
            2,
            "assistant",
            "the middle assistant response is unrelated and sufficiently long",
        ),
        _event(
            3,
            "assistant",
            "the nearest assistant response is unrelated and sufficiently long",
        ),
        _event(4, "user", f"Returning to this: {quoted}"),
    )

    assert (
        quote_touch_evidence_from_session_model(
            model, min_length=30, threshold=0.75, lookback=2
        )["findings"]
        == []
    )
    payload = quote_touch_evidence_from_session_model(
        model, min_length=30, threshold=0.75, lookback=3
    )
    assert payload["finding_count"] == 1
    assert payload["findings"][0]["predecessor_distance"] == 3


def test_hidden_and_later_assistant_text_never_supplies_evidence() -> None:
    quote = "this repeated material is long enough to cross the quotation threshold"
    payload = quote_touch_evidence_from_session_model(
        _model(
            _event(1, "assistant", quote, visible=False),
            _event(2, "user", quote),
            _event(3, "assistant", quote),
        ),
        min_length=30,
        threshold=0.75,
        lookback=5,
    )
    assert payload["findings"] == []
