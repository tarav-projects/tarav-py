import json
from pathlib import Path

import pytest

from tarav.l1.skw.document import Document


def document(tmp_path):
    source = tmp_path / ".skw/src/demo.skw.json"
    source.parent.mkdir(parents=True)
    target = tmp_path / "context.txt"
    target.write_text("first\n" + "x" * 8000 + "\nlast\n")
    source.write_text(json.dumps({"type": "Tarav.Skillware.Document", "schema_version": 1,
        "output": "demo.md", "blocks": [{"id": "body", "kind": "generation", "prompt": [],
        "output": ["Retained"], "context": [
            {"kind": "reference", "roles": ["dependency"], "reference": {"type": "Tarav.Reference.StructuredFile",
                "locator": {"path": "../../context.txt"}}},
            {"kind": "reference", "roles": ["dependency"], "reference": {"type": "Tarav.Reference.StructuredFile",
                "locator": {"path": "missing.txt"}}}]}]}))
    return Document(source), target


def test_listing_does_not_read_targets(tmp_path, monkeypatch):
    doc, target = document(tmp_path)
    def forbidden(*args, **kwargs):
        raise AssertionError("Listing read a target")
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    monkeypatch.setattr(Path, "read_text", forbidden)
    entries = doc.context("body")
    assert entries[0]["path"] == str(target.resolve())
    assert entries[0]["status"] == "available-unchecked"
    assert entries[1]["status"] == "unresolvable"
    assert "content" not in entries[0]


def test_selected_reads_ignore_other_missing_targets_and_bound_previews(tmp_path):
    doc, target = document(tmp_path)
    assert doc.read_context("body", 0, mode="head", line_limit=1)["text"] == "first\n"
    assert doc.read_context("body", 0, mode="tail", line_limit=1)["text"] == "last\n"
    preview = doc.read_context("body", 0, mode="head", char_limit=40)
    assert len(preview["text"]) == 40 and preview["truncated"]
    assert doc.read_context("body", 0)["text"] == target.read_text()
    for index in (-1, 2):
        with pytest.raises(ValueError, match="index"):
            doc.read_context("body", index)


def test_navigation_does_not_modify_baselines_and_lint_still_checks(tmp_path):
    doc, target = document(tmp_path)
    doc.data["blocks"][0]["context"].pop()
    doc.source.write_text(json.dumps(doc.data))
    doc.observe_context("body")
    before = doc.lock_path.read_bytes()
    target.write_text("changed")
    doc.context("body")
    doc.read_context("body", 0)
    assert doc.lock_path.read_bytes() == before
    assert "stale-context" in {f["kind"] for f in doc.lint()}


def test_cli_lists_then_reads_selected_entry(tmp_path):
    import subprocess
    import sys

    doc, _ = document(tmp_path)
    command = [sys.executable, "-c", "from tarav.cli import main; raise SystemExit(main())",
               "skw", "document", "context", "--project", str(tmp_path), "--source", "demo.skw.json", "--block", "body"]
    listing = subprocess.run(command, capture_output=True, text=True, check=True)
    explicit = subprocess.run(command + ["--rendered"], capture_output=True, text=True, check=True)
    assert listing.stdout == explicit.stdout
    assert "[0] reference  available-unchecked" in listing.stdout
    structured = subprocess.run(command + ["--json"], capture_output=True, text=True, check=True)
    structured_result = json.loads(structured.stdout)
    assert structured_result == doc.context("body")
    assert "content" not in structured_result[0]
    preview = subprocess.run(command + ["--head", "0", "--lines", "1"],
                             capture_output=True, text=True, check=True)
    assert preview.stdout == "first\n"
    assert "truncated" in preview.stderr
    preview_json = subprocess.run(command + ["--head", "0", "--lines", "1", "--json"],
                                  capture_output=True, text=True, check=True)
    assert json.loads(preview_json.stdout) == doc.read_context(
        "body", 0, mode="head", line_limit=1, char_limit=4000
    ) == {
        "index": 0, "mode": "head", "text": "first\n", "truncated": True,
    }
    assert preview_json.stderr == ""


def test_project_discovery_and_source_boundaries(tmp_path, monkeypatch):
    from tarav.l1.skw.document import project_document, project_root

    doc, _ = document(tmp_path)
    nested = tmp_path / "nested/deep"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)
    assert project_root() == tmp_path.resolve()
    assert project_document("demo.skw.json").source == doc.source
    (nested / ".skw").mkdir()
    assert project_root() == nested.resolve()
    assert project_document("demo.skw.json", project=tmp_path).source == doc.source
    for invalid in ("../../outside.json", str(doc.source)):
        with pytest.raises(ValueError):
            project_document(invalid, project=tmp_path)
    with pytest.raises(ValueError, match="No .skw"):
        project_root(tmp_path / "missing")
