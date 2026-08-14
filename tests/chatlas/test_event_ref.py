"""Stable-place `Event.Ref` contract (Impl.Req 520, Slices 1-3)."""

from __future__ import annotations

import pytest

from tarav.chatlas.event_ref import (
    EVENT_HASH_MIN_CHARS,
    EVENT_REF_SCHEMA,
    EventRefOutcome,
    event_ref,
    format_event_ref,
    parse_event_ref,
    resolve_event_ref,
)

FULL = "caa55f90bec3cf7ecfe5f7887a4cf06fe5c4db4b9fdf792f2f02ac0d3431df38"
ADDRESS = "a" * 64


def _event(digest: str, sequence: int, *, address: str | None = None) -> dict:
    return {
        "event_address": address or f"{sequence:064x}",
        "event_hash": digest,
        "sequence": sequence,
        "kind": "message",
        "timestamp": f"2026-07-28T10:00:{sequence:02d}.000Z",
    }


def _tape(*digests: str) -> list[dict]:
    return [_event(d, i + 1) for i, d in enumerate(digests)]


def _d(seed: str) -> str:
    return (seed * 64)[:64]


def test_ref_is_an_object_with_address_and_assertion_not_position():
    ref = event_ref(_event(FULL, 9, address=ADDRESS))
    assert ref == {
        "event_address": ADDRESS,
        "event_hash": FULL[:EVENT_HASH_MIN_CHARS],
    }
    assert "sequence" not in ref


def test_optional_fields_are_opt_in():
    event = _event(FULL, 1, address=ADDRESS)
    ref = event_ref(event, session="s" * 64, with_timestamp=True, with_schema=True)
    assert ref["schema"] == EVENT_REF_SCHEMA
    assert ref["session"] == "s" * 64
    assert ref["at"] == event["timestamp"]


def test_hash_length_is_the_storer_s_choice_with_a_floor():
    event = _event(FULL, 1)
    assert event_ref(event, hash_chars=64)["event_hash"] == FULL
    assert len(event_ref(event)["event_hash"]) == EVENT_HASH_MIN_CHARS
    with pytest.raises(ValueError):
        event_ref(event, hash_chars=4)


def test_string_form_is_address_then_assertion_and_round_trips():
    ref = event_ref(_event(FULL, 1, address=ADDRESS), hash_chars=64)
    text = format_event_ref(ref)
    assert text == f"{ADDRESS}:{FULL}"
    assert parse_event_ref(text) == ref


def test_malformed_sugar_and_refs_are_rejected():
    for bad in ("", "abc", f"{ADDRESS}:", f":{FULL}", "short:short"):
        with pytest.raises(ValueError):
            parse_event_ref(bad)
    with pytest.raises(ValueError):
        resolve_event_ref(_tape(FULL), {"event_hash": FULL})


def test_matching_address_and_assertion_is_matched():
    tape = _tape(_d("a"), _d("b"), _d("c"))
    result = resolve_event_ref(tape, event_ref(tape[1]))
    assert result.outcome is EventRefOutcome.MATCHED
    assert result.event is tape[1]
    assert result.finding is None


def test_same_address_with_changed_content_is_amended():
    original = _event(_d("a"), 1, address=ADDRESS)
    ref = event_ref(original)
    amended = _event(_d("b"), 17, address=ADDRESS)
    result = resolve_event_ref([amended], ref)
    assert result.outcome is EventRefOutcome.AMENDED
    assert result.event is amended
    assert result.finding is not None


def test_missing_address_is_missing_even_when_content_moved_elsewhere():
    original = _event(_d("a"), 1, address=ADDRESS)
    same_content_new_place = _event(_d("a"), 3, address="b" * 64)
    result = resolve_event_ref([same_content_new_place], event_ref(original))
    assert result.outcome is EventRefOutcome.MISSING
    assert result.event is None


def test_resolution_mutates_neither_tape_nor_reference():
    tape = [_event(_d("b"), 2, address=ADDRESS)]
    before = [dict(event) for event in tape]
    ref = {"event_address": ADDRESS, "event_hash": _d("a")[:16]}
    ref_before = dict(ref)
    resolve_event_ref(tape, ref)
    assert tape == before and ref == ref_before


def test_event_without_address_cannot_be_referenced():
    event = {"sequence": 1, "event_hash": FULL}
    with pytest.raises(ValueError, match="event_address"):
        event_ref(event)
