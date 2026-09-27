from __future__ import annotations

import json

from tarav.cli.cli import build_parser, main
from tarav.l1.chatlas.rendering import (
    INLINED_CAPTURE_MARKDOWN_RENDERER,
    TURN_LEDGER_RENDERER,
)


def _event_ref() -> dict[str, str]:
    return {"event_address": "4" * 64, "event_hash": "5" * 64}


def _event() -> dict[str, object]:
    return {
        "type": "User.Event",
        **_event_ref(),
        "started_at": "2026-09-20T00:00:00Z",
        "origin": "user",
        "observations": [
            {
                "observed_at": "2026-09-20T00:00:00Z",
                "source_ref": {
                    "source_id": "source-one",
                    "record_index": 1,
                    "line": 1,
                },
            }
        ],
        "opaque_payload_hash": "6" * 64,
    }


def test_chatlas_help_exposes_current_commands() -> None:
    parser = build_parser()
    chatlas = next(
        action.choices["chatlas"]
        for action in parser._actions
        if hasattr(action, "choices") and action.choices and "chatlas" in action.choices
    )
    help_text = chatlas.format_help()

    for command in (
        "update",
        "current-session",
        "index",
        "raw",
        "normal-model",
        "query",
        "render",
    ):
        assert command in help_text
    for removed in ("recents", "products", "anchory", "views", "events"):
        assert removed not in help_text


def test_query_and_default_render_share_query_execution_and_output(
    monkeypatch, capsys
) -> None:
    calls: list[tuple[str, ...]] = []

    class Reader:
        def model_header(self):
            return {
                "session": {
                    "provider": "codex",
                    "session_id": "session-one",
                    "identity_hash": "0" * 64,
                }
            }

        def iter_turns(self):
            calls.append(("turns",))
            yield {
                "type": "Chat.Turn",
                "turn_address": "1" * 64,
                "turn_hash": "a" * 64,
                "side": "user",
                "event_refs": [
                    {"event_address": "4" * 64, "event_hash": "5" * 64}
                ],
                "message_refs": [
                    {
                        "message_address": "2" * 64,
                        "message_hash": "3" * 64,
                    }
                ],
            }

        def iter_messages(self):
            calls.append(("messages",))
            yield {
                "type": "Chat.Message",
                "message_address": "2" * 64,
                "message_hash": "3" * 64,
                "side": "user",
                "event_refs": [
                    {"event_address": "4" * 64, "event_hash": "5" * 64}
                ],
                "text": "selected text",
            }

        def iter_events(self):
            calls.append(("events",))
            yield {
                "type": "User.Event",
                "event_address": "4" * 64,
                "event_hash": "5" * 64,
                "started_at": "2026-09-20T00:00:00Z",
                "origin": "user",
                "observations": [
                    {
                        "observed_at": "2026-09-20T00:00:00Z",
                        "source_ref": {
                            "source_id": "source-one",
                            "record_index": 1,
                            "line": 1,
                        },
                    }
                ],
                "opaque_payload_hash": "6" * 64,
            }

    monkeypatch.setattr(
        "tarav.l1.chatlas.commands.provide_normal_model_reader", lambda **_: Reader()
    )
    argv = ["--identity-hash", "0" * 64, "--turn-hash-prefix", "a" * 8]

    assert main(["chatlas", "query", *argv]) == 0
    queried = capsys.readouterr().out
    assert main(["chatlas", "render", *argv]) == 0
    rendered = capsys.readouterr().out

    assert queried == rendered
    assert "selected text" in queried
    assert calls == [
        ("turns",),
        ("messages",),
        ("events",),
        ("turns",),
        ("messages",),
        ("events",),
    ]


