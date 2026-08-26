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
    monkeypatch.setattr(
        "tarav.chatlas.commands.provide_normal_model",
        lambda **kwargs: calls.append(kwargs)
        or {"class": "tarav.chatlas.normal_model"},
    )

    assert main(["chatlas", "normal-model", "--identity-hash", "abc"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "class": "tarav.chatlas.normal_model"
    }
    assert calls == [
        {
            "identity_hash": "abc",
            "session_id": None,
            "provider": None,
            "instance": None,
            "chatlas_root": None,
            "refresh": False,
        }
    ]
