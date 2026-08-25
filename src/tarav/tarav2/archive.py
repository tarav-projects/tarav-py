"""Flat Archive Records for root and Git-contained Artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import secrets
import socket
import subprocess
from urllib.parse import urlsplit
import warnings

from tarav._core.persistence import atomic_write_json, atomic_write_text


ARCHIVE_CLASS = "Tarav.Archive"
REGISTRATION_CLASS = "Tarav.Archive.Artifact.Registration.Record"
LOCATOR_CLASS = "Tarav.Archive.Artifact.Locator.Record"
GIT_HINT_CLASS = "Tarav.Archive.Artifact.GitHint.Record"
GIT_COORDINATE_CLASS = "Tarav.Archive.Artifact.GitCoordinate.Record"
EXTERNAL_DESCRIPTORS_CLASS = "Tarav.Archive.Artifact.ExternalDescriptors.Record"
SCHEMA_VERSION = 1
ARTIFACT_ID_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SCP_GIT_LOCATOR_PATTERN = re.compile(
    r"^(?:[A-Za-z0-9._-]+@)?[A-Za-z0-9.-]+:[^\s?#]+$"
)
DERIVED_ID_SCHEME = "tarav.archive.git-contained.v1"
DEFAULT_REPOSITORY_BRANCH = "main"
MAX_GIT_HINT_COMMITS = 10


class ArchiveError(RuntimeError):
    """Base error for Archive operations."""


class ArchiveWarning(UserWarning):
    """A non-blocking Archive admission or retention warning."""


class ArtifactNotFoundError(ArchiveError):
    """Raised when no Artifact matches a selector."""


class AmbiguousArtifactError(ArchiveError):
    """Raised when a convenience selector matches several Artifacts."""


class DuplicateArtifactNameError(ArchiveError):
    """Raised when a public Artifact name is already registered."""


class DuplicateArtifactLocatorError(ArchiveError):
    """Raised when a locator is already registered with different claims."""


class InvalidArtifactIdError(ArchiveError):
    """Raised when persisted Artifact identity is malformed."""


class NotGitRepositoryError(ArchiveError):
    """Raised when registration does not target a Git working tree."""


class BranchNotFoundError(ArchiveError):
    """Raised when the selected local Repository branch does not exist."""


class RepositoryLocatorUnavailableError(ArchiveError):
    """Raised when no retained local locator can provide a Repository."""


class GitArtifactNotFoundError(ArchiveError):
    """Raised when a commit or subpath is not present in a Repository."""


@dataclass(frozen=True, slots=True)
class RegisteredArtifact:
    """The primary Archive registration of one Artifact."""

    id: str
    kind: str
    name: str | None
    recorded_at: str


@dataclass(frozen=True, slots=True)
class ArtifactDossier:
    """All retained flat Records for one Artifact, without reconciliation."""

    artifact: RegisteredArtifact
    records: dict[str, object]


@dataclass(frozen=True, slots=True)
class DescriptorRegistration:
    """One attributed External.Descriptor declaration."""

    target: RegisteredArtifact
    descriptor: RegisteredArtifact
    attribution: str
    recorded_at: str
    created: bool


@dataclass(frozen=True, slots=True)
class _Locator:
    kind: str
    value: str
    host: str | None = None
    remote: str | None = None
    direction: str | None = None


@dataclass(frozen=True, slots=True)
class _GitEntry:
    mode: str
    object_type: str
    object_oid: str
    path: str
    size: int | None


@dataclass(frozen=True, slots=True)
class Archive:
    """One Archive root containing a Record repository and hosted repositories."""

    root: Path

    @property
    def records_root(self) -> Path:
        return self.root / "records"

    @property
    def artifacts_root(self) -> Path:
        return self.records_root / "artifacts"

    @property
    def repositories_root(self) -> Path:
        return self.root / "repositories"

    @classmethod
    def create(cls, root: Path) -> Archive:
        resolved = root.expanduser().resolve()
        if resolved.exists() and any(resolved.iterdir()):
            return cls.open(resolved)

        records_root = resolved / "records"
        repositories_root = resolved / "repositories"
        records_root.mkdir(parents=True, exist_ok=True)
        repositories_root.mkdir(parents=True, exist_ok=True)
        _run_git(records_root, "init", "-q")
        atomic_write_json(
            records_root / "archive.json",
            {
                "class": ARCHIVE_CLASS,
                "schema_version": SCHEMA_VERSION,
                "recorded_at": _timestamp(),
            },
        )
        _commit_paths(
            records_root,
            (Path("archive.json"),),
            message="archive: initialize records",
        )
        return cls(root=resolved)

    @classmethod
    def open(cls, root: Path) -> Archive:
        resolved = root.expanduser().resolve()
        records_root = resolved / "records"
        repositories_root = resolved / "repositories"
        if not (records_root / ".git").is_dir():
            raise ArchiveError(f"Archive Record repository is missing: {records_root}")
        if not (records_root / "archive.json").is_file():
            raise ArchiveError(f"Archive definition is missing: {records_root / 'archive.json'}")
        if not repositories_root.is_dir():
            raise ArchiveError(f"Archive repositories directory is missing: {repositories_root}")
        return cls(root=resolved)

    def register_artifact(
        self,
        *,
        locator: str,
        name: str | None = None,
        kind: str = "Artifact",
    ) -> RegisteredArtifact:
        """Register a root/repoless Artifact and one locator hint."""

        _validate_optional_name(name)
        _validate_kind(kind)
        normalized = _normalize_locator(locator)
        registered = self._registered_artifacts()
        locator_matches = self._artifacts_at(normalized, registered=registered)
        if locator_matches:
            existing = _require_one(locator_matches, selector=normalized.value)
            if existing.name != name or existing.kind != kind:
                raise DuplicateArtifactLocatorError(
                    f"Artifact locator is already registered as {existing.kind} "
                    f"{existing.name or existing.id}: {normalized.value}"
                )
            return existing
        self._ensure_name_available(name, registered=registered)
        return self._register_root(
            kind=kind,
            name=name,
            locators=(normalized,),
            git_hint=None,
        )

    def register_repository(
        self,
        location: Path,
        *,
        name: str,
        branch: str = DEFAULT_REPOSITORY_BRANCH,
    ) -> RegisteredArtifact:
        """Register an external Git repository as a root Artifact."""

        _validate_optional_name(name, required=True)
        source_root = _git_top_level(location)
        local_locator = _path_locator(source_root)
        registered = self._registered_artifacts()
        locator_matches = self._artifacts_at(local_locator, registered=registered)
        if locator_matches:
            existing = _require_one(locator_matches, selector=local_locator.value)
            if existing.kind != "Repository" or existing.name != name:
                raise DuplicateArtifactLocatorError(
                    f"Artifact locator is already registered as {existing.kind} "
                    f"{existing.name or existing.id}: {local_locator.value}"
                )
            hint = _read_json_object(self._artifact_root(existing.id) / "git-hint.json")
            if hint.get("branch") != branch:
                raise DuplicateArtifactLocatorError(
                    f"Repository is already registered for branch {hint.get('branch')!r}"
                )
            return existing
        self._ensure_name_available(name, registered=registered)

        recorded_at = _timestamp()
        git_hint = _repository_git_hint(
            source_root,
            branch=branch,
            recorded_at=recorded_at,
        )
        remote_locators, skipped_count = _repository_remote_locators(source_root)
        repository = self._register_root(
            kind="Repository",
            name=name,
            locators=(local_locator, *remote_locators),
            git_hint=git_hint,
            recorded_at=recorded_at,
        )
        if skipped_count:
            warnings.warn(
                f"skipped {skipped_count} suspicious or unsupported Git remote "
                "locator(s)",
                ArchiveWarning,
                stacklevel=2,
            )
        return repository

    def add_locator(self, selector: str, *, locator: str) -> bool:
        """Append a caller-provided locator hint to an Artifact registry."""

        artifact = self.resolve_artifact(selector)
        normalized = _normalize_locator(locator)
        record_path = self._artifact_root(artifact.id) / "locators.jsonl"
        records = _read_jsonl_objects(record_path)
        if any(_locator_matches(candidate, normalized) for candidate in records):
            return False
        records.append(
            _locator_record(
                target=artifact.id,
                locator=normalized,
                recorded_at=_timestamp(),
            )
        )
        _write_jsonl(record_path, records)
        _commit_paths(
            self.records_root,
            (record_path.relative_to(self.records_root),),
            message=f"archive(artifact): add locator {artifact.id[:12]}",
        )
        return True

    def materialize_git_artifact(
        self,
        repository_selector: str | Path,
        *,
        commit: str,
        path: str,
    ) -> RegisteredArtifact:
        """Lazily retain Records for one exact committed file or folder."""

        repository = self.resolve_repository(repository_selector)
        source_root = self._available_repository_locator(repository)
        exact_commit = _resolve_commit(source_root, commit)
        exact_path = _validate_git_subpath(path)
        entry = _git_entry(source_root, commit=exact_commit, path=exact_path)
        object_format = _run_git(source_root, "rev-parse", "--show-object-format")
        artifact_id = derive_git_artifact_id(
            repository_id=repository.id,
            object_format=object_format,
            commit=exact_commit,
            path=exact_path,
        )
        kind = _git_artifact_kind(entry.object_type)
        object_root = self._artifact_root(artifact_id)
        if object_root.exists():
            artifact = self._read_registration(object_root)
            coordinate = _read_json_object(object_root / "git-coordinate.json")
            expected = (repository.id, exact_commit, exact_path)
            observed = (
                coordinate.get("repository"),
                coordinate.get("commit"),
                coordinate.get("path"),
            )
            if artifact.kind != kind or observed != expected:
                raise ArchiveError(f"derived Artifact ID collision: {artifact_id}")
            return artifact

        recorded_at = _timestamp()
        artifact = RegisteredArtifact(
            id=artifact_id,
            kind=kind,
            name=None,
            recorded_at=recorded_at,
        )
        atomic_write_json(
            object_root / "registration.json",
            _registration_payload(
                artifact,
                identity={
                    "method": "derived",
                    "algorithm": "sha256",
                    "scheme": DERIVED_ID_SCHEME,
                },
            ),
        )
        _write_jsonl(
            object_root / "locators.jsonl",
            [
                {
                    "class": LOCATOR_CLASS,
                    "schema_version": SCHEMA_VERSION,
                    "target": artifact.id,
                    "recorded_at": recorded_at,
                    "kind": "repository-coordinate",
                    "repository": repository.id,
                    "commit": exact_commit,
                    "path": exact_path,
                }
            ],
        )
        atomic_write_json(
            object_root / "git-coordinate.json",
            {
                "class": GIT_COORDINATE_CLASS,
                "schema_version": SCHEMA_VERSION,
                "target": artifact.id,
                "recorded_at": recorded_at,
                "repository": repository.id,
                "object_format": object_format,
                "commit": exact_commit,
                "path": exact_path,
                "mode": entry.mode,
                "object_type": entry.object_type,
                "object_oid": entry.object_oid,
                "size": entry.size,
            },
        )
        _commit_paths(
            self.records_root,
            (object_root.relative_to(self.records_root),),
            message=f"archive(artifact): materialize {artifact.id[:12]}",
        )
        return artifact

    def register_external_descriptor(
        self,
        target_selector: str,
        descriptor_selector: str,
        *,
        attribution: str,
    ) -> DescriptorRegistration:
        """Record an attributed Artifact-as-Descriptor declaration."""

        if not attribution or attribution != attribution.strip():
            raise ValueError("Descriptor attribution must be a non-empty trimmed string")
        target = self.resolve_artifact(target_selector)
        descriptor = self.resolve_artifact(descriptor_selector)
        if target.id == descriptor.id:
            raise ValueError("An Artifact cannot be its own External.Descriptor")
        record_path = self._artifact_root(target.id) / "external-descriptors.json"
        if record_path.exists():
            record = _read_json_object(record_path)
        else:
            record = {
                "class": EXTERNAL_DESCRIPTORS_CLASS,
                "schema_version": SCHEMA_VERSION,
                "target": target.id,
                "recorded_at": _timestamp(),
                "descriptors": [],
            }
        descriptors = record.get("descriptors")
        if not isinstance(descriptors, list):
            raise ArchiveError(f"invalid External.Descriptors Record: {record_path}")
        for candidate in descriptors:
            if (
                isinstance(candidate, dict)
                and candidate.get("artifact") == descriptor.id
                and candidate.get("attribution") == attribution
            ):
                return DescriptorRegistration(
                    target=target,
                    descriptor=descriptor,
                    attribution=attribution,
                    recorded_at=str(candidate["recorded_at"]),
                    created=False,
                )
        recorded_at = _timestamp()
        descriptors.append(
            {
                "artifact": descriptor.id,
                "attribution": attribution,
                "recorded_at": recorded_at,
            }
        )
        if len(descriptors) == 1:
            record["recorded_at"] = recorded_at
        atomic_write_json(record_path, record)
        _commit_paths(
            self.records_root,
            (record_path.relative_to(self.records_root),),
            message=f"archive(descriptor): register for {target.id[:12]}",
        )
        return DescriptorRegistration(
            target=target,
            descriptor=descriptor,
            attribution=attribution,
            recorded_at=recorded_at,
            created=True,
        )

    def resolve_artifact(self, selector: str | Path) -> RegisteredArtifact:
        registered = self._registered_artifacts()
        if isinstance(selector, Path):
            normalized = _path_locator(selector.expanduser().resolve())
            return _require_one(
                self._artifacts_at(normalized, registered=registered),
                selector=normalized.value,
            )
        exact_names = [item for item in registered if item.name == selector]
        if exact_names:
            return _require_one(exact_names, selector=selector)
        normalized = selector.lower()
        id_matches = [item for item in registered if item.id.startswith(normalized)]
        return _require_one(id_matches, selector=selector)

    def resolve_repository(self, selector: str | Path) -> RegisteredArtifact:
        artifact = self.resolve_artifact(selector)
        if artifact.kind != "Repository":
            raise ArtifactNotFoundError(f"Archive Repository not found: {selector}")
        return artifact

    def dossier(self, selector: str | Path) -> ArtifactDossier:
        artifact = self.resolve_artifact(selector)
        records: dict[str, object] = {}
        object_root = self._artifact_root(artifact.id)
        for path in sorted((*object_root.glob("*.json"), *object_root.glob("*.jsonl"))):
            if path.suffix == ".jsonl":
                records[path.name] = _read_jsonl_objects(path)
            else:
                records[path.name] = _read_json_object(path)
        return ArtifactDossier(artifact=artifact, records=records)

    def _register_root(
        self,
        *,
        kind: str,
        name: str | None,
        locators: tuple[_Locator, ...],
        git_hint: dict[str, object] | None,
        recorded_at: str | None = None,
    ) -> RegisteredArtifact:
        now = recorded_at or _timestamp()
        artifact = RegisteredArtifact(
            id=_random_artifact_id(),
            kind=kind,
            name=name,
            recorded_at=now,
        )
        object_root = self._artifact_root(artifact.id)
        if object_root.exists():
            raise ArchiveError(f"random Artifact ID collision: {artifact.id}")
        atomic_write_json(
            object_root / "registration.json",
            _registration_payload(
                artifact,
                identity={
                    "method": "issued",
                    "algorithm": "random",
                    "bits": 256,
                },
            ),
        )
        _write_jsonl(
            object_root / "locators.jsonl",
            [
                _locator_record(target=artifact.id, locator=locator, recorded_at=now)
                for locator in locators
            ],
        )
        if git_hint is not None:
            git_hint["target"] = artifact.id
            atomic_write_json(object_root / "git-hint.json", git_hint)
        _commit_paths(
            self.records_root,
            (object_root.relative_to(self.records_root),),
            message=f"archive(artifact): register {name or artifact.id[:12]}",
        )
        return artifact

    def _registered_artifacts(self) -> tuple[RegisteredArtifact, ...]:
        if not self.artifacts_root.is_dir():
            return ()
        artifacts: list[RegisteredArtifact] = []
        for object_root in sorted(self.artifacts_root.iterdir()):
            if object_root.is_dir():
                artifacts.append(self._read_registration(object_root))
        return tuple(artifacts)

    def _read_registration(self, object_root: Path) -> RegisteredArtifact:
        record_path = object_root / "registration.json"
        payload = _read_json_object(record_path)
        try:
            artifact = RegisteredArtifact(
                id=str(payload["id"]),
                kind=str(payload["kind"]),
                name=None if payload.get("name") is None else str(payload["name"]),
                recorded_at=str(payload["recorded_at"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ArchiveError(f"invalid Artifact registration: {record_path}") from exc
        if (
            payload.get("class") != REGISTRATION_CLASS
            or not ARTIFACT_ID_PATTERN.fullmatch(artifact.id)
            or object_root.name != artifact.id
        ):
            raise InvalidArtifactIdError(f"invalid Artifact registration: {record_path}")
        return artifact

    def _artifacts_at(
        self,
        locator: _Locator,
        *,
        registered: tuple[RegisteredArtifact, ...],
    ) -> list[RegisteredArtifact]:
        matches: list[RegisteredArtifact] = []
        for artifact in registered:
            record_path = self._artifact_root(artifact.id) / "locators.jsonl"
            if not record_path.exists():
                continue
            records = _read_jsonl_objects(record_path)
            if any(_locator_matches(candidate, locator) for candidate in records):
                matches.append(artifact)
        return matches

    def _ensure_name_available(
        self,
        name: str | None,
        *,
        registered: tuple[RegisteredArtifact, ...],
    ) -> None:
        if name is not None and any(item.name == name for item in registered):
            raise DuplicateArtifactNameError(f"Archive Artifact name is already registered: {name}")

    def _available_repository_locator(self, repository: RegisteredArtifact) -> Path:
        record_path = self._artifact_root(repository.id) / "locators.jsonl"
        records = _read_jsonl_objects(record_path)
        host = socket.gethostname()
        for candidate in records:
            if candidate.get("kind") != "local-path" or candidate.get("host") != host:
                continue
            value = candidate.get("value")
            if not isinstance(value, str):
                continue
            try:
                source_root = _git_top_level(Path(value))
            except NotGitRepositoryError:
                continue
            if str(source_root) == value:
                return source_root
        raise RepositoryLocatorUnavailableError(
            f"no available local locator for Archive Repository: "
            f"{repository.name or repository.id}"
        )

    def _artifact_root(self, artifact_id: str) -> Path:
        return self.artifacts_root / artifact_id


def derive_git_artifact_id(
    *,
    repository_id: str,
    object_format: str,
    commit: str,
    path: str,
) -> str:
    """Derive one stable 256-bit ID from an exact Git-contained coordinate."""

    if not ARTIFACT_ID_PATTERN.fullmatch(repository_id):
        raise InvalidArtifactIdError(f"invalid Repository Artifact ID: {repository_id}")
    payload = json.dumps(
        [DERIVED_ID_SCHEME, repository_id, object_format, commit, path],
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _random_artifact_id() -> str:
    return secrets.token_hex(32)


def _registration_payload(
    artifact: RegisteredArtifact,
    *,
    identity: dict[str, object],
) -> dict[str, object]:
    return {
        "class": REGISTRATION_CLASS,
        "schema_version": SCHEMA_VERSION,
        "id": artifact.id,
        "kind": artifact.kind,
        "name": artifact.name,
        "recorded_at": artifact.recorded_at,
        "identity": identity,
    }


def _validate_optional_name(name: str | None, *, required: bool = False) -> None:
    if required and name is None:
        raise ValueError("Archive Artifact name is required")
    if name is None:
        return
    if not name or name != name.strip():
        raise ValueError("Archive Artifact name must be a non-empty trimmed string")
    if "/" in name or "\x00" in name:
        raise ValueError("Archive Artifact name cannot contain '/' or a null byte")


def _validate_kind(kind: str) -> None:
    if not isinstance(kind, str) or not kind or kind != kind.strip() or "\x00" in kind:
        raise ValueError("Archive Artifact kind must be a non-empty trimmed string")


def _normalize_locator(value: str) -> _Locator:
    if not isinstance(value, str) or not value or value != value.strip() or "\x00" in value:
        raise ValueError("Artifact locator must be a non-empty trimmed string")
    parsed = urlsplit(value)
    if parsed.scheme and (parsed.netloc or parsed.scheme in {"file", "mailto", "urn"}):
        return _Locator(kind="uri", value=value)
    return _path_locator(Path(value).expanduser().resolve())


def _path_locator(path: Path) -> _Locator:
    return _Locator(kind="local-path", value=str(path), host=socket.gethostname())


def _locator_record(
    *,
    target: str,
    locator: _Locator,
    recorded_at: str,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "class": LOCATOR_CLASS,
        "schema_version": SCHEMA_VERSION,
        "target": target,
        "recorded_at": recorded_at,
        "kind": locator.kind,
        "value": locator.value,
    }
    if locator.host is not None:
        payload["host"] = locator.host
    if locator.remote is not None:
        payload["remote"] = locator.remote
    if locator.direction is not None:
        payload["direction"] = locator.direction
    return payload


def _locator_matches(candidate: object, locator: _Locator) -> bool:
    return (
        isinstance(candidate, dict)
        and candidate.get("kind") == locator.kind
        and candidate.get("value") == locator.value
        and candidate.get("host") == locator.host
        and candidate.get("remote") == locator.remote
        and candidate.get("direction") == locator.direction
    )


def _git_top_level(location: Path) -> Path:
    candidate = location.expanduser().resolve()
    try:
        return Path(_run_git(candidate, "rev-parse", "--show-toplevel")).resolve()
    except ArchiveError as exc:
        raise NotGitRepositoryError(f"not a Git working tree: {candidate}") from exc


def _repository_git_hint(
    repository: Path,
    *,
    branch: str,
    recorded_at: str,
) -> dict[str, object]:
    commits = _branch_commits(repository, branch=branch)
    sampled = _sample_commits(commits)
    return {
        "class": GIT_HINT_CLASS,
        "schema_version": SCHEMA_VERSION,
        "recorded_at": recorded_at,
        "object_format": _run_git(repository, "rev-parse", "--show-object-format"),
        "branch": branch,
        "commits": [
            {
                "hash": commit,
                "raw": _run_git_bytes(
                    repository,
                    "cat-file",
                    "commit",
                    commit,
                ).decode("utf-8", "surrogateescape"),
            }
            for commit in sampled
        ],
    }


def _branch_commits(repository: Path, *, branch: str) -> tuple[str, ...]:
    if not branch or branch != branch.strip() or "\x00" in branch:
        raise ValueError("Repository branch must be a non-empty trimmed string")
    result = subprocess.run(
        ("git", "-C", str(repository), "check-ref-format", "--branch", branch),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(f"invalid Repository branch name: {branch}")
    ref = f"refs/heads/{branch}"
    try:
        _run_git(repository, "rev-parse", "--verify", f"{ref}^{{commit}}")
    except ArchiveError as exc:
        raise BranchNotFoundError(f"local Repository branch not found: {branch}") from exc
    commits = tuple(
        _run_git(repository, "rev-list", "--reverse", "--topo-order", ref).splitlines()
    )
    if not commits:
        raise BranchNotFoundError(f"local Repository branch has no commits: {branch}")
    return commits


def _sample_commits(commits: tuple[str, ...]) -> tuple[str, ...]:
    if len(commits) <= MAX_GIT_HINT_COMMITS:
        return commits
    last = len(commits) - 1
    return tuple(
        commits[index * last // (MAX_GIT_HINT_COMMITS - 1)]
        for index in range(MAX_GIT_HINT_COMMITS)
    )


def _repository_remote_locators(repository: Path) -> tuple[tuple[_Locator, ...], int]:
    admitted: list[_Locator] = []
    skipped = 0
    for remote in sorted(_run_git(repository, "remote").splitlines()):
        for direction, key in (
            ("fetch", f"remote.{remote}.url"),
            ("push", f"remote.{remote}.pushurl"),
        ):
            for value in _git_config_values(repository, key):
                if not _admit_git_remote_locator(value):
                    skipped += 1
                    continue
                admitted.append(
                    _Locator(
                        kind="git-remote",
                        value=value,
                        remote=remote,
                        direction=direction,
                    )
                )
    return tuple(admitted), skipped


def _git_config_values(repository: Path, key: str) -> tuple[str, ...]:
    try:
        result = subprocess.run(
            ("git", "-C", str(repository), "config", "--null", "--get-all", key),
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        raise ArchiveError(f"cannot run Git for {repository}: {exc}") from exc
    if result.returncode == 1:
        return ()
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip() or "Git command failed"
        raise ArchiveError(f"Git failed for {repository}: {detail}")
    return tuple(
        value.decode("utf-8", "surrogateescape")
        for value in result.stdout.split(b"\0")
        if value
    )


def _admit_git_remote_locator(value: str) -> bool:
    if (
        not value
        or value != value.strip()
        or any(
            character.isspace()
            or ord(character) < 32
            or ord(character) == 127
            or 0xD800 <= ord(character) <= 0xDFFF
            for character in value
        )
    ):
        return False
    if value.startswith(("/", "./", "../", "~/")):
        return True
    if "://" not in value and SCP_GIT_LOCATOR_PATTERN.fullmatch(value):
        return True
    parsed = urlsplit(value)
    if parsed.scheme not in {"https", "ssh", "git", "file"}:
        return False
    if parsed.query or parsed.fragment or parsed.password is not None:
        return False
    if parsed.scheme == "https" and parsed.username is not None:
        return False
    if parsed.scheme == "file":
        return bool(parsed.path)
    return parsed.hostname is not None and bool(parsed.path)


def _resolve_commit(repository: Path, commit: str) -> str:
    if not commit or commit != commit.strip() or "\x00" in commit:
        raise ValueError("Git commit must be a non-empty trimmed string")
    try:
        return _run_git(repository, "rev-parse", "--verify", f"{commit}^{{commit}}")
    except ArchiveError as exc:
        raise GitArtifactNotFoundError(f"Git commit not found: {commit}") from exc


def _validate_git_subpath(path: str) -> str:
    if (
        not isinstance(path, str)
        or not path
        or path != path.strip()
        or path.startswith("/")
        or path.endswith("/")
        or "\x00" in path
    ):
        raise ValueError("Git Artifact path must be a canonical non-empty relative path")
    if any(part in {"", ".", ".."} for part in path.split("/")):
        raise ValueError("Git Artifact path must not contain empty, '.' or '..' segments")
    return path


def _git_entry(repository: Path, *, commit: str, path: str) -> _GitEntry:
    raw = _run_git_bytes(repository, "ls-tree", "-z", commit, "--", path)
    entries = [entry for entry in raw.split(b"\0") if entry]
    if len(entries) != 1:
        raise GitArtifactNotFoundError(f"Git Artifact not found at {commit}: {path}")
    header, separator, raw_path = entries[0].partition(b"\t")
    fields = header.decode("ascii").split()
    decoded_path = raw_path.decode("utf-8", "surrogateescape")
    if not separator or len(fields) != 3 or decoded_path != path:
        raise GitArtifactNotFoundError(f"Git Artifact not found at {commit}: {path}")
    mode, object_type, object_oid = fields
    size: int | None = None
    if object_type == "blob":
        size = int(_run_git(repository, "cat-file", "-s", object_oid))
    return _GitEntry(
        mode=mode,
        object_type=object_type,
        object_oid=object_oid,
        path=path,
        size=size,
    )


def _git_artifact_kind(object_type: str) -> str:
    return {
        "blob": "File.Version",
        "tree": "Folder.Version",
        "commit": "Gitlink.Version",
    }.get(object_type, "Git.Artifact.Version")


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _read_json_object(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArchiveError(f"cannot read Archive Record: {path}") from exc
    if not isinstance(payload, dict):
        raise ArchiveError(f"Archive Record must contain a JSON object: {path}")
    return payload


def _read_jsonl_objects(path: Path) -> list[dict[str, object]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ArchiveError(f"cannot read Archive Record: {path}") from exc
    records: list[dict[str, object]] = []
    for line_number, line in enumerate(lines, start=1):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ArchiveError(
                f"cannot read Archive Record: {path}:{line_number}"
            ) from exc
        if not isinstance(payload, dict):
            raise ArchiveError(
                f"Archive Record must contain a JSON object: {path}:{line_number}"
            )
        records.append(payload)
    return records


def _write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    text = "".join(
        json.dumps(record, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n"
        for record in records
    )
    atomic_write_text(path, text)


def _require_one(
    matches: list[RegisteredArtifact],
    *,
    selector: str,
) -> RegisteredArtifact:
    if not matches:
        raise ArtifactNotFoundError(f"Archive Artifact not found: {selector}")
    if len(matches) > 1:
        raise AmbiguousArtifactError(f"Archive Artifact selector is ambiguous: {selector}")
    return matches[0]


def _run_git(repo: Path, *args: str) -> str:
    return _run_git_raw(repo, *args).strip()


def _run_git_raw(repo: Path, *args: str) -> str:
    try:
        result = subprocess.run(
            ("git", "-C", str(repo), *args),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise ArchiveError(f"cannot run Git for {repo}: {exc}") from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "Git command failed"
        raise ArchiveError(f"Git failed for {repo}: {detail}")
    return result.stdout


def _run_git_bytes(repo: Path, *args: str) -> bytes:
    try:
        result = subprocess.run(
            ("git", "-C", str(repo), *args),
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        raise ArchiveError(f"cannot run Git for {repo}: {exc}") from exc
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip() or "Git command failed"
        raise ArchiveError(f"Git failed for {repo}: {detail}")
    return result.stdout


def _commit_paths(repo: Path, paths: tuple[Path, ...], *, message: str) -> None:
    path_strings = tuple(path.as_posix() for path in paths)
    _run_git(repo, "add", "--", *path_strings)
    _run_git(
        repo,
        "-c",
        "user.name=Tarav Archive",
        "-c",
        "user.email=archive@tarav.invalid",
        "commit",
        "-q",
        "--only",
        "-m",
        message,
        "--",
        *path_strings,
    )


__all__ = [
    "AmbiguousArtifactError",
    "Archive",
    "ArchiveError",
    "ArchiveWarning",
    "ArtifactDossier",
    "ArtifactNotFoundError",
    "BranchNotFoundError",
    "DescriptorRegistration",
    "DuplicateArtifactLocatorError",
    "DuplicateArtifactNameError",
    "GitArtifactNotFoundError",
    "InvalidArtifactIdError",
    "NotGitRepositoryError",
    "RegisteredArtifact",
    "RepositoryLocatorUnavailableError",
    "derive_git_artifact_id",
]
