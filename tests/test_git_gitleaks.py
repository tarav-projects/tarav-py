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


def test_the_cli_scans_and_registers_on_the_owner(repo: Path, tmp_path: Path, monkeypatch,
                                                   capsys) -> None:
    from tarav.l3.cli.cli import main
    from tarav.l3.runtime import create_runtime, set_runtime

    monkeypatch.setenv("TARAV_RECORDS", str(tmp_path / "records"))
    set_runtime(create_runtime())
    system = tmp_path / "system"
    _marker(system, "5b1d6c2e-3f4a-4b8c-9d0e-1f2a3b4c5d6e")
    monkeypatch.setattr("tarav.l1.git.gitleaks.system_project_root", lambda: system)
    try:
        _commit_token(repo)
        assert main(["git", "gitleaks", "scan", "--repo", str(repo), "--json"]) == 0
    finally:
        set_runtime(None)
    report = json.loads(capsys.readouterr().out)
    assert (report["kind"], report["findings"], report["actions_changed"]) == ("history", 1, 1)
    assert report["owner"]["root"] == str(system)


# --- verification, POIs and actions (slice 2)

from tarav.l1.actions import CLOSED, RUNNING  # noqa: E402
from tarav.l1.actions.blessing import BLESSED, BlessingInput  # noqa: E402
from tarav.l1.actions.pois import action_id  # noqa: E402
from tarav.l1.checks import CheckSuite  # noqa: E402
from tarav.l1.git.gitleaks import (  # noqa: E402
    GitleaksCheck, GitleaksFinding, GitleaksNeverScanned, owner_of, register_run,
)
from tarav.l3.runtime import create_runtime  # noqa: E402

from test_actions_workflow import Stores  # noqa: E402


@pytest.fixture
def stores(tmp_path):
    return Stores(tmp_path / "records", create_runtime().records)


def _pois(root: Path):
    return list(GitleaksCheck(root).run().pois())


def test_a_reported_finding_still_in_history_raises_one_poi(repo: Path) -> None:
    assert [type(poi) for poi in _pois(repo)] == [GitleaksNeverScanned]
    commit = _commit_token(repo)
    run_gitleaks(repo)
    (poi,) = _pois(repo)
    assert isinstance(poi, GitleaksFinding)
    assert poi.situation["repository"] == repository_key(repo)
    assert poi.details["commit"] == commit


def test_findings_go_when_ignored_rewritten_away_or_no_longer_reported(repo: Path) -> None:
    _commit_token(repo)
    (finding,) = GitleaksDepot().report(run_gitleaks(repo))
    (repo / ".gitleaksignore").write_text(finding["Fingerprint"] + "\n", encoding="utf-8")
    assert _pois(repo) == []
    (repo / ".gitleaksignore").unlink()
    assert len(_pois(repo)) == 1

    _git(repo, "reset", "-q", "--hard", "HEAD~1")
    _git(repo, "reflog", "expire", "--expire=now", "--all")
    _git(repo, "gc", "-q", "--prune=now")
    assert _pois(repo) == []  # the commit is no longer reachable

    _commit_token(repo, "other.py")
    run_gitleaks(repo)
    assert len(_pois(repo)) == 1
    (repo / "other.py").write_text("clean\n", encoding="utf-8")
    _git(repo, "commit", "-qam", "Clean")
    assert len(_pois(repo)) == 1  # still in history
    # a later report that no longer lists it: here, one taken while it was ignored
    (only,) = GitleaksDepot().report(run_gitleaks(repo))
    (repo / ".gitleaksignore").write_text(only["Fingerprint"] + "\n", encoding="utf-8")
    run_gitleaks(repo)
    (repo / ".gitleaksignore").unlink()
    assert _pois(repo) == []


def test_blessing_appends_the_fingerprint_and_closes_the_action(repo: Path, stores) -> None:
    _commit_token(repo)
    run = run_gitleaks(repo)
    owner = {"id": "test-owner", "name": "test-owner", "root": str(repo)}
    first = stores.update(owner, CheckSuite([GitleaksCheck(repo)], name="gitleaks").run())
    assert first["opened"] == 1
    (poi,) = _pois(repo)
    reason = stores.contexts.put(BlessingInput.new(reason="A test token."))
    stores.runner.close(str(action_id(poi)), reason, exit=BLESSED)
    (finding,) = GitleaksDepot().report(run)
    assert (repo / ".gitleaksignore").read_text(encoding="utf-8") == finding["Fingerprint"] + "\n"
    stores.update(owner, CheckSuite([GitleaksCheck(repo)], name="gitleaks").run())
    assert [(item.state, item.exit) for item in stores.runs.list()] == [(CLOSED, BLESSED)]


def _marker(root: Path, project_id: str) -> None:
    (root / ".tarav").mkdir(parents=True, exist_ok=True)
    (root / ".tarav" / "project.json").write_text(json.dumps(
        {"project_id": project_id, "created_at": "2026-10-18T00:00:00Z"}), encoding="utf-8")


def test_owner_is_the_enclosing_project_or_the_system_project(repo: Path, tmp_path: Path,
                                                                stores) -> None:
    system = tmp_path / "system"
    _marker(system, "5b1d6c2e-3f4a-4b8c-9d0e-1f2a3b4c5d6e")
    assert owner_of(repo, system=system) == {"id": "5b1d6c2e-3f4a-4b8c-9d0e-1f2a3b4c5d6e", "name": "system",
                                             "root": str(system)}
    _commit_token(repo)
    changed = register_run(repo, run_gitleaks(repo), system=system, runs=stores.runs)
    assert len(changed) == 1
    assert stores.runs.list(state=RUNNING)[0].data["project"]["id"] == "5b1d6c2e-3f4a-4b8c-9d0e-1f2a3b4c5d6e"

    _marker(repo.parent, "7c2e8d3f-4a5b-4c9d-8e0f-2a3b4c5d6e7f")
    assert owner_of(repo, system=system)["id"] == "7c2e8d3f-4a5b-4c9d-8e0f-2a3b4c5d6e7f"


def test_the_system_project_checks_scanned_repositories_no_project_owns(repo: Path) -> None:
    from tarav.l1.git.gitleaks import unowned_checks

    _commit_token(repo)
    run_gitleaks(repo)
    assert [check.root for check in unowned_checks()] == [repo.resolve()]
    _marker(repo.parent, "7c2e8d3f-4a5b-4c9d-8e0f-2a3b4c5d6e7f")
    assert unowned_checks() == []
