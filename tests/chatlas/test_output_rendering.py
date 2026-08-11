from __future__ import annotations

import argparse
import json

import pytest

from agentos.chatlas.output import (
    add_chatlas_output_arguments,
    print_chatlas_output,
    render_payload_text,
)
from agentos.chatlas.time_interface import format_local_timestamp


def _parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="chatlas-test")
    add_chatlas_output_arguments(parser)
    return parser.parse_args(argv)


def test_output_defaults_to_text() -> None:
    assert _parse([]).output == "text"


def test_output_flags_select_their_mode() -> None:
    assert _parse(["--json"]).output == "json"
    assert _parse(["--text"]).output == "text"


def test_output_flags_are_mutually_exclusive() -> None:
    with pytest.raises(SystemExit):
        _parse(["--json", "--text"])


def test_json_output_is_byte_identical_to_the_shared_json_writer(
    capsys: pytest.CaptureFixture[str],
) -> None:
    payload = {"status": "ok", "count": 2, "rows": [{"b": 1, "a": 2}]}
    print_chatlas_output(payload, output="json")
    captured = capsys.readouterr().out
    assert captured == json.dumps(payload, indent=2, sort_keys=True) + "\n"


def test_text_output_uses_a_supplied_renderer(
    capsys: pytest.CaptureFixture[str],
) -> None:
    print_chatlas_output(
        {"anything": 1}, output="text", text_renderer=lambda _payload: "rendered"
    )
    assert capsys.readouterr().out == "rendered\n"


def test_json_output_ignores_a_supplied_renderer(
    capsys: pytest.CaptureFixture[str],
) -> None:
    print_chatlas_output(
        {"a": 1}, output="json", text_renderer=lambda _payload: "rendered"
    )
    assert "rendered" not in capsys.readouterr().out


def test_generic_renderer_prints_scalars_as_sorted_fields() -> None:
    rendered = render_payload_text({"status": "ok", "count": 2})
    assert rendered == "count: 2\nstatus: ok"


def test_generic_renderer_lowercases_booleans_and_marks_none() -> None:
    rendered = render_payload_text({"fresh": True, "stale": False, "warning": None})
    assert rendered == "fresh: true\nstale: false\nwarning: (none)"


def test_generic_renderer_indents_nested_objects() -> None:
    rendered = render_payload_text({"freshness": {"state": "stale", "matches": False}})
    assert rendered == "freshness:\n  matches: false\n  state: stale"


def test_generic_renderer_joins_short_scalar_lists() -> None:
    rendered = render_payload_text({"providers": ["codex", "claude-code"]})
    assert rendered == "providers: codex, claude-code"


def test_generic_renderer_blocks_lists_of_objects() -> None:
    rendered = render_payload_text(
        {"products": [{"name": "a", "input_view": "v"}, {"name": "b"}]}
    )
    assert rendered == (
        "products:\n"
        "  - input_view: v\n"
        "    name: a\n"
        "  - name: b"
    )


def test_generic_renderer_marks_empty_containers() -> None:
    rendered = render_payload_text({"rows": [], "detail": {}})
    assert rendered == "detail: (empty)\nrows: (none)"


def test_generic_renderer_blocks_multiline_strings() -> None:
    rendered = render_payload_text({"prompt": "first line\nsecond line"})
    assert rendered == "prompt:\n  first line\n  second line"


def test_generic_renderer_preserves_non_ascii_text() -> None:
    assert render_payload_text({"hint": "café — ok"}) == "hint: café — ok"


def test_generic_renderer_accepts_a_top_level_list() -> None:
    assert render_payload_text([{"a": 1}, {"a": 2}]) == "- a: 1\n- a: 2"


def test_generic_renderer_accepts_a_top_level_scalar() -> None:
    assert render_payload_text("done") == "done"


def test_generic_renderer_handles_a_realistic_product_payload() -> None:
    payload = {
        "status": "ok",
        "command": "chatlas products status",
        "product": {
            "name": "zip-transcript-summary",
            "state": "production_required",
            "artifact": None,
            "freshness": {"state": "missing"},
        },
    }
    rendered = render_payload_text(payload)
    assert "command: chatlas products status" in rendered
    assert "  name: zip-transcript-summary" in rendered
    assert "    state: missing" in rendered
    assert "{" not in rendered


def test_generic_renderer_localizes_timestamp_fields_only() -> None:
    stamp = "2026-08-03T10:00:00Z"
    rendered = render_payload_text(
        {
            "generated_at": stamp,
            "summary": stamp,
            "rows": [{"last_activity_at": stamp}],
        }
    )
    local_stamp = format_local_timestamp(stamp)
    assert f"generated_at: {local_stamp}" in rendered
    assert f"last_activity_at: {local_stamp}" in rendered
    assert f"summary: {stamp}" in rendered


def test_view_renderer_reads_zip_transcript_turns_as_a_conversation() -> None:
    from agentos.chatlas.inline import format_chatlas_view_text

    rendered = format_chatlas_view_text(
        {
            "class": "agentos_chatlas.zip_transcript",
            "view": "zip-transcript",
            "session": {"provider": "codex", "session_id": "abc"},
            "turns": [
                {"role": "user", "text": "do the thing"},
                {"role": "assistant", "text": "done"},
            ],
        }
    )
    assert "codex" in rendered
    assert "user:" in rendered
    assert "do the thing" in rendered
    assert "assistant:" in rendered
    assert "done" in rendered
    assert '"turns"' not in rendered


