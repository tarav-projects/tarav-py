from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from tarav.l0.kernel import entity
from tarav.l1.breadcrumbs import BreadcrumbStore
from tarav.l1.chatlas.references import ChatlasTurnReference
from tarav.l1.git import GitError, GitRepository
from tarav.l1.references.git import (
    GitCommitMessagePositionReference,
    GitCommitMessagePositionTarget,
)
from tarav.l2.breadcrumb_workflows.chatlas_context import (
    ChatlasContextBreadcrumbWorkflow,
    ChatlasContextRequest,
)
from tarav.l2.git.breadcrumbs import (
    CommitEvidenceError,
    CommitManifest,
    audit_commit,
    commit_from_manifest,
    prepare_message,
    register_commit,
)
from tarav.l3.cli.cli import main


IDENTITY = "12345678" + "0" * 56
TURN_ADDRESS = "e" * 64
TURN_HASH = "d" * 64


def _git(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _repository(path: Path) -> Path:
    path.mkdir()
    _git(path, "init", "-q")
    _git(path, "config", "user.name", "Test")
    _git(path, "config", "user.email", "test@example.com")
    (path / "selected.txt").write_text("original\n", encoding="utf-8")
    (path / "other.txt").write_text("original\n", encoding="utf-8")
    _git(path, "add", ".")
    _git(path, "commit", "-qm", "initial")
    return path


def _turn_reference() -> dict[str, object]:
    return {
        "type": entity(ChatlasTurnReference).name,
        "locator": {
            "session_identity": IDENTITY,
            "turn_address": TURN_ADDRESS,
            "turn_hash": TURN_HASH,
        },
    }


def _request() -> ChatlasContextRequest:
    return ChatlasContextRequest(resolver=lambda _alias, _prefix: _turn_reference())


def _manifest(repository: Path, *, files: list[str] | None = None) -> CommitManifest:
    return CommitManifest.from_record(
        {
            "type": entity(CommitManifest).name,
            "repository": str(repository),
            "files": files if files is not None else ["selected.txt"],
            "message": (
                "Evidence commit\n\n"
                "- selected.txt: supported change\n"
                f"<!-- tarav.context {IDENTITY[:8]}:{TURN_HASH[:12]} -->"
            ),
        }
    )


def test_repository_commits_only_selected_paths_and_preserves_other_staging(tmp_path):
    repository = _repository(tmp_path / "repository")
    (repository / "selected.txt").write_text("selected\n", encoding="utf-8")
    (repository / "other.txt").write_text("staged\n", encoding="utf-8")
    _git(repository, "add", "other.txt")

    commit = GitRepository(repository).commit(
        ["selected.txt"],
        "Scoped commit\n\n- selected.txt: change\n"
        "<!-- tarav.evidence agent-initiated -->",
    )

    assert _git(repository, "show", "--format=", "--name-only", commit) == "selected.txt"
    assert _git(repository, "status", "--short") == "M  other.txt"


def test_commit_message_reference_keeps_the_exact_commit(tmp_path):
    repository = _repository(tmp_path / "repository")
    first = _git(repository, "rev-parse", "HEAD")
    reference = GitCommitMessagePositionReference(
        repository=repository,
        commit=first,
        line=1,
    )
    (repository / "selected.txt").write_text("later\n", encoding="utf-8")
    _git(repository, "add", "selected.txt")
    _git(repository, "commit", "-qm", "later")

    result = reference.resolve()
    assert result.ok
    assert isinstance(result.target, GitCommitMessagePositionTarget)
    assert result.target.commit == first
    assert result.target.text == "initial"

    loaded = GitCommitMessagePositionReference.from_record(reference.to_record())
    assert loaded.resolve().target.commit == first


def test_manifest_flow_registers_before_commit_and_observes_after(tmp_path):
    repository = _repository(tmp_path / "repository")
    store = BreadcrumbStore(tmp_path / "breadcrumbs")
    (repository / "selected.txt").write_text("changed\n", encoding="utf-8")

    result = commit_from_manifest(
        _manifest(repository),
        store=store,
        workflow=ChatlasContextBreadcrumbWorkflow(),
        request=_request(),
    )

    assert len(result.breadcrumb_ids) == 1
    breadcrumb_id = result.breadcrumb_ids[0]
    shown = store.show(breadcrumb_id)
    assert len(shown["attachments"]) == 1
    assert len(shown["observations"]) == 1
    assert shown["observations"][0]["locator"]["locator"]["commit"] == result.commit
    resolution = store.resolve(breadcrumb_id)
    assert resolution.ok
    assert isinstance(resolution.position, GitCommitMessagePositionTarget)
    _, message = GitRepository(repository).commit_message(result.commit)
    assert f"tarav.breadcrumb {breadcrumb_id}" in message
    assert "tarav.commit-evidence" in message
    assert "tarav.context" not in message


def test_existing_commit_registration_recovers_and_is_idempotent(tmp_path):
    repository = _repository(tmp_path / "repository")
    first_store = BreadcrumbStore(tmp_path / "first-breadcrumbs")
    (repository / "selected.txt").write_text("changed\n", encoding="utf-8")
    committed = commit_from_manifest(
        _manifest(repository),
        store=first_store,
        workflow=ChatlasContextBreadcrumbWorkflow(),
        request=_request(),
    )
    recovered_store = BreadcrumbStore(tmp_path / "recovered-breadcrumbs")

    first = register_commit(repository, committed.commit, store=recovered_store)
    second = register_commit(repository, committed.commit, store=recovered_store)

    assert first == second
    shown = recovered_store.show(first.breadcrumb_ids[0])
    assert len(shown["attachments"]) == 1
    assert len(shown["observations"]) == 1


def test_git_failure_leaves_registered_unobserved_breadcrumb(tmp_path):
    repository = _repository(tmp_path / "repository")
    store = BreadcrumbStore(tmp_path / "breadcrumbs")

    with pytest.raises(GitError, match="no changes"):
        commit_from_manifest(
            _manifest(repository),
            store=store,
            workflow=ChatlasContextBreadcrumbWorkflow(),
            request=_request(),
        )

    records = tuple((store.records_root).iterdir())
    assert len(records) == 1
    shown = store.show(records[0].name)
    assert len(shown["attachments"]) == 1
    assert shown["observations"] == []


def test_malformed_message_is_rejected_before_registration(tmp_path):
    repository = _repository(tmp_path / "repository")
    store = BreadcrumbStore(tmp_path / "breadcrumbs")
    manifest = _manifest(repository)
    assert manifest._record is not None
    manifest._record["message"] = (
        "Bad\n\n<!-- tarav.context 12345678:dddddddd -->"
    )

    with pytest.raises(CommitEvidenceError, match="preceding '- ' group"):
        prepare_message(
            manifest,
            store=store,
            workflow=ChatlasContextBreadcrumbWorkflow(),
            request=_request(),
        )

    assert not store.root.exists()


def test_commit_audit_accepts_registered_chatlas_evidence(tmp_path, monkeypatch):
    repository = _repository(tmp_path / "repository")
    store = BreadcrumbStore(tmp_path / "breadcrumbs")
    (repository / "selected.txt").write_text("changed\n", encoding="utf-8")
    committed = commit_from_manifest(
        _manifest(repository),
        store=store,
        workflow=ChatlasContextBreadcrumbWorkflow(),
        request=_request(),
    )
    monkeypatch.setattr(
        "tarav.l2.breadcrumb_workflows.chatlas_context.workflow.compute_normal_model",
        lambda **_kwargs: {
            "turns": [
                {
                    "type": "Chat.Turn",
                    "turn_address": TURN_ADDRESS,
                    "turn_hash": TURN_HASH,
                    "side": "user",
                    "message_refs": [],
                    "event_refs": [
                        {"event_address": "a" * 64, "event_hash": "b" * 64}
                    ],
                }
            ]
        },
    )

    audit = audit_commit(
        repository,
        committed.commit,
        store=store,
        workflow=ChatlasContextBreadcrumbWorkflow(),
        request=ChatlasContextRequest(),
    )

    assert audit.ok
    assert len(audit.context.breadcrumbs) == 1


def test_manifest_file_load_resolves_relative_repository(tmp_path):
    repository = _repository(tmp_path / "repository")
    manifest_path = repository / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "type": entity(CommitManifest).name,
                "repository": ".",
                "files": [],
                "message": (
                    "Checkpoint\n\n- scope: empty checkpoint\n"
                    "<!-- tarav.evidence agent-initiated -->"
                ),
                "allow_empty": True,
            }
        ),
        encoding="utf-8",
    )

    assert CommitManifest.load(manifest_path).repository_path == repository


