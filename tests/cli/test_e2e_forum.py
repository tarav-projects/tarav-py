from __future__ import annotations

import pytest

from tarav.cli.cli import main
from _helpers import captured_json


def test_forum_post_check_read_round_trip(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("TARAV_FORUM_ROOT", str(tmp_path / "forum"))
    monkeypatch.setenv("TARAV_FORUM_CURSOR", str(tmp_path / "cursor.json"))
    monkeypatch.chdir(tmp_path)

    assert main(["forum", "post", "--title", "Hello", "--body", "world", "--from", "project-a", "--json"]) == 0
    posted = captured_json(capsys)
    assert posted["post"]["title"] == "Hello"

    assert main(["forum", "check", "--json"]) == 0
    checked = captured_json(capsys)
    assert checked["unread_count"] == 1
    assert checked["posts"][0]["title"] == "Hello"

    assert main(["forum", "read", "--json"]) == 0
    read = captured_json(capsys)
    assert read["count"] == 1
    assert read["cursor_advanced"] is True
    assert read["posts"][0]["body"] == "world"

    assert main(["forum", "check", "--json"]) == 0
    assert captured_json(capsys)["unread_count"] == 0


def test_forum_read_date_does_not_advance_cursor(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("TARAV_FORUM_ROOT", str(tmp_path / "forum"))
    monkeypatch.setenv("TARAV_FORUM_CURSOR", str(tmp_path / "cursor.json"))
    posts = tmp_path / "forum" / "posts"
    posts.mkdir(parents=True)
    posts.joinpath("2026-07-18.md").write_text(
        "## 10:00:00Z — Dated\n\nbody\n\n- from: project\n",
        encoding="utf-8",
    )

    assert main(["forum", "read", "--date", "2026-07-18", "--json"]) == 0
    payload = captured_json(capsys)
    assert payload["count"] == 1
    assert payload["cursor_advanced"] is False
    assert not (tmp_path / "cursor.json").exists()


def test_forum_help_is_top_level(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["forum", "--help"])
    assert exc_info.value.code == 0
    assert "post" in capsys.readouterr().out