def test_view_renderer_reads_message_shaped_views() -> None:
    from agentos.chatlas.inline import format_chatlas_view_text

    rendered = format_chatlas_view_text(
        {
            "view": "transcript",
            "session": {"provider": "codex", "session_id": "abc"},
            "chat": {
                "messages": [
                    {
                        "role": "user",
                        "timestamp": "2026-08-03T10:00:00Z",
                        "content": [{"type": "text", "text": "hello there"}],
                    }
                ]
            },
        }
    )
    local_stamp = format_local_timestamp("2026-08-03T10:00:00Z")
    assert f"user  [{local_stamp}]:" in rendered
    assert "hello there" in rendered


def test_view_renderer_falls_back_for_model_shaped_views() -> None:
    from agentos.chatlas.inline import format_chatlas_view_text

    rendered = format_chatlas_view_text({"view": "events", "chat": {"events": []}})
    assert "view: events" in rendered


def test_query_renderer_lists_rows_with_a_count_line() -> None:
    from agentos.chatlas.query import format_chatlas_query_text

    rendered = format_chatlas_query_text(
        {
            "returned_row_count": 1,
            "query_matched_row_count": 4,
            "rows": [
                {
                    "identity_hash": "a" * 64,
                    "provider": "codex",
                    "session_id": "s-1",
                    "last_activity_at": "2026-08-03T10:00:00Z",
                    "project_path": "/tmp/p",
                    "summary": "a short summary",
                }
            ],
        }
    )
    assert "codex" in rendered
    assert "s-1" in rendered
    assert format_local_timestamp("2026-08-03T10:00:00Z") in rendered
    assert "2026-08-03T10:00:00Z" not in rendered
    assert "a short summary" in rendered
    assert "1 of 4" in rendered


def test_query_renderer_reports_an_empty_result() -> None:
    from agentos.chatlas.query import format_chatlas_query_text

    rendered = format_chatlas_query_text(
        {"returned_row_count": 0, "query_matched_row_count": 0, "rows": []}
    )
    assert "no sessions matched" in rendered.lower()


def test_stats_renderer_localizes_the_activity_range() -> None:
    from agentos.chatlas.index_stats import format_chatlas_index_stats_markdown

    oldest = "2026-08-03T10:00:00Z"
    latest = "2026-08-04T10:00:00Z"
    rendered = format_chatlas_index_stats_markdown(
        {"stats": {"oldest_active_at": oldest, "latest_active_at": latest}}
    )
    assert (
        "Updated range: "
        f"{format_local_timestamp(oldest)} .. {format_local_timestamp(latest)}"
    ) in rendered
    assert oldest not in rendered
    assert latest not in rendered


def test_turns_query_renderer_shows_matched_turn_text() -> None:
    from agentos.chatlas.event_query import format_chatlas_turns_query_text

    rendered = format_chatlas_turns_query_text(
        {
            "match_count": 1,
            "returned_turn_count": 1,
            "turns": [
                {
                    "member_ref": "abc:turn-1",
                    "matched_events": [
                        {"role": "user", "text": "the matched sentence"}
                    ],
                }
            ],
        }
    )
    assert "abc:turn-1" in rendered
    assert "the matched sentence" in rendered


def test_update_family_replaces_output_mode_with_explicit_flags() -> None:
    import argparse

    from agentos.chatlas.commands import register_chatlas_commands

    parser = argparse.ArgumentParser(prog="agentos")
    register_chatlas_commands(parser.add_subparsers(dest="cmd"))
    update = parser.parse_args(["chatlas", "index", "update"])
    assert update.output == "text"
    assert update.quiet is False
    assert parser.parse_args(["chatlas", "index", "update", "--json"]).output == "json"
    assert parser.parse_args(["chatlas", "index", "update", "--quiet"]).quiet is True
    with pytest.raises(SystemExit):
        parser.parse_args(["chatlas", "index", "update", "--output-mode", "json"])


def test_every_chatlas_leaf_command_offers_the_output_contract() -> None:
    import argparse

    from agentos.chatlas.commands import register_chatlas_commands

    parser = argparse.ArgumentParser(prog="agentos")
    register_chatlas_commands(parser.add_subparsers(dest="cmd"))

    missing: list[str] = []

    def walk(node: argparse.ArgumentParser, path: str) -> None:
        if "handler" in node._defaults:
            flags = {flag for action in node._actions for flag in action.option_strings}
            if not {"--json", "--text"} <= flags:
                missing.append(path)
        for action in node._actions:
            if isinstance(action, argparse._SubParsersAction):
                for name, child in action.choices.items():
                    walk(child, f"{path} {name}")

    walk(parser._subparsers._group_actions[0].choices["chatlas"], "chatlas")
    assert missing == []


def test_turns_query_exposes_normalized_turn_kind_without_human_sugar() -> None:
    import argparse

    from agentos.chatlas.commands import register_chatlas_commands

    parser = argparse.ArgumentParser(prog="agentos")
    register_chatlas_commands(parser.add_subparsers(dest="cmd"))
    parsed = parser.parse_args(
        ["chatlas", "turns", "query", "--turn-kind", "user"]
    )
    assert parsed.turn_kind == "user"
    with pytest.raises(SystemExit):
        parser.parse_args(["chatlas", "turns", "query", "--human"])
