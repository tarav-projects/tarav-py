"""The root CLI owns one explicit Python argument boundary."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tarav.l1.python_env import RunnerConfiguration
from tarav.l3.cli.cli import build_parser, main


# tarav.breadcrumb ecc883a43a33
def test_run_forwards_python_arguments_and_exit_code(capfd) -> None:
    code = "import json, sys; print(json.dumps(sys.argv[1:])); raise SystemExit(7)"

    assert main(["run", "--", "-c", code, "--flag", "value"]) == 7
    assert json.loads(capfd.readouterr().out) == ["--flag", "value"]


def test_run_selects_project_configuration_and_project_working_directory(
    tmp_path: Path, monkeypatch, capfd
) -> None:
    from tarav.l3 import run as command

    script = tmp_path / "probe.py"
    script.write_text("import json, os, sys; print(json.dumps([os.getcwd(), sys.argv[1:]]))\n")
    selected = []

    class Configurator:
        @classmethod
        def from_path(cls, path):
            selected.append(path)
            return cls()

        def configure(self):
            return RunnerConfiguration(interpreter=sys.executable, cwd=tmp_path)

    monkeypatch.setattr(command, "ProjectRunnerConfigurator", Configurator)

    assert main(["run", "--project", str(tmp_path), "--", script.name, "a b"]) == 0
    assert selected == [tmp_path]
    assert json.loads(capfd.readouterr().out) == [str(tmp_path), ["a b"]]


# tarav.breadcrumb 70beef8929bb
def test_bare_project_discovers_parent_project(tmp_path: Path, monkeypatch) -> None:
    from tarav.l3 import run as command

    root = tmp_path / "project"
    marker = root / ".tarav" / "project.json"
    marker.parent.mkdir(parents=True)
    marker.write_text(
        json.dumps(
            {
                "project_id": "4e6efc4a-76fd-4585-994e-3d8081e80523",
                "created_at": "2026-10-15T00:00:00Z",
                "harness": {"environment": ".tarav/env", "type": "tarav.l2.project:Project"},
            }
        )
    )
    environment = root / ".tarav" / "env"
    interpreter = environment / "bin" / "python"
    interpreter.parent.mkdir(parents=True)
    interpreter.symlink_to(sys.executable)
    (environment / "pyvenv.cfg").write_text("home = test\n")
    nested = root / "nested" / "deeper"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)
    selected = []
    monkeypatch.setattr(
        command,
        "run_python",
        lambda arguments, *, configuration: selected.append((arguments, configuration)) or 0,
    )

    assert main(["run", "--project", "--", "-c", "import os; print(os.getcwd())"]) == 0
    assert selected[0][0] == ["-c", "import os; print(os.getcwd())"]
    assert selected[0][1].cwd == root
    assert selected[0][1].interpreter == interpreter


def test_bare_project_fails_outside_project(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)

    assert main(["run", "--project", "--", "-c", "print(1)"]) == 1
    assert "not inside a tarav project" in capsys.readouterr().err


def test_run_without_project_uses_current_environment_inside_project(
    tmp_path: Path, monkeypatch, capfd
) -> None:
    from tarav.l3 import run as command

    marker = tmp_path / ".tarav" / "project.json"
    marker.parent.mkdir()
    marker.write_text(
        json.dumps(
            {
                "project_id": "4e6efc4a-76fd-4585-994e-3d8081e80523",
                "created_at": "2026-10-15T00:00:00Z",
                "harness": {"environment": ".tarav/env", "type": "tarav.l2.project:Project"},
            }
        )
    )
    monkeypatch.chdir(tmp_path)

    class UnexpectedProjectConfigurator:
        @classmethod
        def from_path(cls, path):
            raise AssertionError("project selection must be explicit")

    monkeypatch.setattr(command, "ProjectRunnerConfigurator", UnexpectedProjectConfigurator)
    assert main(["run", "--", "-c", "import sys; print(sys.executable)"]) == 0
    assert capfd.readouterr().out.strip() == sys.executable


def test_run_supports_python_module_and_stdin(tmp_path: Path, monkeypatch, capfd) -> None:
    module = tmp_path / "probe_module.py"
    module.write_text("import sys; print(sys.argv[1:])\n")
    monkeypatch.chdir(tmp_path)

    assert main(["run", "--", "-m", "probe_module", "--flag"]) == 0
    assert capfd.readouterr().out.strip() == "['--flag']"

    child = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from tarav.l3.cli.cli import main; raise SystemExit(main(sys.argv[1:]))",
            "run", "--", "-",
        ],
        input="print('from stdin')\n",
        capture_output=True,
        text=True,
        check=False,
    )
    assert child.returncode == 0, child.stderr
    assert child.stdout.strip() == "from stdin"


@pytest.mark.parametrize("arguments", [["run"], ["run", "script.py"], ["run", "--"]])
def test_run_requires_nonempty_python_arguments_after_separator(arguments, capsys) -> None:
    assert main(arguments) == 1
    assert "after --" in capsys.readouterr().err


def test_duplicate_run_leaves_are_removed() -> None:
    parser = build_parser()
    for arguments in (["python", "run"], ["project", "harness", "run"]):
        with pytest.raises(SystemExit):
            parser.parse_args(arguments)