def test_current_session_reports_verified_codex_and_claude_context(
    monkeypatch, capsys
) -> None:
    monkeypatch.setenv("CODEX_THREAD_ID", "codex-session")
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)

    assert main(["chatlas", "current-session", "--provider", "codex", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "provider": "codex",
        "session_id": "codex-session",
    }

    monkeypatch.delenv("CODEX_THREAD_ID")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "claude-session")

    assert (
        main(
            [
                "chatlas",
                "current-session",
                "--provider",
                "claude-code",
                "--json",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out) == {
        "provider": "claude-code",
        "session_id": "claude-session",
    }


def test_current_session_requires_unambiguous_verified_context(
    monkeypatch, capsys
) -> None:
    monkeypatch.setenv("CODEX_THREAD_ID", "codex-session")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "claude-session")

    assert main(["chatlas", "current-session"]) == 1
    assert "ambiguous" in capsys.readouterr().err


def test_render_selects_a_registered_renderer_and_passes_options(
    monkeypatch, capsys
) -> None:
    from tarav.l1.chatlas.rendering import ChatlasRenderer, register_renderer

    class Reader:
        def model_header(self):
            return {"session": {"session_id": "session-one"}}

        def iter_turns(self):
            yield {
                "type": "Chat.Turn",
                "turn_address": "1" * 64,
                "turn_hash": "a" * 64,
                "side": "user",
                "event_refs": [_event_ref()],
                "message_refs": [],
            }

        def iter_messages(self):
            return iter(())

        def iter_events(self):
            yield _event()

    monkeypatch.setattr(
        "tarav.l1.chatlas.commands.provide_normal_model_reader", lambda **_: Reader()
    )
    register_renderer(
        ChatlasRenderer(
            "workflow.cli.test.renderer",
            "text/plain",
            "CLI test renderer.",
            lambda result, options: f"{options['label']}:{len(result.findings)}",
        )
    )

    assert (
        main(
            [
                "chatlas",
                "render",
                "--identity-hash",
                "0" * 64,
                "--turn-hash-prefix",
                "a" * 8,
                "--renderer",
                "workflow.cli.test.renderer",
                "--renderer-option",
                "label=chosen",
            ]
        )
        == 0
    )

    assert capsys.readouterr().out == "chosen:1\n"


def test_query_json_uses_the_default_renderer_envelope(monkeypatch, capsys) -> None:
    class Reader:
        def model_header(self):
            return {"session": {"session_id": "session-one"}}

        def iter_turns(self):
            yield {
                "type": "Chat.Turn",
                "turn_address": "1" * 64,
                "turn_hash": "a" * 64,
                "side": "user",
                "event_refs": [_event_ref()],
                "message_refs": [],
            }

        def iter_messages(self):
            return iter(())

        def iter_events(self):
            yield _event()

    monkeypatch.setattr(
        "tarav.l1.chatlas.commands.provide_normal_model_reader", lambda **_: Reader()
    )

    assert (
        main(
            [
                "chatlas",
                "query",
                "--identity-hash",
                "0" * 64,
                "--turn-hash-prefix",
                "a" * 8,
                "--json",
            ]
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["renderer"] == "Chatlas.Query.Default.Renderer"
    assert payload["query_result"]["findings"][0]["prefix"] == "a" * 8


def test_query_discovers_current_session_with_an_explicit_provider(
    monkeypatch, capsys
) -> None:
    calls: list[dict[str, object]] = []

    class Reader:
        def model_header(self):
            return {"session": {"session_id": "current-session"}}

        def iter_turns(self):
            return iter(())

        def iter_messages(self):
            return iter(())

    monkeypatch.setenv("CODEX_THREAD_ID", "current-session")
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    monkeypatch.setattr(
        "tarav.l1.chatlas.commands.provide_normal_model_reader",
        lambda **kwargs: calls.append(kwargs) or Reader(),
    )

    assert (
        main(
            [
                "chatlas",
                "query",
                "--provider",
                "codex",
                "--current-session",
                "--side",
                "user",
                "--limit",
                "5",
            ]
        )
        == 0
    )

    assert capsys.readouterr().out == "\n"
    assert calls == [
        {
            "identity_hash": None,
            "session_id": "current-session",
            "provider": "codex",
            "instance": None,
            "chatlas_root": None,
            "refresh": False,
        }
    ]


def test_current_session_inference_rejects_ambiguous_harness_context(
    monkeypatch, capsys
) -> None:
    monkeypatch.setenv("CODEX_THREAD_ID", "codex-session")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "claude-session")

    assert main(["chatlas", "query", "--current-session"]) == 1
    assert "ambiguous" in capsys.readouterr().err


def test_update_current_session_is_an_explicit_provider_scoped_write(
    monkeypatch, capsys
) -> None:
    calls: list[dict[str, object]] = []
    monkeypatch.setenv("CODEX_THREAD_ID", "current-session")
    monkeypatch.setattr(
        "tarav.l1.chatlas.commands.chatlas_update",
        lambda **kwargs: calls.append(kwargs) or {"status": "ok"},
    )

    assert main(["chatlas", "update", "--provider", "codex", "--current-session"]) == 0

    assert json.loads(capsys.readouterr().out) == {"status": "ok"}
    assert calls[0]["providers"] == ("codex",)
    assert calls[0]["session_ids"] == ("current-session",)


def test_query_update_captures_exact_session_before_forced_refresh(
    monkeypatch, capsys
) -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    class Reader:
        def model_header(self):
            return {"session": {"session_id": "session-one"}}

        def iter_turns(self):
            return iter(())

        def iter_messages(self):
            return iter(())

    def update(**kwargs):
        calls.append(("update", kwargs))
        kwargs["progress"]("captured exact session")
        return {"status": "ok"}

    def reader(**kwargs):
        calls.append(("reader", kwargs))
        return Reader()

    monkeypatch.setattr("tarav.l1.chatlas.commands.chatlas_update", update)
    monkeypatch.setattr("tarav.l1.chatlas.commands.provide_normal_model_reader", reader)

    assert (
        main(
            [
                "chatlas",
                "query",
                "--provider",
                "codex",
                "--session-id",
                "session-one",
                "--update",
            ]
        )
        == 0
    )

    captured = capsys.readouterr()
    assert captured.out == "\n"
    assert captured.err == "captured exact session\n"
    assert [name for name, _kwargs in calls] == ["update", "reader"]
    assert calls[0][1]["providers"] == ("codex",)
    assert calls[0][1]["session_ids"] == ("session-one",)
    assert calls[1][1]["refresh"] is True


def test_render_update_resolves_the_provider_explicit_current_session(
    monkeypatch, capsys
) -> None:
    updates: list[dict[str, object]] = []

    class Reader:
        def model_header(self):
            return {"session": {"session_id": "current-session"}}

        def iter_turns(self):
            return iter(())

        def iter_messages(self):
            return iter(())

    monkeypatch.setenv("CODEX_THREAD_ID", "current-session")
    monkeypatch.setattr(
        "tarav.l1.chatlas.commands.chatlas_update",
        lambda **kwargs: updates.append(kwargs) or {"status": "ok"},
    )
    monkeypatch.setattr(
        "tarav.l1.chatlas.commands.provide_normal_model_reader", lambda **_: Reader()
    )

    assert (
        main(
            [
                "chatlas",
                "render",
                "--provider",
                "codex",
                "--current-session",
                "--update",
            ]
        )
        == 0
    )

    assert capsys.readouterr().out == "\n"
    assert updates[0]["providers"] == ("codex",)
    assert updates[0]["session_ids"] == ("current-session",)


def test_query_update_rejects_non_exact_update_targets_before_capture(
    monkeypatch, capsys
) -> None:
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        "tarav.l1.chatlas.commands.chatlas_update",
        lambda **kwargs: calls.append(kwargs),
    )

    assert main(["chatlas", "query", "--session-id", "session-one", "--update"]) == 1
    assert "requires --provider" in capsys.readouterr().err
    assert (
        main(
            [
                "chatlas",
                "query",
                "--provider",
                "codex",
                "--identity-hash",
                "0" * 64,
                "--update",
            ]
        )
        == 1
    )
    assert "not --identity-hash" in capsys.readouterr().err
    assert (
        main(
            [
                "chatlas",
                "query",
                "--provider",
                "codex",
                "--session-id",
                "session-one",
                "--update",
                "--limit",
                "0",
            ]
        )
        == 1
    )
    assert "limit must be positive" in capsys.readouterr().err
    assert calls == []


def test_render_uses_query_discovery_with_the_turn_ledger_renderer(
    monkeypatch, capsys
) -> None:
    class Reader:
        def model_header(self):
            return {"session": {"session_id": "session-one"}}

        def iter_turns(self):
            yield {
                "type": "Chat.Turn",
                "turn_address": "1" * 64,
                "turn_hash": "a" * 64,
                "side": "user",
                "event_refs": [_event_ref()],
                "message_refs": [
                    {"message_address": "2" * 64, "message_hash": "3" * 64}
                ],
            }

        def iter_messages(self):
            yield {
                "type": "Chat.Message",
                "message_address": "2" * 64,
                "message_hash": "3" * 64,
                "side": "user",
                "event_refs": [_event_ref()],
                "text": "discover this Turn",
            }

        def iter_events(self):
            yield _event()

    monkeypatch.setattr(
        "tarav.l1.chatlas.commands.provide_normal_model_reader", lambda **_: Reader()
    )

    assert (
        main(
            [
                "chatlas",
                "render",
                "--identity-hash",
                "0" * 64,
                "--side",
                "user",
                "--text-contains",
                "THIS turn",
                "--renderer",
                TURN_LEDGER_RENDERER,
            ]
        )
        == 0
    )

    assert capsys.readouterr().out == (
        "2026-09-20 00:00Z  aaaaaaaaaaaaaaaa  user   discover this Turn\n"
    )


def test_render_accepts_a_repeatable_turn_prefix_batch(monkeypatch, capsys) -> None:
    class Reader:
        def model_header(self):
            return {"session": {"session_id": "session-one"}}

        def iter_turns(self):
            yield {
                "type": "Chat.Turn",
                "turn_address": "1" * 64,
                "turn_hash": "a" * 64,
                "side": "user",
                "event_refs": [_event_ref()],
                "message_refs": [],
            }
            yield {
                "type": "Chat.Turn",
                "turn_address": "2" * 64,
                "turn_hash": "b" * 64,
                "side": "agent",
                "event_refs": [_event_ref()],
                "message_refs": [],
            }

        def iter_messages(self):
            return iter(())

        def iter_events(self):
            yield _event()

    monkeypatch.setattr(
        "tarav.l1.chatlas.commands.provide_normal_model_reader", lambda **_: Reader()
    )

    assert (
        main(
            [
                "chatlas",
                "render",
                "--identity-hash",
                "0" * 64,
                "--turn-hash-prefix",
                "b" * 8,
                "--turn-hash-prefix",
                "a" * 8,
            ]
        )
        == 0
    )

    output = capsys.readouterr().out
    assert output.index("Agent Turn `bbbbbbbb`") < output.index("User Turn `aaaaaaaa`")


def test_render_formats_an_ordered_inlined_capture_batch(monkeypatch, capsys) -> None:
    class Reader:
        def model_header(self):
            return {
                "session": {
                    "session_id": "session-one",
                    "provider": "codex",
                    "identity_hash": "0" * 64,
                }
            }

        def iter_turns(self):
            for digit in ("a", "b"):
                yield {
                    "type": "Chat.Turn",
                    "turn_address": digit * 64,
                    "turn_hash": digit * 64,
                    "side": "user",
                    "event_refs": [_event_ref()],
                    "message_refs": [],
                }

        def iter_messages(self):
            return iter(())

        def iter_events(self):
            yield _event()

    monkeypatch.setattr(
        "tarav.l1.chatlas.commands.provide_normal_model_reader", lambda **_: Reader()
    )

    assert (
        main(
            [
                "chatlas",
                "render",
                "--identity-hash",
                "0" * 64,
                "--turn-hash-prefix",
                "b" * 8,
                "--turn-hash-prefix",
                "a" * 20,
                "--renderer",
                INLINED_CAPTURE_MARKDOWN_RENDERER,
            ]
        )
        == 0
    )

    assert capsys.readouterr().out == (
        "<!-- tarav.context 00000000:bbbbbbbbbbbbbbbb -->\n"
        "<!-- tarav.context 00000000:aaaaaaaaaaaaaaaaaaaa -->\n"
    )


def test_normal_model_command_uses_an_exact_session_reference(
    monkeypatch, capsys
) -> None:
    calls: list[dict[str, object]] = []

    class Reader:
        def project(self, **kwargs):
            calls.append({"projection": kwargs})
            return {"type": "Chatlas.Normal.Model", "events": []}

    monkeypatch.setattr(
        "tarav.l1.chatlas.commands.provide_normal_model_reader",
        lambda **kwargs: calls.append(kwargs) or Reader(),
    )

    assert main(["chatlas", "normal-model", "--identity-hash", "abc"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "type": "Chatlas.Normal.Model",
        "events": [],
    }
    assert calls == [
        {
            "identity_hash": "abc",
            "session_id": None,
            "provider": None,
            "instance": None,
            "chatlas_root": None,
            "refresh": False,
        },
        {
            "projection": {
                "include_messages": False,
                "include_turns": False,
                "include_loaded_contexts": False,
            }
        },
    ]


def test_normal_model_collection_flags_are_additive(monkeypatch, capsys) -> None:
    projections: list[dict[str, object]] = []

    class Reader:
        def project(self, **kwargs):
            projections.append(kwargs)
            return {"events": [], "messages": [], "turns": [], "loaded_contexts": []}

    monkeypatch.setattr(
        "tarav.l1.chatlas.commands.provide_normal_model_reader",
        lambda **_: Reader(),
    )

    assert (
        main(
            [
                "chatlas",
                "normal-model",
                "--identity-hash",
                "abc",
                "--messages",
                "--turns",
                "--loaded-contexts",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["events"] == []
    assert projections == [
        {
            "include_messages": True,
            "include_turns": True,
            "include_loaded_contexts": True,
        }
    ]


def test_normal_model_all_and_raw_use_the_same_projection(monkeypatch, capsys) -> None:
    model = {
        "type": "Chatlas.Normal.Model",
        "schema_version": 1,
        "metadata": {},
        "session": {},
        "sources": [],
        "events": [1],
        "messages": [2],
        "turns": [3],
        "loaded_contexts": [4],
        "counts": {
            "events": 1,
            "messages": 1,
            "turns": 1,
            "loaded_contexts": 1,
        },
        "raw": [5],
    }
    monkeypatch.setattr(
        "tarav.l1.chatlas.commands.compute_normal_model",
        lambda **_: model,
    )

    assert (
        main(
            [
                "chatlas",
                "normal-model",
                "--identity-hash",
                "abc",
                "--all",
                "--include-raw",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out) == model
