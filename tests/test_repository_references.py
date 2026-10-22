"""Repository declarations, explicit Git consumption and Change-ID recovery."""
# tarav.breadcrumb 518279c0d1c0

import json
import os
import subprocess
import uuid

import pytest

from tarav.l0.kernel import TaravObject, TypeRegistry
from tarav.l1.archive import Archive
from tarav.l1.archive.model import DOI_RECORD_TYPES, LocalLocator, RepositoryDOI
from tarav.l1.archive.references import DOIReference, RepositoryReference
from tarav.l1.git.change import TaravChangeBindingMissing, TaravChangeCheck, ids_at
from tarav.l1.git.hooks import install
from tarav.l1.git.witness import ChangeWitnesses
from tarav.l2.git.archive import capture_repository, install_repository_hooks, resolve_repository
from tarav.l3.runtime import create_runtime


def git(root, *args, input=None):
    return subprocess.run(["git", "-C", str(root), *args], input=input,
                          text=True, capture_output=True, check=True).stdout.strip()


def initialize(root):
    root.mkdir()
    git(root, "init", "-qb", "main")
    git(root, "config", "user.name", "Test")
    git(root, "config", "user.email", "test@example.org")


@pytest.fixture
def recorded(tmp_path, monkeypatch):
    create_runtime()
    monkeypatch.setenv("TARAV_GIT_CHANGES_ROOT", str(tmp_path / "witness"))
    monkeypatch.setenv("TARAV_RECORDS", str(tmp_path / "records"))
    root = tmp_path / "repo"
    initialize(root)
    (root / "payload").write_text("captured content")
    (root / ".tarav").mkdir()
    change = str(uuid.uuid4())
    (root / ".tarav/changes").write_text(change + "\n")
    git(root, "add", ".")
    git(root, "commit", "-qm", f"Capture\n\ntarav-change: {change}")
    archive = Archive.create(tmp_path / "registry")
    doi = archive.register(RepositoryDOI(locators=[LocalLocator(root)]))
    reference = capture_repository(DOIReference(doi.id, registry=archive.root), root, path="payload")
    return root, archive, doi, reference


def replace_history(root, reference, *, message="Rewritten", tree=None):
    locator = reference.locator
    rewritten = git(root, "commit-tree", tree or locator["tree"],
                    input=f"{message}\n\ntarav-change: {locator['change_id']}\n")
    git(root, "update-ref", "refs/heads/main", rewritten)
    git(root, "reflog", "expire", "--expire=now", "--all")
    git(root, "gc", "--prune=now")
    return rewritten


def test_declaration_lookup_needs_no_external_resource_and_relocation_works(recorded, tmp_path):
    root, archive, doi, reference = recorded
    moved = tmp_path / "moved"
    root.rename(moved)
    assert reference.resolve().target.repository.id == doi.id
    assert not resolve_repository(reference).ok
    doi.locators = [LocalLocator(moved)]
    archive.update(doi)
    result = resolve_repository(reference)
    assert result.ok and result.target.repository == moved
    assert result.target.content == b"captured content"
    assert not result.target.recovered


def test_equivalent_rewritten_tree_is_recovered_but_original_is_not_retargeted(recorded):
    root, _, _, reference = recorded
    original = reference.locator["commit"]
    rewritten = replace_history(root, reference)
    assert rewritten != original
    result = resolve_repository(reference)
    assert result.ok and result.target.recovered
    assert result.target.commit == rewritten
    assert result.target.content == b"captured content"
    assert reference.locator["commit"] == original


def test_shared_change_id_does_not_accept_a_changed_tree(recorded):
    root, _, _, reference = recorded
    (root / "payload").write_text("different content")
    git(root, "add", "payload")
    tree = git(root, "write-tree")
    replace_history(root, reference, tree=tree)
    result = resolve_repository(reference)
    assert result.status == "mismatch"
    assert result.target is None


def test_ambiguous_equivalent_candidates_are_not_silently_selected(recorded):
    root, _, _, reference = recorded
    first = replace_history(root, reference)
    second = git(root, "commit-tree", reference.locator["tree"],
                 input=f"Another candidate\n\ntarav-change: {reference.locator['change_id']}\n")
    git(root, "update-ref", "refs/heads/other", second)
    result = resolve_repository(reference)
    assert result.status == "unresolvable"
    assert "Ambiguous" in result.message
    assert set(result.hints["commits"]) == {first, second}


