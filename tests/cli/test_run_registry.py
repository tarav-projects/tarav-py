"""`tarav run` retains the code it executes without affecting the run."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

from tarav.l1.python_env import RunnerConfiguration, RunRegistry
from tarav.l1.python_env.registry import GLOBAL_PARTITION
from tarav.l3.cli.cli import main


def _entries(root: Path, partition: str = GLOBAL_PARTITION) -> list[Path]:
    folder = root / partition
    return sorted(path for path in folder.iterdir() if path.is_dir()) if folder.is_dir() else []


def _record(entry: Path) -> dict:
    return json.loads((entry / "entry.json").read_text())


@pytest.fixture
def registry(tmp_path: Path, monkeypatch) -> Path:
    root = tmp_path / "registry"
    monkeypatch.setenv("TARAV_RUN_REGISTRY", str(root))
    return root


# tarav.breadcrumb dfcdb298fb34d4217164fcb8a2b10f807ceff034f6023956189cd6c8ff944d88
def test_inline_code_is_retained_with_its_outcome(registry: Path, capfd) -> None:
    code = "print('hello'); raise SystemExit(3)"

    assert main(["run", "--", "-c", code, "--flag"]) == 3
    capfd.readouterr()

    (entry,) = _entries(registry)
    record = _record(entry)
    assert (entry / "source.py").read_text() == code
    assert record["mode"] == "code"
    assert record["arguments"] == ["--flag"]
    assert record["exit_code"] == 3
    assert record["project"] is None
    assert record["truncated"] is False
    assert record["calling_directory"] == str(Path.cwd())


def test_script_file_is_copied_with_its_path(registry: Path, tmp_path: Path, capfd) -> None:
    script = tmp_path / "probe.py"
    script.write_text("print('probe')\n")

    assert main(["run", "--", str(script)]) == 0
    capfd.readouterr()

    (entry,) = _entries(registry)
    assert (entry / "source.py").read_text() == "print('probe')\n"
    assert _record(entry)["script"] == str(script.resolve())


def test_module_run_keeps_the_name_and_no_source(registry: Path, capfd) -> None:
    assert main(["run", "--", "-m", "platform"]) == 0
    capfd.readouterr()

    (entry,) = _entries(registry)
    assert _record(entry)["module"] == "platform"
    assert not (entry / "source.py").exists()


def test_standard_input_is_retained_and_replayed(registry: Path, monkeypatch, capfd) -> None:
    code = b"print('from stdin')\n"
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(code)))

    assert main(["run", "--", "-"]) == 0
    assert capfd.readouterr().out.strip() == "from stdin"

    (entry,) = _entries(registry)
    assert (entry / "source.py").read_bytes() == code
    assert _record(entry)["mode"] == "stdin"


def test_project_runs_use_the_project_partition(
    registry: Path, tmp_path: Path, monkeypatch, capfd
) -> None:
    from tarav.l3 import run as command

    project = tmp_path / "project"
    (project / ".tarav").mkdir(parents=True)
    identity = "20c26be7-a8e5-4974-9ec0-0b5a3a125a94"
    (project / ".tarav" / "project.json").write_text(json.dumps(
        {"project_id": identity, "created_at": "2026-10-15T00:00:00Z",
         "harness": {"environment": ".tarav/env", "type": "tarav.l2.project:Project"}}))

    class Configurator:
        @classmethod
        def from_path(cls, path):
            return cls()

        def configure(self):
            return RunnerConfiguration(interpreter=sys.executable, cwd=project)

    monkeypatch.setattr(command, "ProjectRunnerConfigurator", Configurator)

    assert main(["run", "--project", str(project), "--", "-c", "print(1)"]) == 0
    capfd.readouterr()

    assert _entries(registry) == []
    (entry,) = _entries(registry, identity)
    assert _record(entry)["project"]["id"] == identity
    assert _record(entry)["project"]["root"] == str(project.resolve())


def test_an_unusable_registry_never_changes_the_run(tmp_path: Path, monkeypatch, capfd) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("not a folder")
    monkeypatch.setenv("TARAV_RUN_REGISTRY", str(blocker))

    assert main(["run", "--", "-c", "raise SystemExit(5)"]) == 5
    capfd.readouterr()


# tarav.breadcrumb efdd4a8e8070b72baf93a746feffa5a5121c600346ac7c0f5c46593cde9423c7
def test_large_source_is_cut_and_marked(tmp_path: Path) -> None:
    registry = RunRegistry(tmp_path, entry_limit=10)

    entry = registry.begin(partition=None, source=b"x" * 25, metadata={"mode": "code"})

    assert entry is not None
    assert (entry.directory / "source.py").read_bytes() == b"x" * 10
    assert entry.record["truncated"] is True
    assert entry.record["size"] == 25


def test_partition_is_pruned_oldest_first_by_size(tmp_path: Path) -> None:
    registry = RunRegistry(tmp_path, partition_limit=700)

    made = [registry.begin(partition="p", source=bytes([65 + i]) * 200, metadata={"mode": "code"})
            for i in range(4)]

    kept = _entries(tmp_path, "p")
    assert made[-1].directory in kept
    assert made[0].directory not in kept
    assert 0 < len(kept) < 4


def test_repeated_code_shares_one_file_and_survives_pruning(tmp_path: Path) -> None:
    registry = RunRegistry(tmp_path)

    first = registry.begin(partition=None, source=b"print(1)", metadata={"mode": "code"})
    second = registry.begin(partition=None, source=b"print(1)", metadata={"mode": "code"})

    one, two = first.directory / "source.py", second.directory / "source.py"
    assert one.stat().st_ino == two.stat().st_ino
    one.unlink()
    assert two.read_bytes() == b"print(1)"


def test_an_interrupted_run_is_still_recorded(tmp_path: Path) -> None:
    registry = RunRegistry(tmp_path)

    entry = registry.begin(partition=None, source=b"pass", metadata={"mode": "code"})

    assert _record(entry.directory)["exit_code"] is None
    registry.finish(entry, exit_code=0)
    assert _record(entry.directory)["exit_code"] == 0
