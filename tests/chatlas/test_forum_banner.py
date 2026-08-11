from __future__ import annotations

from agentos.cli.cli import main


def test_chatlas_update_prints_forum_banner_on_non_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr("agentos.chatlas.commands.set_trust_tier", lambda _tier: None)
    monkeypatch.setattr("agentos.chatlas.commands.chatlas_update", lambda **_kwargs: {"status": "ok"})
    monkeypatch.setattr(
        "agentos.chatlas.commands.forum_banner_line",
        lambda: "agentos forum: 1 unread post(s) — run 'agentos forum check'",
    )

    assert main(["chatlas", "update", "--quiet", "--verbose-mode", "quiet"]) == 0

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "agentos forum: 1 unread post(s) — run 'agentos forum check'\n"


def test_chatlas_update_suppresses_forum_banner_on_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr("agentos.chatlas.commands.set_trust_tier", lambda _tier: None)
    monkeypatch.setattr("agentos.chatlas.commands.chatlas_update", lambda **_kwargs: {"status": "ok"})
    monkeypatch.setattr(
        "agentos.chatlas.commands.forum_banner_line",
        lambda: "agentos forum: 1 unread post(s) — run 'agentos forum check'",
    )

    assert main(["chatlas", "update", "--json", "--verbose-mode", "quiet"]) == 0

    captured = capsys.readouterr()
    assert '"status": "ok"' in captured.out
    assert captured.err == ""
