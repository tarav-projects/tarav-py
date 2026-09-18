import json
import subprocess

from tarav.references import FileReference
from tarav.references.git import GitFileReference
from tarav.archive import Archive
from tarav.archive.references import ArchiveReference
from tarav.runtime import create_runtime


def test_file_hints_are_observed_once_and_loading_does_not_refresh(tmp_path):
    path = tmp_path / "file.txt"
    path.write_text("hello")
    reference = FileReference(path)
    assert reference.hints["size"] == 5
    retained = json.loads(json.dumps(reference.record))
    path.write_text("changed content")
    runtime = create_runtime()
    loaded = runtime.references.load(retained)
    assert loaded.hints["size"] == 5
    assert runtime.references.resolve(retained).ok
    path.unlink()
    assert not runtime.references.resolve(retained).ok
    assert FileReference(path).hints["unavailable"]


def test_archive_default_is_retained_and_not_reselected(tmp_path, monkeypatch):
    import tarav.archive.references as references

    archive = Archive.create(tmp_path / "archive")
    target = tmp_path / "file"
    target.write_text("data")
    doi = archive.reference_file(str(target))["locator"]["doi"]
    monkeypatch.setattr(references, "default_archive_root", lambda: archive.root)
    reference = ArchiveReference(doi=doi)
    monkeypatch.setattr(references, "default_archive_root", lambda: tmp_path / "other")
    assert reference.locator["archive"] == str(archive.root)
    assert create_runtime().references.resolve(reference.record).ok


def test_git_reference_keeps_edition_after_head_changes(tmp_path):
    def git(*args):
        return subprocess.run(
            ["git", "-C", str(tmp_path), *args],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    git("init", "-q")
    path = tmp_path / "file.txt"
    path.write_text("original")
    git("add", ".")
    git(
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.com",
        "commit",
        "-qm",
        "first",
    )
    reference = GitFileReference(repository=tmp_path, commit="HEAD", path="file.txt")
    path.write_text("changed")
    git("add", ".")
    git(
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.com",
        "commit",
        "-qm",
        "second",
    )
    result = create_runtime().references.resolve(reference.record)
    assert result.ok
    assert result.target["content"] == b"original"
    assert reference.hints["revision"] == "HEAD"
    assert reference.locator["commit"] != git("rev-parse", "HEAD")


def test_unknown_reference_is_reported_without_importing_code():
    result = create_runtime().references.resolve({"type": "unknown.module.Class"})
    assert not result.ok
    assert result.findings
