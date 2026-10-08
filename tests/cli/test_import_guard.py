"""The two import doors and their inherited process context."""

import os
import subprocess
import sys
from pathlib import Path


def _python(source: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.pop("_TARAV_IMPORT_ENTRY", None)
    return subprocess.run([sys.executable, "-c", source], env=environment,
                          capture_output=True, text=True, check=False)


# tarav.breadcrumb ef4fff2d8e46c0d99d286f6bbda3c6fa6e1023bcb54fd1451d2a8e8bdc2b348e
def test_plain_import_errors_with_the_run_route() -> None:
    result = _python("import tarav")
    assert result.returncode != 0
    assert "TaravImportError" in result.stderr
    assert "tarav run -- <script>" in result.stderr
    assert "tarav run --project -- <script>" in result.stderr
    assert "_TARAV_IMPORT_ENTRY" not in result.stderr
    assert "tarav_bypass" not in result.stderr


def test_bypass_opens_the_same_library_without_importing_it_early() -> None:
    result = _python("import sys, tarav_bypass; "
                     "assert 'tarav' not in sys.modules; "
                     "import tarav; print(tarav.__version__)")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "0.1.0"


def test_marked_parent_allows_child_import() -> None:
    result = _python("import tarav_bypass, subprocess, sys; "
                     "p=subprocess.run([sys.executable, '-c', 'import tarav'], "
                     "check=False); raise SystemExit(p.returncode)")
    assert result.returncode == 0, result.stderr


def test_cli_door_marks_the_run_child() -> None:
    environment = os.environ.copy()
    environment.pop("_TARAV_IMPORT_ENTRY", None)
    command = Path(sys.executable).with_name("tarav")
    result = subprocess.run(
        [str(command), "run", "--", "-c", "import tarav; print(tarav.__version__)"],
        env=environment, capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "0.1.0"