def test_older_commits_without_a_marker_do_not_borrow_ancestor_markers(recorded):
    root, archive, doi, _ = recorded
    (root / "new").write_text("unmarked change")
    git(root, "add", "new")
    git(root, "commit", "-qm", "No marker on this commit")
    assert ids_at(root, "HEAD") == ()
    ref = capture_repository(DOIReference(doi.id, registry=archive.root), root)
    assert "change_id" not in ref.locator
    assert resolve_repository(ref).ok


def test_exact_commit_with_wrong_tree_is_rejected(recorded):
    _, _, _, ref = recorded
    record = ref.records.to_record()
    record["locator"]["tree"] = "0" * 40
    result = resolve_repository(RepositoryReference(record))
    assert result.status == "mismatch" and result.target is None


def test_reference_round_trip_uses_custom_registry(recorded):
    _, archive, doi, reference = recorded
    records = TypeRegistry(TaravObject, (*DOI_RECORD_TYPES, DOIReference, RepositoryReference))
    loaded = records.from_record(reference.records.to_record())
    assert loaded.resolve().target.repository.id == doi.id
    assert loaded.records.to_record() == reference.records.to_record()
    assert archive.read(doi.id).id == doi.id


def test_unbound_change_hooks_report_missing_repository_identity(recorded):
    root, _, _, _ = recorded
    install(root, add=["tarav-change"])
    assert any(isinstance(poi, TaravChangeBindingMissing)
               for poi in TaravChangeCheck(root).run().pois())


def test_two_non_project_repositories_share_owner_without_sharing_witness(tmp_path, monkeypatch):
    create_runtime()
    monkeypatch.setenv("TARAV_RECORDS", str(tmp_path / "records"))
    monkeypatch.setenv("TARAV_GIT_CHANGES_ROOT", str(tmp_path / "witness"))
    owner = tmp_path / "owner"
    (owner / ".tarav").mkdir(parents=True)
    project_id = "20c26be7-a8e5-4974-9ec0-0b5a3a125a94"
    (owner / ".tarav/project.json").write_text(json.dumps({
        "type": "Tarav.Project", "project_id": project_id, "created_at": "2026-10-16T00:00:00Z"}))
    bindings = []
    for name in ["first", "second"]:
        root = tmp_path / name
        initialize(root)
        install_repository_hooks(root, add=["tarav-change"], owner=owner)
        git(root, "add", ".")
        git(root, "commit", "-qm", name)
        assert not (root / ".tarav/project.json").exists()
        binding = json.loads((root / ".tarav/config.json").read_text())["git"]["repository"]
        witness = ChangeWitnesses().get(binding, "main")
        assert witness.project == project_id and len(witness.changes) == 1
        bindings.append(binding)
    assert bindings[0] != bindings[1]
    # Hook signals route to that owner, whose normal status loop rechecks them.
    first = tmp_path / "first"
    retained = (first / ".tarav/changes").read_text()
    (first / ".tarav/changes").write_text("")
    stopped = subprocess.run(["git", "-C", str(first), "commit", "-qam", "Drops identity"],
                             capture_output=True, text=True)
    assert stopped.returncode != 0
    from tarav.l2.project import Project
    project = Project.from_path(owner)
    actions = [run for run in project.actions.list()
               if run.data["event"]["poi"]["type"] == "Tarav.Git.Change.Removed"]
    assert len(actions) == 1 and actions[0].state == "running"
    assert actions[0].data["event"]["poi"]["situation"]["repository"] == bindings[0]
    (first / ".tarav/changes").write_text(retained)
    project.status()
    updated = next(run for run in project.actions.list() if run.id == actions[0].id)
    assert updated.state == "closed" and updated.exit == "gone"


def test_cli_can_install_on_non_project_repository(tmp_path, monkeypatch):
    create_runtime()
    monkeypatch.setenv("TARAV_RECORDS", str(tmp_path / "records"))
    monkeypatch.setenv("TARAV_GIT_CHANGES_ROOT", str(tmp_path / "witness"))
    owner = tmp_path / "owner"
    (owner / ".tarav").mkdir(parents=True)
    (owner / ".tarav/project.json").write_text(json.dumps({
        "project_id": str(uuid.uuid4()), "created_at": "2026-10-16T00:00:00Z"}))
    root = tmp_path / "repo"
    initialize(root)
    result = subprocess.run(["tarav", "git", "hooks", "install", "--repo", str(root),
                             "--owner-project", str(owner), "--handler", "tarav-change", "--json"],
                            capture_output=True, text=True, env=os.environ.copy())
    assert result.returncode == 0, result.stderr
    assert json.loads((root / ".tarav/config.json").read_text())["git"]["repository"]
