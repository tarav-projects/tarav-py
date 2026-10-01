from tarav.l0.kernel import entity

import json
import subprocess

from tarav.l1.references import FileReference
from tarav.l1.references.git import GitFileReference
from tarav.l1.archive import Archive
from tarav.l1.archive.references import ArchiveReference, reference_record
from tarav.l3.runtime import create_runtime


def test_file_hints_are_observed_once_and_loading_does_not_refresh(tmp_path):
    path = tmp_path / "file.txt"
    path.write_text("hello")
    reference = FileReference(path)
    assert reference.hints["size"] == 5
    retained = json.loads(json.dumps(reference.to_record()))
    path.write_text("changed content")
    runtime = create_runtime()
    loaded = runtime.references.load(retained)
    assert loaded.hints["size"] == 5
    assert runtime.references.resolve(retained).ok
    path.unlink()
    assert not runtime.references.resolve(retained).ok
    assert FileReference(path).hints["unavailable"]


def test_reference_producers_omit_absent_optional_fields(tmp_path):
    missing = FileReference(tmp_path / "missing")
    archive = Archive.create(tmp_path / "archive")

    assert "check" not in missing.to_record()
    assert missing.hints
    assert reference_record(archive, "0" * 64) == {
        "type": entity(ArchiveReference).name,
        "locator": {"archive": str(archive.root), "doi": "0" * 64},
    }


def test_archive_default_is_retained_and_not_reselected(tmp_path, monkeypatch):
    import tarav.l1.archive.references as references

    archive = Archive.create(tmp_path / "archive")
    target = tmp_path / "file"
    target.write_text("data")
    doi = archive.reference_file(str(target))["locator"]["doi"]
    monkeypatch.setattr(references, "default_archive_root", lambda: archive.root)
    reference = ArchiveReference(doi=doi)
    monkeypatch.setattr(references, "default_archive_root", lambda: tmp_path / "other")
    assert reference.locator["archive"] == str(archive.root)
    assert create_runtime().references.resolve(reference.to_record()).ok


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
    result = create_runtime().references.resolve(reference.to_record())
    assert result.ok
    assert result.target["content"] == b"original"
    assert reference.hints["revision"] == "HEAD"
    assert reference.locator["commit"] != git("rev-parse", "HEAD")


def test_unknown_reference_is_reported_without_importing_code():
    result = create_runtime().references.resolve({"type": "unknown.module.Class"})
    assert not result.ok
    assert result.pois
