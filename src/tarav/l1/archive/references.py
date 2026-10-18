"""DOI-rooted references interpreted by the Archive, with explicit checks."""

import hashlib
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from pydantic import ConfigDict, Field

from tarav.l0.kernel import TaravClass, entity
from tarav.l0.kernel import TaravObject, TypeShip
from tarav.l0.kernel.records import _json_object
from tarav.l1.references import Reference, ReferenceResult
from tarav.l1.references.git import git_bytes, git_text
from tarav.l1.archive.identity import ARCHIVE_WORKFLOW_SHIP
from collections.abc import Mapping
from . import default_archive_root

from . import (
    Archive,
    ArchiveError,
    ARTIFACT_ID_PATTERN,
    _read_json_object,
    _read_jsonl_objects,
)


@dataclass(frozen=True)
class ArchiveTarget:
    doi: str
    path: Path | None = None
    content: bytes | None = None
    git_oid: str | None = None


class ArchiveLocator(TaravObject.RecordInterface):
    model_config = ConfigDict(strict=True, extra="forbid")

    archive: str = Field(min_length=1)
    doi: Annotated[str, Field(pattern=ARTIFACT_ID_PATTERN.pattern)]


class ArchiveSha256Check(TaravObject.RecordInterface):
    model_config = ConfigDict(strict=True, extra="forbid")

    sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")


class ArchiveGitOidCheck(TaravObject.RecordInterface):
    model_config = ConfigDict(strict=True, extra="forbid")

    git_oid: str = Field(min_length=1)


class ArchiveContainsCommitCheck(TaravObject.RecordInterface):
    model_config = ConfigDict(strict=True, extra="forbid")

    contains_commit: str = Field(min_length=1)


class ArchiveReference(Reference):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('c2b01ef3-5c7a-4c60-9826-b16828660fa9'),
            name='Tarav.Archive.Reference',
            workflow=ARCHIVE_WORKFLOW_SHIP,
        )

    class RecordInterface(Reference.RecordInterface):
        locator: ArchiveLocator
        check: (
            ArchiveSha256Check
            | ArchiveGitOidCheck
            | ArchiveContainsCommitCheck
            | None
        ) = None

    class Records(Reference.Records):
        def record_example(self) -> dict[str, object]:
            cls = self._owner
            return {
                "type": entity(cls).name,
                "locator": {"archive": "/example/archive", "doi": "0" * 64},
            }


    def __init__(
        self,
        record: Mapping | None = None,
        *,
        doi: str | None = None,
        archive: str | Path | None = None,
        check=None,
        hints=None,
    ):
        if record is None:
            if doi is None or not ARTIFACT_ID_PATTERN.fullmatch(doi):
                raise ValueError("Archive reference requires an exact DOI")
            root = (
                Path(archive).expanduser().absolute()
                if archive is not None
                else default_archive_root()
            )
            observed = {"archive": str(root), "doi": doi}
            if hints is not None:
                observed.update(hints)
            record = {
                "type": entity(type(self)).name,
                "locator": {"archive": str(root), "doi": doi},
                "hints": observed,
            }
            if check is not None:
                record["check"] = check
        elif any(value is not None for value in (doi, archive, check, hints)):
            raise ValueError("Loading retained data cannot override reference fields")
        super().__init__()
        self._fields = _json_object(record)

    def locate(self, locator: object) -> ArchiveTarget:
        if not isinstance(locator, dict) or set(locator) != {"archive", "doi"}:
            raise ValueError("Archive locator requires archive root and DOI")
        doi = locator["doi"]
        if not isinstance(doi, str) or not ARTIFACT_ID_PATTERN.fullmatch(doi):
            raise ValueError("Archive reference requires an exact DOI, not a selector")
        archive = Archive.open(Path(locator["archive"]))
        artifact = archive.resolve_artifact(doi)
        if artifact.id != doi:
            raise ValueError("Archive DOI resolved to a different identity")
        root = archive._artifact_root(artifact.id)
        if (root / "tombstones.jsonl").exists():
            raise ValueError(f"DOI is retired; retained evidence: {root}")
        coordinate_path = root / "git-coordinate.json"
        if coordinate_path.exists():
            coordinate = _read_json_object(coordinate_path)
            repository = archive.resolve_repository(coordinate["repository"])
            repo = archive._available_repository_locator(repository)
            address = f"{coordinate['commit']}:{coordinate['path']}"
            oid = git_text(repo, "rev-parse", "--verify", "--end-of-options", address)
            content = git_bytes(repo, "show", address)
            return ArchiveTarget(artifact.id, content=content, git_oid=oid)
        if artifact.kind == "git-repository":
            return ArchiveTarget(
                artifact.id, path=archive._available_repository_locator(artifact)
            )
        candidates = _read_jsonl_objects(root / "locators.jsonl")
        local = [
            item
            for item in candidates
            if item.get("kind") == "local-path"
            and item.get("host") == socket.gethostname()
        ]
        if not local:
            raise FileNotFoundError(f"No local locator for DOI {artifact.id}")
        path = Path(local[-1]["value"])
        if not path.exists():
            raise FileNotFoundError(path)
        version = root / "file-version.json"
        if version.exists():
            expected = _read_json_object(version)["sha256"]
            with path.open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
                    raise ValueError(
                        f"DOI identity contract no longer holds: {artifact.id}"
                    )
        return ArchiveTarget(artifact.id, path=path)

    def check_target(self, target: ArchiveTarget, check: object) -> bool:
        if check is None:
            return True
        if not isinstance(check, dict) or len(check) != 1:
            raise ValueError("Archive check must specify exactly one identity check")
        if "sha256" in check:
            if target.content is not None:
                actual = hashlib.sha256(target.content).hexdigest()
            else:
                if target.path is None or not target.path.is_file():
                    raise ValueError("sha256 check requires file content")
                with target.path.open("rb") as stream:
                    actual = hashlib.file_digest(stream, "sha256").hexdigest()
            return actual == check["sha256"]
        if "git_oid" in check:
            return target.git_oid == check["git_oid"]
        if "contains_commit" in check:
            if target.path is None:
                raise ValueError("contains_commit check requires a repository")
            return (
                git_text(
                    target.path,
                    "rev-parse",
                    "--verify",
                    f"{check['contains_commit']}^{{commit}}",
                )
                == check["contains_commit"]
            )
        raise ValueError("Unknown Archive reference check")

    def resolve(self) -> ReferenceResult:
        try:
            return super().resolve()
        except ArchiveError as exc:
            return ReferenceResult(None, "unresolvable", str(exc), self.hints)


def reference_record(
    archive: Archive,
    doi: str,
    *,
    check: dict | None = None,
    hints: dict | None = None,
) -> dict:
    record = {
        "type": entity(ArchiveReference).name,
        "locator": {"archive": str(archive.root), "doi": doi},
    }
    if check is not None:
        record["check"] = check
    if hints:
        record["hints"] = hints
    return record
