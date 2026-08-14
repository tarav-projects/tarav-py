from __future__ import annotations

from tarav.cli.cli import main


def test_chatlas_update_prints_forum_banner_on_non_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr("tarav.chatlas._command_support.set_trust_tier", lambda _tier: None)
    monkeypatch.setattr("tarav.chatlas._command_support.chatlas_update", lambda **_kwargs: {"status": "ok"})
    monkeypatch.setattr(
        "tarav.chatlas._command_support.forum_banner_line",
        lambda: "tarav forum: 1 unread post(s) — run 'tarav forum check'",
    )

    assert main(["chatlas", "update", "--quiet", "--verbose-mode", "quiet"]) == 0

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "tarav forum: 1 unread post(s) — run 'tarav forum check'\n"


def test_chatlas_update_suppresses_forum_banner_on_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr("tarav.chatlas._command_support.set_trust_tier", lambda _tier: None)
    monkeypatch.setattr("tarav.chatlas._command_support.chatlas_update", lambda **_kwargs: {"status": "ok"})
    monkeypatch.setattr(
        "tarav.chatlas._command_support.forum_banner_line",
        lambda: "tarav forum: 1 unread post(s) — run 'tarav forum check'",
    )

    assert main(["chatlas", "update", "--json", "--verbose-mode", "quiet"]) == 0

    captured = capsys.readouterr()
    assert '"status": "ok"' in captured.out
    assert captured.err == ""
