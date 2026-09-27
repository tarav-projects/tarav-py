from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import socket
import subprocess

import pytest

from tarav.l1 import archive as archive_module
from tarav.l1.archive import (
    AmbiguousArtifactError,
    Archive,
    ArchiveWarning,
    ArtifactNotFoundError,
    BranchNotFoundError,
    DuplicateArtifactLocatorError,
    DuplicateArtifactNameError,
    RepositoryLocatorUnavailableError,
    derive_git_artifact_id,
)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ("git", "-C", str(repo), *args),
        capture_output=True,
        check=True,
        text=True,
    )
    return result.stdout.strip()


def _source_repository(
    path: Path,
    *,
    content: str = "hello\n",
    branch: str = "main",
) -> Path:
    path.mkdir(parents=True)
    _git(path, "init", "-q", "-b", branch)
    (path / "nested").mkdir()
    (path / "nested" / "tracked.txt").write_text(content, encoding="utf-8")
    _git(path, "add", "nested/tracked.txt")
    _git(
        path,
        "-c",
        "user.name=Archive Test",
        "-c",
        "user.email=archive-test@example.invalid",
        "commit",
        "-q",
        "-m",
        "initial",
    )
    return path


def _commit_file(repo: Path, path: str, content: str, *, message: str) -> str:
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    _git(repo, "add", "--", path)
    _git(
        repo,
        "-c",
        "user.name=Archive Test",
        "-c",
        "user.email=archive-test@example.invalid",
        "commit",
        "-q",
        "-m",
        message,
    )
    return _git(repo, "rev-parse", "HEAD")


