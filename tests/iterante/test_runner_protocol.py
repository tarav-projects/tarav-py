"""Tests for the runner I/O wire protocol (owned by `_runner`)."""

import json

from agentos.iterante._runner import FRAME_SENTINEL, error_line, frame_line, parse_error


def test_error_line_roundtrips_through_parse_error():
    assert parse_error(error_line("boom")) == "boom"


def test_parse_error_tolerates_surrounding_whitespace():
    assert parse_error("  " + error_line("boom") + "\n") == "boom"


def test_parse_error_falls_back_on_non_json():
    assert parse_error("not json at all") == "not json at all"


def test_frame_line_is_sentinel_prefixed_and_roundtrips():
    line = frame_line({"a": 1, "b": "x"})
    assert line.startswith(FRAME_SENTINEL)
    assert line.endswith("\n")
    assert json.loads(line[len(FRAME_SENTINEL):]) == {"a": 1, "b": "x"}
