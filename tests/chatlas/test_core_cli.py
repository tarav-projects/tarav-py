from __future__ import annotations

import json

from tarav.cli.cli import build_parser, main
from tarav.chatlas.rendering import (
    INLINED_CAPTURE_MARKDOWN_RENDERER,
    TURN_LEDGER_RENDERER,
)


def test_chatlas_help_exposes_current_commands() -> None:
    parser = build_parser()
    chatlas = next(
        action.choices["chatlas"]
        for action in parser._actions
        if hasattr(action, "choices") and action.choices and "chatlas" in action.choices
    )
    help_text = chatlas.format_help()

    for command in ("update", "index", "raw", "normal-model", "query", "render"):
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
                "class": "Chat.Turn",
                "turn_address": "1" * 64,
                "turn_hash": "a" * 64,
                "side": "user",
                "event_refs": [],
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
                "class": "Chat.Message",
                "message_address": "2" * 64,
                "message_hash": "3" * 64,
                "side": "user",
                "event_refs": [],
                "text": "selected text",
            }

    monkeypatch.setattr(
        "tarav.chatlas.commands.provide_normal_model_reader", lambda **_: Reader()
    )
    argv = ["--identity-hash", "0" * 64, "--turn-hash-prefix", "a" * 8]

    assert main(["chatlas", "query", *argv]) == 0
    queried = capsys.readouterr().out
    assert main(["chatlas", "render", *argv]) == 0
    rendered = capsys.readouterr().out

    assert queried == rendered
    assert "selected text" in queried
    assert calls == [("turns",), ("messages",), ("turns",), ("messages",)]


def test_render_selects_a_registered_renderer_and_passes_options(
    monkeypatch, capsys
) -> None:
    from tarav.chatlas.rendering import ChatlasRenderer, register_renderer

    class Reader:
        def model_header(self):
            return {"session": {"session_id": "session-one"}}

        def iter_turns(self):
            yield {
                "turn_address": "1" * 64,
                "turn_hash": "a" * 64,
                "side": "user",
                "message_refs": [],
            }

        def iter_messages(self):
            return iter(())

    monkeypatch.setattr(
        "tarav.chatlas.commands.provide_normal_model_reader", lambda **_: Reader()
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
                "turn_address": "1" * 64,
                "turn_hash": "a" * 64,
                "side": "user",
                "message_refs": [],
            }

        def iter_messages(self):
            return iter(())

    monkeypatch.setattr(
        "tarav.chatlas.commands.provide_normal_model_reader", lambda **_: Reader()
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
        "tarav.chatlas.commands.provide_normal_model_reader",
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
        "tarav.chatlas.commands.chatlas_update",
        lambda **kwargs: calls.append(kwargs) or {"status": "ok"},
    )

    assert main(["chatlas", "update", "--provider", "codex", "--current-session"]) == 0

    assert json.loads(capsys.readouterr().out) == {"status": "ok"}
    assert calls[0]["providers"] == ("codex",)
    assert calls[0]["session_ids"] == ("current-session",)


def test_render_uses_query_discovery_with_the_turn_ledger_renderer(
    monkeypatch, capsys
) -> None:
    class Reader:
        def model_header(self):
            return {"session": {"session_id": "session-one"}}

        def iter_turns(self):
            yield {
                "turn_address": "1" * 64,
                "turn_hash": "a" * 64,
                "side": "user",
                "message_refs": [
                    {"message_address": "2" * 64, "message_hash": "3" * 64}
                ],
            }

        def iter_messages(self):
            yield {
                "message_address": "2" * 64,
                "message_hash": "3" * 64,
                "side": "user",
                "text": "discover this Turn",
            }

    monkeypatch.setattr(
        "tarav.chatlas.commands.provide_normal_model_reader", lambda **_: Reader()
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

    assert capsys.readouterr().out == ("aaaaaaaaaaaaaaaa  user   discover this Turn\n")


def test_render_accepts_a_repeatable_turn_prefix_batch(monkeypatch, capsys) -> None:
    class Reader:
        def model_header(self):
            return {"session": {"session_id": "session-one"}}

        def iter_turns(self):
            yield {
                "turn_address": "1" * 64,
                "turn_hash": "a" * 64,
                "side": "user",
                "message_refs": [],
            }
            yield {
                "turn_address": "2" * 64,
                "turn_hash": "b" * 64,
                "side": "agent",
                "message_refs": [],
            }

        def iter_messages(self):
            return iter(())

    monkeypatch.setattr(
        "tarav.chatlas.commands.provide_normal_model_reader", lambda **_: Reader()
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
            return {"session": {"session_id": "session-one"}}

        def iter_turns(self):
            for digit in ("a", "b"):
                yield {
                    "turn_address": digit * 64,
                    "turn_hash": digit * 64,
                    "side": "user",
                    "message_refs": [],
                }

        def iter_messages(self):
            return iter(())

    monkeypatch.setattr(
        "tarav.chatlas.commands.provide_normal_model_reader", lambda **_: Reader()
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
                "--renderer-option",
                "session-alias=phd",
            ]
        )
        == 0
    )

    assert capsys.readouterr().out == (
        "<!-- tarav.context phd:bbbbbbbbbbbbbbbb -->\n"
        "<!-- tarav.context phd:aaaaaaaaaaaaaaaaaaaa -->\n"
    )


def test_normal_model_command_uses_an_exact_session_reference(
    monkeypatch, capsys
) -> None:
    calls: list[dict[str, object]] = []

    class Reader:
        def project(self, **kwargs):
            calls.append({"projection": kwargs})
            return {"class": "tarav.chatlas.normal_model", "events": []}

    monkeypatch.setattr(
        "tarav.chatlas.commands.provide_normal_model_reader",
        lambda **kwargs: calls.append(kwargs) or Reader(),
    )

    assert main(["chatlas", "normal-model", "--identity-hash", "abc"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "class": "tarav.chatlas.normal_model",
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
        "tarav.chatlas.commands.provide_normal_model_reader",
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
        "class": "tarav.chatlas.normal_model",
        "schema_version": 1,
        "metadata": {},
        "session": {},
        "sources": [],
        "events": [1],
        "messages": [2],
        "turns": [3],
        "loaded_contexts": [4],
        "raw": [5],
    }
    monkeypatch.setattr(
        "tarav.chatlas.commands.compute_normal_model",
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