def _json(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _jsonl(path: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        payload = json.loads(line)
        assert isinstance(payload, dict)
        records.append(payload)
    return records


def test_registers_a_repository_as_timestamped_records_and_git_hint(
    tmp_path: Path,
) -> None:
    source = _source_repository(tmp_path / "chatlas")
    first_commit = _git(source, "rev-parse", "HEAD")
    source_files_before = sorted(path.name for path in source.iterdir())
    archive = Archive.create(tmp_path / "tarav-archive")

    repository = archive.register_repository(source, name="tarav.chatlas")

    assert re.fullmatch(r"[0-9a-f]{64}", repository.id)
    assert repository.kind == "git-repository"
    assert repository.name == "tarav.chatlas"
    assert {path.name for path in archive.root.iterdir()} == {"records", "repositories"}
    assert list(archive.repositories_root.iterdir()) == []
    assert _json(archive.records_root / "main.json")["recorded_at"]

    object_root = archive.artifacts_root / repository.id
    assert {path.name for path in object_root.iterdir()} == {
        "main.json",
        "locators.jsonl",
        "git-hint.json",
    }
    assert _json(object_root / "main.json") == {
        "type": "Tarav.Archive.Artifact.Registration.Record",
        "schema_version": 2,
        "id": repository.id,
        "kind": "git-repository",
        "name": "tarav.chatlas",
        "contract": {"kind": "git-repository", "identity": {"method": "issued", "algorithm": "random", "bits": 256}},
        "recorded_at": repository.recorded_at,
        "identity": {
            "method": "issued",
            "algorithm": "random",
            "bits": 256,
        },
    }
    assert _jsonl(object_root / "locators.jsonl") == [
        {
            "type": "Tarav.Archive.Artifact.Locator.Record",
            "schema_version": 2,
            "target": repository.id,
            "recorded_at": repository.recorded_at,
            "kind": "local-path",
            "value": str(source.resolve()),
            "host": socket.gethostname(),
        }
    ]
    git_hint = _json(object_root / "git-hint.json")
    assert git_hint["type"] == "Tarav.Archive.Artifact.GitHint.Record"
    assert git_hint["target"] == repository.id
    assert git_hint["recorded_at"] == repository.recorded_at
    assert git_hint["object_format"] == "sha1"
    assert git_hint["branch"] == "main"
    assert "head" not in git_hint
    assert git_hint["commits"] == [
        {
            "hash": first_commit,
            "raw": git_hint["commits"][0]["raw"],
        }
    ]
    assert "author Archive Test" in git_hint["commits"][0]["raw"]
    assert git_hint["commits"][0]["raw"].endswith("initial\n")

    assert sorted(path.name for path in source.iterdir()) == source_files_before
    assert _git(source, "status", "--porcelain") == ""
    assert _git(archive.records_root, "status", "--porcelain") == ""
    assert _git(archive.records_root, "log", "--format=%s").splitlines() == [
        "archive(artifact): register tarav.chatlas",
        "archive: initialize records",
    ]


def test_git_hint_samples_up_to_ten_commits_across_the_selected_branch(
    tmp_path: Path,
) -> None:
    source = _source_repository(tmp_path / "chatlas")
    commits = [_git(source, "rev-parse", "HEAD")]
    for number in range(1, 13):
        commits.append(
            _commit_file(
                source,
                "nested/tracked.txt",
                f"version {number}\n",
                message=f"commit {number}",
            )
        )
    archive = Archive.create(tmp_path / "tarav-archive")

    repository = archive.register_repository(source, name="tarav.chatlas")
    hint = _json(archive.artifacts_root / repository.id / "git-hint.json")
    samples = hint["commits"]

    assert isinstance(samples, list)
    assert len(samples) == 10
    assert samples[0]["hash"] == commits[0]
    assert samples[-1]["hash"] == commits[-1]
    assert len({sample["hash"] for sample in samples}) == 10
    for sample in samples:
        assert (
            sample["raw"]
            == subprocess.run(
                ("git", "-C", str(source), "cat-file", "commit", sample["hash"]),
                capture_output=True,
                check=True,
                text=True,
            ).stdout
        )


def test_git_hint_preserves_non_utf8_commit_metadata_losslessly(tmp_path: Path) -> None:
    source = _source_repository(tmp_path / "chatlas")
    parent = _git(source, "rev-parse", "HEAD")
    tree = _git(source, "rev-parse", "HEAD^{tree}")
    raw_commit = (
        f"tree {tree}\n"
        f"parent {parent}\n"
        "author Archive Test <archive-test@example.invalid> 0 +0000\n"
        "committer Archive Test <archive-test@example.invalid> 0 +0000\n\n"
    ).encode("ascii") + b"non-utf8 message: \xff\n"
    result = subprocess.run(
        ("git", "-C", str(source), "hash-object", "-t", "commit", "-w", "--stdin"),
        input=raw_commit,
        capture_output=True,
        check=True,
    )
    commit = result.stdout.decode("ascii").strip()
    _git(source, "update-ref", "refs/heads/main", commit)
    archive = Archive.create(tmp_path / "tarav-archive")

    repository = archive.register_repository(source, name="tarav.chatlas")
    hint = _json(archive.artifacts_root / repository.id / "git-hint.json")
    sample = hint["commits"][-1]

    assert sample["hash"] == commit
    assert (
        sample["raw"]
        .encode("utf-8", "surrogateescape")
        .endswith(b"non-utf8 message: \xff\n")
    )


def test_repository_registration_captures_admitted_remotes_and_skips_weird_ones(
    tmp_path: Path,
) -> None:
    source = _source_repository(tmp_path / "chatlas")
    _git(source, "remote", "add", "origin", "https://example.test/owner/chatlas.git")
    _git(
        source,
        "remote",
        "set-url",
        "--add",
        "--push",
        "origin",
        "git@example.test:owner/chatlas.git",
    )
    suspicious = "https://secret-token@example.test/private/chatlas.git"
    _git(source, "remote", "add", "private", suspicious)
    archive = Archive.create(tmp_path / "tarav-archive")

    with pytest.warns(ArchiveWarning) as caught:
        repository = archive.register_repository(source, name="tarav.chatlas")

    warning = str(caught[0].message)
    assert "skipped 1" in warning
    assert "secret-token" not in warning
    assert suspicious not in warning
    locators = _jsonl(archive.artifacts_root / repository.id / "locators.jsonl")
    remotes = [item for item in locators if item["kind"] == "git-remote"]
    assert remotes == [
        {
            "type": "Tarav.Archive.Artifact.Locator.Record",
            "schema_version": 2,
            "target": repository.id,
            "recorded_at": repository.recorded_at,
            "kind": "git-remote",
            "remote": "origin",
            "direction": "fetch",
            "value": "https://example.test/owner/chatlas.git",
        },
        {
            "type": "Tarav.Archive.Artifact.Locator.Record",
            "schema_version": 2,
            "target": repository.id,
            "recorded_at": repository.recorded_at,
            "kind": "git-remote",
            "remote": "origin",
            "direction": "push",
            "value": "git@example.test:owner/chatlas.git",
        },
    ]


def test_repository_branch_is_explicit_and_defaults_to_main(tmp_path: Path) -> None:
    source = _source_repository(tmp_path / "chatlas", branch="trunk")
    archive = Archive.create(tmp_path / "tarav-archive")

    with pytest.raises(BranchNotFoundError, match="main"):
        archive.register_repository(source, name="tarav.chatlas")

    repository = archive.register_repository(
        source, name="tarav.chatlas", branch="trunk"
    )
    hint = _json(archive.artifacts_root / repository.id / "git-hint.json")
    assert hint["branch"] == "trunk"


def test_registers_a_repoless_artifact_and_appends_locator_records(
    tmp_path: Path,
) -> None:
    archive = Archive.create(tmp_path / "tarav-archive")

    video = archive.register_artifact(
        locator="https://www.youtube.com/watch?v=example",
        name="example.video",
        kind="Video",
    )
    assert archive.add_locator(video.id, locator="https://youtu.be/example")
    assert not archive.add_locator(video.id, locator="https://youtu.be/example")

    dossier = archive.dossier("example.video")
    assert dossier.artifact == video
    assert set(dossier.records) == {"main.json", "locators.jsonl"}
    locators = dossier.records["locators.jsonl"]
    assert isinstance(locators, list)
    assert [item["value"] for item in locators] == [
        "https://www.youtube.com/watch?v=example",
        "https://youtu.be/example",
    ]
    assert all(item["recorded_at"] for item in locators)


def test_registration_and_convenience_resolution_are_stable(tmp_path: Path) -> None:
    source = _source_repository(tmp_path / "chatlas")
    archive = Archive.create(tmp_path / "tarav-archive")
    first = archive.register_repository(source, name="tarav.chatlas")
    commits_before = _git(archive.records_root, "rev-list", "--count", "HEAD")

    repeated = Archive.open(archive.root).register_repository(
        source, name="tarav.chatlas"
    )

    assert repeated == first
    assert archive.resolve_repository("tarav.chatlas") == first
    assert archive.resolve_repository(first.id) == first
    assert archive.resolve_repository(first.id[:12]) == first
    assert archive.resolve_repository(source) == first
    assert _git(archive.records_root, "rev-list", "--count", "HEAD") == commits_before


def test_repository_reregistration_is_a_strict_noop(tmp_path: Path) -> None:
    source = _source_repository(tmp_path / "chatlas")
    archive = Archive.create(tmp_path / "tarav-archive")
    repository = archive.register_repository(source, name="tarav.chatlas")
    object_root = archive.artifacts_root / repository.id
    records_before = {
        path.name: path.read_bytes() for path in object_root.iterdir() if path.is_file()
    }
    commits_before = _git(archive.records_root, "rev-list", "--count", "HEAD")
    _git(source, "remote", "add", "origin", "https://example.test/new.git")

    repeated = archive.register_repository(source, name="tarav.chatlas")

    assert repeated == repository
    assert {
        path.name: path.read_bytes() for path in object_root.iterdir() if path.is_file()
    } == records_before
    assert _git(archive.records_root, "rev-list", "--count", "HEAD") == commits_before


def test_registration_rejects_conflicting_names_and_locators(tmp_path: Path) -> None:
    source = _source_repository(tmp_path / "chatlas")
    other = _source_repository(tmp_path / "other")
    archive = Archive.create(tmp_path / "tarav-archive")
    archive.register_repository(source, name="tarav.chatlas")

    with pytest.raises(DuplicateArtifactNameError, match="tarav.chatlas"):
        archive.register_repository(other, name="tarav.chatlas")
    with pytest.raises(DuplicateArtifactLocatorError, match="already registered"):
        archive.register_repository(source, name="renamed.chatlas")


def test_id_prefix_must_be_unambiguous(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ids = iter(("a" * 63 + "1", "a" * 63 + "2"))
    monkeypatch.setattr(archive_module, "_random_artifact_id", lambda: next(ids))
    archive = Archive.create(tmp_path / "tarav-archive")
    archive.register_artifact(locator="https://example.test/one", name="one")
    archive.register_artifact(locator="https://example.test/two", name="two")

    with pytest.raises(AmbiguousArtifactError, match="aaaaaaaa"):
        archive.resolve_artifact("aaaaaaaa")
    with pytest.raises(ArtifactNotFoundError, match="unknown"):
        archive.resolve_artifact("unknown")


def test_materializes_only_requested_git_artifacts_with_deterministic_ids(
    tmp_path: Path,
) -> None:
    source = _source_repository(tmp_path / "chatlas")
    initial_commit = _git(source, "rev-parse", "HEAD")
    changed_commit = _commit_file(
        source,
        "nested/tracked.txt",
        "changed\n",
        message="change file",
    )
    archive = Archive.create(tmp_path / "tarav-archive")
    repository = archive.register_repository(source, name="tarav.chatlas")

    initial = archive.materialize_git_artifact(
        "tarav.chatlas",
        commit=initial_commit,
        path="nested/tracked.txt",
    )
    changed = archive.materialize_git_artifact(
        repository.id[:12],
        commit=changed_commit,
        path="nested/tracked.txt",
    )
    repeated = archive.materialize_git_artifact(
        "tarav.chatlas",
        commit=initial_commit,
        path="nested/tracked.txt",
    )
    folder = archive.materialize_git_artifact(
        "tarav.chatlas",
        commit=changed_commit,
        path="nested",
    )

    assert repeated == initial
    assert initial.id != changed.id
    assert initial.kind == changed.kind == "git-file-version"
    assert folder.kind == "git-folder-version"
    assert initial.id == derive_git_artifact_id(
        repository_id=repository.id,
        object_format="sha1",
        commit=initial_commit,
        path="nested/tracked.txt",
    )
    assert len(list(archive.artifacts_root.iterdir())) == 4
    dossier = archive.dossier(initial.id)
    assert set(dossier.records) == {
        "main.json",
        "locators.jsonl",
        "git-coordinate.json",
    }
    coordinate = dossier.records["git-coordinate.json"]
    assert coordinate["recorded_at"] == initial.recorded_at
    assert coordinate["repository"] == repository.id
    assert coordinate["commit"] == initial_commit
    assert coordinate["path"] == "nested/tracked.txt"
    assert coordinate["object_type"] == "blob"
    assert coordinate["size"] == len("hello\n")
    assert _git(archive.records_root, "status", "--porcelain") == ""


def test_external_descriptors_are_timestamped_attributed_records(
    tmp_path: Path,
) -> None:
    archive = Archive.create(tmp_path / "tarav-archive")
    video = archive.register_artifact(
        locator="https://example.test/video",
        name="video",
        kind="Video",
    )
    transcript = archive.register_artifact(
        locator="https://example.test/transcript",
        name="transcript",
        kind="File",
    )

    first = archive.register_external_descriptor(
        video.id,
        transcript.id,
        attribution="user:pereiro",
    )
    repeated = archive.register_external_descriptor(
        "video",
        "transcript",
        attribution="user:pereiro",
    )

    assert first.created
    assert not repeated.created
    assert repeated.recorded_at == first.recorded_at
    assert archive.dossier(video.id).records["external-descriptors.json"] == {
        "type": "Tarav.Archive.Artifact.ExternalDescriptors.Record",
        "schema_version": 2,
        "target": video.id,
        "recorded_at": first.recorded_at,
        "descriptors": [
            {
                "artifact": transcript.id,
                "attribution": "user:pereiro",
                "recorded_at": first.recorded_at,
            }
        ],
    }


def test_missing_repository_data_leaves_records_inspectable(tmp_path: Path) -> None:
    source = _source_repository(tmp_path / "chatlas")
    archive = Archive.create(tmp_path / "tarav-archive")
    repository = archive.register_repository(source, name="tarav.chatlas")
    source.rename(tmp_path / "moved-chatlas")

    assert archive.dossier(repository.id).artifact == repository
    with pytest.raises(RepositoryLocatorUnavailableError, match="no available"):
        archive.materialize_git_artifact(
            repository.id,
            commit="main",
            path="nested/tracked.txt",
        )


def test_repository_reference_is_flat_cheap_and_does_not_mutate_records(
    tmp_path: Path,
) -> None:
    source = _source_repository(tmp_path / "chatlas")
    remote = "git@example.test:owner/chatlas.git"
    _git(source, "remote", "add", "origin", remote)
    first_commit = _git(source, "rev-list", "--max-parents=0", "main")
    archive = Archive.create(tmp_path / "tarav-archive")
    repository = archive.register_repository(source, name="tarav.chatlas")
    commits_before = _git(archive.records_root, "rev-list", "--count", "HEAD")

    reference = archive.reference_repository(str(source))
    remote_reference = archive.reference_repository(remote)

    from tarav.l1.archive.references import ArchiveReference

    assert reference["locator"]["doi"] == repository.id
    assert reference["check"] == {"contains_commit": first_commit}
    assert reference["hints"] == {"path": str(source), "name": "tarav.chatlas"}
    assert remote_reference["locator"] == reference["locator"]
    assert remote_reference["hints"]["path"] == remote
    assert ArchiveReference(reference).resolve().ok
    assert _git(archive.records_root, "rev-list", "--count", "HEAD") == commits_before


def test_git_file_reference_materializes_one_exact_version(tmp_path: Path) -> None:
    source = _source_repository(tmp_path / "chatlas")
    commit = _git(source, "rev-parse", "HEAD")
    blob = _git(source, "rev-parse", f"{commit}:nested/tracked.txt")
    archive = Archive.create(tmp_path / "tarav-archive")
    repository = archive.register_repository(source, name="tarav.chatlas")

    reference = archive.reference_git_file(
        "tarav.chatlas",
        commit=commit,
        locator="nested/tracked.txt",
    )

    from tarav.l1.archive.references import ArchiveReference

    assert reference["locator"]["doi"] == derive_git_artifact_id(
            repository_id=repository.id,
            object_format="sha1",
            commit=commit,
            path="nested/tracked.txt",
        )
    assert reference["check"] == {"git_oid": blob}
    resolved = ArchiveReference(reference).resolve()
    assert resolved.ok
    assert resolved.target.content == b"hello\n"


def test_repoless_file_reference_tracks_exact_versions_and_reuses_unchanged_bytes(
    tmp_path: Path,
) -> None:
    source = tmp_path / "report.txt"
    source.write_text("first\n", encoding="utf-8")
    archive = Archive.create(tmp_path / "tarav-archive")

    first = archive.reference_file(str(source))
    repeated = archive.reference_file(str(source))

    assert repeated == first
    from tarav.l1.archive.references import ArchiveReference

    assert first["check"] == {"sha256": hashlib.sha256(b"first\n").hexdigest()}
    assert ArchiveReference(first).resolve().ok
    dossier = archive.dossier(str(first["locator"]["doi"]))
    assert dossier.artifact.kind == "file-version"
    assert dossier.records["file-version.json"] == {
        "type": "Tarav.Archive.Artifact.FileVersion.Record",
        "schema_version": 2,
        "target": first["locator"]["doi"],
        "recorded_at": first["hints"]["recorded_at"],
        "sha256": first["check"]["sha256"],
        "size": len("first\n"),
    }

    source.write_text("second\n", encoding="utf-8")
    second = archive.reference_file(str(source))

    assert second["locator"]["doi"] != first["locator"]["doi"]
    assert second["check"]["sha256"] == hashlib.sha256(b"second\n").hexdigest()
    assert not ArchiveReference(first).resolve().ok
    assert ArchiveReference(second).resolve().ok