def test_cli_commit_register_and_audit_marker_only_evidence(tmp_path, capsys):
    repository = _repository(tmp_path / "repository")
    breadcrumbs = tmp_path / "breadcrumbs"
    recovered = tmp_path / "recovered"
    (repository / "selected.txt").write_text("changed\n", encoding="utf-8")
    manifest_path = repository / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "type": entity(CommitManifest).name,
                "repository": ".",
                "files": ["selected.txt"],
                "message": (
                    "CLI evidence commit\n\n"
                    "- selected.txt: agent-selected change\n"
                    "<!-- tarav.evidence agent-initiated -->"
                ),
            }
        ),
        encoding="utf-8",
    )

    assert main(
        [
            "git",
            "commit",
            "--manifest",
            str(manifest_path),
            "--breadcrumbs-root",
            str(breadcrumbs),
            "--json",
        ]
    ) == 0
    committed = json.loads(capsys.readouterr().out)

    assert main(
        [
            "breadcrumbs",
            "register-commit",
            "--repo",
            str(repository),
            "--commit",
            committed["commit"],
            "--breadcrumbs-root",
            str(recovered),
            "--json",
        ]
    ) == 0
    registered = json.loads(capsys.readouterr().out)
    assert registered["commit"] == committed["commit"]

    assert main(
        [
            "breadcrumbs",
            "audit",
            "chatlas-context",
            "--repo",
            str(repository),
            "--commit",
            committed["commit"],
            "--breadcrumbs-root",
            str(recovered),
            "--json",
        ]
    ) == 0
    audited = json.loads(capsys.readouterr().out)
    assert audited["status"] == "ok"
