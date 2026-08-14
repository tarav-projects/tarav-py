from __future__ import annotations

from datetime import datetime, timezone

from tarav.forum import core
from tarav.forum.core import ForumDepot, forum_banner_line, read_cursor


def _set_now(monkeypatch, value: str) -> None:
    now = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    monkeypatch.setattr(core, "_utc_now", lambda: now)


def test_forum_post_appends_date_sections(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TARAV_FORUM_ROOT", str(tmp_path / "forum"))
    depot = ForumDepot()
    _set_now(monkeypatch, "2026-07-18T10:00:00Z")
    first = depot.post("First", "hello", "project-a")
    _set_now(monkeypatch, "2026-07-18T10:01:00Z")
    second = depot.post("Second", "world", "project-b")

    assert first.path == second.path == tmp_path / "forum" / "posts" / "2026-07-18.md"
    text = first.path.read_text(encoding="utf-8")
    assert "## 10:00:00Z — First" in text
    assert "## 10:01:00Z — Second" in text
    assert text.index("First") < text.index("Second")


def test_forum_posts_since_filters_and_skips_malformed(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TARAV_FORUM_ROOT", str(tmp_path / "forum"))
    depot = ForumDepot()
    _set_now(monkeypatch, "2026-07-17T23:59:59Z")
    depot.post("Old", "old body", "project")
    _set_now(monkeypatch, "2026-07-18T00:00:01Z")
    depot.post("New", "new body", "project")
    (tmp_path / "forum" / "posts" / "2026-07-18.md").write_text(
        (tmp_path / "forum" / "posts" / "2026-07-18.md").read_text(encoding="utf-8")
        + "\n## malformed\nbad\n",
        encoding="utf-8",
    )

    posts = depot.posts_since("2026-07-18T00:00:00Z")
    assert [post.title for post in posts] == ["New"]


def test_forum_banner_throttles_and_never_raises(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("TARAV_FORUM_ROOT", str(tmp_path / "forum"))
    monkeypatch.setenv("TARAV_FORUM_CURSOR", str(tmp_path / "cursor.json"))
    depot = ForumDepot()
    _set_now(monkeypatch, "2026-07-18T10:00:00Z")
    depot.post("Unread", "body", "project")

    assert forum_banner_line() == "tarav forum: 1 unread post(s) — run 'tarav forum check'"
    assert read_cursor()["last_banner"] == "2026-07-18T10:00:00Z"
    assert forum_banner_line() is None

    def raise_on_read(_self, _timestamp):
        raise OSError("boom")

    monkeypatch.setattr(core.ForumDepot, "posts_since", raise_on_read)
    assert forum_banner_line() is None
