from __future__ import annotations

import json

from tarav.cli.cli import build_parser, main


def test_chatlas_help_exposes_only_core_commands() -> None:
    parser = build_parser()
    chatlas = next(
        action.choices["chatlas"]
        for action in parser._actions
        if hasattr(action, "choices") and action.choices and "chatlas" in action.choices
    )
    help_text = chatlas.format_help()

    for command in ("update", "index", "raw", "normal-model"):
        assert command in help_text
    for removed in ("query", "recents", "products", "anchory", "views", "events"):
        assert removed not in help_text


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

    assert main(
        [
            "chatlas",
            "normal-model",
            "--identity-hash",
            "abc",
            "--messages",
            "--turns",
            "--loaded-contexts",
        ]
    ) == 0
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

    assert main(
        [
            "chatlas",
            "normal-model",
            "--identity-hash",
            "abc",
            "--all",
            "--include-raw",
        ]
    ) == 0
    assert json.loads(capsys.readouterr().out) == model
