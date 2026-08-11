from __future__ import annotations

import argparse
import json
from datetime import timezone
from zoneinfo import ZoneInfo

import pytest

from agentos._core.errors import CliError
from agentos.chatlas.time_interface import (
    format_local_timestamp,
    is_timestamp_field,
    normalize_cli_event_pattern_timestamps,
    normalize_cli_timestamp,
    parse_interface_timestamp,
)


HAVANA = ZoneInfo("America/Havana")


def test_naive_cli_timestamp_is_interpreted_in_local_timezone() -> None:
    assert normalize_cli_timestamp(
        "2026-08-07T12:00:00",
        field="--after",
        local_timezone=HAVANA,
    ) == "2026-08-07T16:00:00Z"


def test_explicit_cli_timestamp_keeps_its_declared_timezone_meaning() -> None:
    assert normalize_cli_timestamp(
        "2026-08-07T12:00:00Z",
        field="--after",
        local_timezone=HAVANA,
    ) == "2026-08-07T12:00:00Z"
    assert normalize_cli_timestamp(
        "2026-08-07T12:00:00+02:00",
        field="--after",
        local_timezone=HAVANA,
    ) == "2026-08-07T10:00:00Z"


def test_recents_since_date_uses_the_shared_cli_time_boundary() -> None:
    from agentos.chatlas.recents import parse_since_date

    assert parse_since_date("2026-08-07T12:00:00+02:00").isoformat() == (
        "2026-08-07T10:00:00+00:00"
    )


def test_invalid_cli_timestamp_names_the_flag() -> None:
    with pytest.raises(CliError, match="--around"):
        normalize_cli_timestamp("not-a-time", field="--around")


def test_event_pattern_cli_normalization_is_recursive_and_non_mutating() -> None:
    payload = {
        "steps": [
            {
                "timestamp_after": "2026-08-07T12:00:00",
                "next_turn": {
                    "timestamp_before": "2026-08-07T13:00:00Z",
                    "text_contains": "2026-08-07T12:00:00",
                },
            }
        ]
    }

    normalized = normalize_cli_event_pattern_timestamps(
        payload, local_timezone=HAVANA
    )

    assert normalized["steps"][0]["timestamp_after"] == "2026-08-07T16:00:00Z"
    assert (
        normalized["steps"][0]["next_turn"]["timestamp_before"]
        == "2026-08-07T13:00:00Z"
    )
    assert (
        normalized["steps"][0]["next_turn"]["text_contains"]
        == "2026-08-07T12:00:00"
    )
    assert payload["steps"][0]["timestamp_after"] == "2026-08-07T12:00:00"


def test_canonical_timestamp_formats_as_explicit_local_time() -> None:
    assert format_local_timestamp(
        "2026-08-07T16:00:00Z", local_timezone=HAVANA
    ) == "2026-08-07T12:00:00-04:00"
    assert format_local_timestamp(
        "2026-08-07T16:00:00Z",
        local_timezone=HAVANA,
        display_format="%Y-%m-%d %H:%M",
    ) == "2026-08-07 12:00"


def test_interface_parser_treats_naive_canonical_data_as_utc() -> None:
    parsed = parse_interface_timestamp("2026-08-07T16:00:00")
    assert parsed is not None
    assert parsed.tzinfo == timezone.utc


@pytest.mark.parametrize(
    "field",
    ["timestamp", "last_activity_at", "cutoff_timestamp", "mtime", "at"],
)
def test_timestamp_field_detection(field: str) -> None:
    assert is_timestamp_field(field) is True


def test_timestamp_field_detection_does_not_convert_arbitrary_text() -> None:
    assert is_timestamp_field("summary") is False
    assert is_timestamp_field("created_at_hint") is False


def test_query_selector_normalizes_explicit_offset_at_cli_boundary() -> None:
    from agentos.chatlas.commands import _chatlas_query_selector_kwargs

    args = argparse.Namespace(
        uri=None,
        identity_hash=None,
        project=None,
        project_base=None,
        providers=None,
        session_id=None,
        display_name=None,
        extractable=False,
        active_after="2026-08-07T12:00:00+02:00",
        idle_for=None,
        sort="newest",
        limit=None,
        scan_limit=None,
        raw_contains=None,
        user_contains=None,
        assistant_contains=None,
        message_contains=None,
        file_read=None,
        file_write=None,
        file_touched=None,
        tool_contains=None,
        tool_name=None,
        min_user_turns=None,
        tags=None,
        without_tags=None,
    )

    assert _chatlas_query_selector_kwargs(args)["active_after"] == (
        "2026-08-07T10:00:00Z"
    )


def test_event_pattern_timestamp_is_normalized_at_cli_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from agentos.chatlas import _command_support

    captured: dict[str, object] = {}

    def fake_query(pattern: object, **kwargs: object) -> dict[str, object]:
        captured["pattern"] = pattern
        captured["kwargs"] = kwargs
        return {"status": "ok"}

    monkeypatch.setattr(_command_support, "chatlas_events_query", fake_query)
    args = argparse.Namespace(
        pattern_json=json.dumps(
            {"event": {"timestamp_after": "2026-08-07T12:00:00+02:00"}}
        ),
        backend="scan",
        uri=None,
        identity_hash=None,
        project=None,
        project_base=None,
        providers=None,
        instances=None,
        provider_instance_fingerprint=None,
        session_id=None,
        display_name=None,
        extractable=False,
        active_after=None,
        sort="lexical",
        limit=None,
        output="json",
    )

    assert _command_support._cmd_chatlas_events_query(args) == 0
    assert captured["pattern"] == {
        "event": {"timestamp_after": "2026-08-07T10:00:00Z"}
    }
