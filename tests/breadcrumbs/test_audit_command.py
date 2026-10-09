"""Batch file selection for the existing Breadcrumb audit command."""

from __future__ import annotations

import json
from pathlib import Path

from tarav.l3.cli.cli import main


# tarav.breadcrumb bd69fa5f753c55e09acfa12ec810c7c7e3eac5d7686ea4b6abe2114132345f79
def test_audit_manifest_reports_each_file_and_continues_after_error(
    tmp_path: Path, monkeypatch, capsys,
) -> None:
    first = tmp_path / "first.md"
    second = tmp_path / "second.py"
    first.write_text("# First\n", encoding="utf-8")
    second.write_text("value = 1\n", encoding="utf-8")
    (tmp_path / "files.txt").write_text(
        "first.md\n\nsecond.py\nmissing.md\nfirst.md\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert main(["breadcrumbs", "audit", "chatlas-context",
                 "--surface", "first.md", "--files-from", "files.txt",
                 "--breadcrumbs-root", str(tmp_path / "store"), "--json"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["summary"] == {"files": 3, "ok": 2, "pois": 0, "errors": 1}
    assert [row["surface"] for row in report["files"]] == [
        str(first), str(second), str(tmp_path / "missing.md")]
    assert [row["status"] for row in report["files"]] == ["ok", "ok", "error"]


def test_repeated_surfaces_and_single_file_shape(tmp_path: Path, capsys) -> None:
    first = tmp_path / "first.md"
    second = tmp_path / "second.md"
    first.write_text("# First\n", encoding="utf-8")
    second.write_text("# Second\n", encoding="utf-8")
    args = ["breadcrumbs", "audit", "chatlas-context",
            "--breadcrumbs-root", str(tmp_path / "store"), "--json"]

    assert main([*args, "--surface", str(first)]) == 0
    single = json.loads(capsys.readouterr().out)
    assert single["surface"] == str(first)
    assert "files" not in single

    assert main([*args, "--surface", str(first), "--surface", str(second),
                 "--refresh-positions"]) == 0
    batch = json.loads(capsys.readouterr().out)
    assert batch["summary"]["files"] == 2
    assert [row["surface"] for row in batch["files"]] == [str(first), str(second)]


def test_file_selection_cannot_mix_with_commit_audit(tmp_path: Path, capsys) -> None:
    assert main(["breadcrumbs", "audit", "chatlas-context", "--commit", "HEAD",
                 "--repo", str(tmp_path), "--files-from", str(tmp_path / "files.txt")]) != 0
    assert "without file-selection options" in capsys.readouterr().err
