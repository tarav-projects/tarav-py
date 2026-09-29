from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from tarav.l3.cli.cli import main
from tarav.l1.python_env import environment_root, interpreter


def test_the_reported_interpreter_is_the_one_running_tarav() -> None:
    assert interpreter() == Path(sys.executable)
    assert environment_root() == Path(sys.prefix)


def test_path_prints_the_interpreter_for_shell_substitution(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["python", "path"]) == 0

    assert capsys.readouterr().out.strip() == sys.executable


def test_path_json_describes_the_environment(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["python", "path", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["status"] == "ok"
    assert payload["command"] == "tarav python path"
    assert payload["interpreter"] == sys.executable
    assert payload["prefix"] == sys.prefix
    assert payload["version"] == ".".join(str(part) for part in sys.version_info[:3])


def test_run_file_executes_a_script_that_can_import_tarav(
    tmp_path: Path,
    capfd: pytest.CaptureFixture[str],
) -> None:
    script = tmp_path / "probe.py"
    script.write_text(
        "import sys, tarav\nprint(tarav.__version__)\nprint(sys.argv[1:])\n",
        encoding="utf-8",
    )

    assert main(["python", "run", "--file", str(script), "--", "--flag", "value"]) == 0
    out = capfd.readouterr().out

    assert "['--flag', 'value']" in out


def test_run_src_executes_source_without_a_file(
    capfd: pytest.CaptureFixture[str],
) -> None:
    assert (
        main(["python", "run", "--src", "import tarav; print(tarav.__version__)"]) == 0
    )

    assert capfd.readouterr().out.strip() != ""


def test_run_src_receives_its_own_arguments(
    capfd: pytest.CaptureFixture[str],
) -> None:
    assert (
        main(["python", "run", "--src", "import sys; print(sys.argv[1:])", "--", "-v"])
        == 0
    )

    assert "['-v']" in capfd.readouterr().out


def test_run_file_reads_the_script_from_standard_input(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from tarav.l3.cli.cli import main; raise SystemExit(main(sys.argv[1:]))",
            "python",
            "run",
            "--file",
            "-",
        ],
        input="import tarav; print('from stdin')\n",
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "from stdin" in result.stdout


def test_run_forwards_the_scripts_exit_code(tmp_path: Path) -> None:
    script = tmp_path / "fails.py"
    script.write_text("raise SystemExit(3)\n", encoding="utf-8")

    assert main(["python", "run", "--file", str(script)]) == 3


def test_run_requires_a_script_to_run() -> None:
    with pytest.raises(SystemExit):
        main(["python", "run"])


def test_run_does_not_claim_script_arguments_without_a_separator(
    tmp_path: Path,
) -> None:
    script = tmp_path / "probe.py"
    script.write_text("print('unreachable')\n", encoding="utf-8")

    with pytest.raises(SystemExit):
        main(["python", "run", "--file", str(script), "--limit", "5"])
