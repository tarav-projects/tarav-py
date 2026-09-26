"""The public example exercises Archive and Context without live user data."""

from __future__ import annotations

import runpy
from pathlib import Path

from tarav import get_runtime, set_runtime
from tarav.archive.records import ArchiveRoot
from tarav.runtime import create_runtime

run_example = runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "dev" / "test_workflow_example.py")
)["run_example"]


def test_full_test_workflow_example_is_repeatable(tmp_path, capsys) -> None:
    previous = get_runtime()
    runtime = create_runtime(archive_root=tmp_path / "archive")
    set_runtime(runtime)
    try:
        archive = ArchiveRoot(runtime.contexts.archive_root)
        first_run, first_context = run_example(archive, runtime)
        second_run, second_context = run_example(archive, runtime)
    finally:
        set_runtime(previous)

    assert first_run != second_run
    assert first_context != second_context
    for root in (first_run, first_context, second_run, second_context):
        assert root.is_dir()
        assert (root / "main.json").is_file() or (
            root / "named" / "main.json"
        ).is_file()
    output = capsys.readouterr().out
    assert "Archive route:" in output
    assert "Context Archive route:" in output
