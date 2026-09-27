from datetime import date
import subprocess

import pytest

from tarav.l0._core.project import initialize_project_layout
from tarav.l1.project import Project
from tarav.wiki import Wiki


def test_project_and_folder_wiki_are_lazy_and_parse_native_markdown(tmp_path):
    initialize_project_layout(tmp_path)
    child = tmp_path / "src"
    child.mkdir()
    wiki = Project.from_path(child).wiki()
    assert wiki.root == Project.from_path(tmp_path).wiki().root
    assert wiki.root == Wiki.from_path(tmp_path / "notes/wiki").root
    note = wiki.daily(date(2026, 9, 26))
    assert not wiki.root.exists()
    assert wiki.ls() == ()
    note.write("# Today\n\n```md\n# Not a heading\n```\n")
    assert [heading.text for heading in note.parse().headings] == ["Today"]
    assert [item.relative_path.as_posix() for item in wiki.ls()] == [
        "daily/2026-09-26.md"
    ]


def test_note_rejects_escape_including_symlink_changed_after_lookup(tmp_path):
    wiki = Wiki(tmp_path / "wiki")
    for path in ("../outside.md", tmp_path / "outside.md", "topic.txt"):
        with pytest.raises(ValueError):
            wiki.get(path)
    note = wiki.get("sub/topic.md")
    wiki.root.mkdir()
    (wiki.root / "sub").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError):
        note.write("outside")
    assert not (tmp_path / "topic.md").exists()


@pytest.mark.parametrize("standalone", [False, True])
def test_commit_includes_wiki_changes_and_preserves_outside_index(tmp_path, standalone):
    def git(*args):
        return subprocess.run(
            ["git", "-C", str(tmp_path), *args],
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()

    git("init")
    git("config", "user.name", "Wiki Test")
    git("config", "user.email", "wiki@example.invalid")
    git("commit", "--allow-empty", "-m", "initial")
    wiki = Wiki(tmp_path if standalone else tmp_path / "notes/wiki")
    wiki.get("old.md").write("old")
    wiki.commit("first")
    wiki.get("old.md").path.unlink()
    wiki.get("new.md").write("new")
    if not standalone:
        (tmp_path / "outside.txt").write_text("staged")
        git("add", "outside.txt")
        (tmp_path / "outside.txt").write_text("unstaged")
        before = git("ls-files", "--stage", "--", "outside.txt")
    commit = wiki.commit("capture")
    assert commit == git("rev-parse", "HEAD")
    assert wiki.commit("nothing") is None
    if not standalone:
        assert git("ls-files", "--stage", "--", "outside.txt") == before
        assert git("status", "--porcelain", "--", "outside.txt") == "AM outside.txt"
        assert "outside.txt" not in git("ls-tree", "-r", "--name-only", "HEAD")
