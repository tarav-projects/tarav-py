"""The gitleaks workflow: runs and their depot, verified findings, the hook (request 920)."""

from __future__ import annotations

import json
import random
import shutil
import string
import subprocess
from pathlib import Path

import pytest

from tarav.l1.git.gitleaks import GitleaksDepot, repository_key, run_gitleaks

pytestmark = pytest.mark.skipif(shutil.which("gitleaks") is None, reason="gitleaks is not installed")


def _token() -> str:
    """A GitHub-token-shaped string, built at run time so no literal secret is committed."""
    return "ghp_" + "".join(random.choices(string.ascii_letters + string.digits, k=36))


def _git(root: Path, *arguments: str) -> str:
    return subprocess.run(["git", "-C", str(root), *arguments], check=True,
                          capture_output=True, text=True).stdout


@pytest.fixture
def repo(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("TARAV_GITLEAKS_ROOT", str(tmp_path / "depot"))
    monkeypatch.delenv("TARAV_GIT_HOOKS_OVERRULE", raising=False)
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    (root / "README.md").write_text("A repository.\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(root, "commit", "-q", "-m", "First")
    return root


def _commit_token(root: Path, name: str = "config.py") -> str:
    (root / name).write_text(f'TOKEN = "{_token()}"\n', encoding="utf-8")
    _git(root, "add", name)
    _git(root, "commit", "-q", "-m", f"Add {name}")
    return _git(root, "rev-parse", "HEAD").strip()


def test_a_history_run_keeps_the_report_as_gitleaks_wrote_it(repo: Path) -> None:
    commit = _commit_token(repo)
    run = run_gitleaks(repo)
    first = _git(repo, "rev-list", "--max-parents=0", "HEAD").strip()
    assert (run.key, run.kind, run.findings) == (first, "history", 1)
    assert repository_key(repo) == first

    depot = GitleaksDepot()
    (finding,) = depot.report(run)
    assert (finding["Commit"], finding["File"], finding["StartLine"]) == (commit, "config.py", 1)
    assert finding["Secret"] == "REDACTED"
    assert depot.latest(first).id == run.id


def test_ignored_fingerprints_are_not_reported(repo: Path) -> None:
    _commit_token(repo)
    (finding,) = GitleaksDepot().report(run_gitleaks(repo))
    (repo / ".gitleaksignore").write_text(finding["Fingerprint"] + "\n", encoding="utf-8")
    assert run_gitleaks(repo).findings == 0


def test_the_cli_scans_a_repository(repo: Path, capsys) -> None:
    from tarav.l3.cli.cli import main

    _commit_token(repo)
    assert main(["git", "gitleaks", "scan", "--repo", str(repo), "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert (report["kind"], report["findings"]) == ("history", 1)
