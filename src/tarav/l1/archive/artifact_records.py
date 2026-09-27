"""Artifact-registration Record authorities and serialization contracts."""

from tarav.l0.kernel import TaravClass
from tarav.l0.kernel import (
    DirectoryRecord,
    FileRecord,
    TaravObject,
    TypeRegistry,
    TypeShip,
)
from tarav.l1.archive.identity import ARCHIVE_WORKFLOW_SHIP


class ArchiveRecord(DirectoryRecord):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('c3b994e9-1907-5cf4-8f6e-3efd6e1fd352'),
            name='Tarav.Archive',
            workflow=ARCHIVE_WORKFLOW_SHIP,
        )


class ArtifactRecord(DirectoryRecord):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('683fd453-7425-5a91-a382-5753a986e324'),
            name='Tarav.Archive.Artifact.Registration.Record',
            workflow=ARCHIVE_WORKFLOW_SHIP,
        )

    @property
    def doi(self) -> str:
        return str(self.to_record()["id"])

    @property
    def contract(self) -> object:
        return self.to_record()["contract"]


class LocatorRecord(FileRecord):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('af6c9c8e-ef25-5023-b1ce-33c4dfd4d05d'),
            name='Tarav.Archive.Artifact.Locator.Record',
            workflow=ARCHIVE_WORKFLOW_SHIP,
        )


class GitHintRecord(FileRecord):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('408cd6d8-02b2-55a5-bbd8-797b4c04c864'),
            name='Tarav.Archive.Artifact.GitHint.Record',
            workflow=ARCHIVE_WORKFLOW_SHIP,
        )


class GitCoordinateRecord(FileRecord):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('2542f5e3-8ecd-5093-86c3-24e731a9cee5'),
            name='Tarav.Archive.Artifact.GitCoordinate.Record',
            workflow=ARCHIVE_WORKFLOW_SHIP,
        )


class FileVersionRecord(FileRecord):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('b0ceadb7-73cf-5bf8-9374-86d579ff9c60'),
            name='Tarav.Archive.Artifact.FileVersion.Record',
            workflow=ARCHIVE_WORKFLOW_SHIP,
        )


class ExternalDescriptorsRecord(FileRecord):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('b0747b7b-0561-55c6-a273-39e0f4caa1ac'),
            name='Tarav.Archive.Artifact.ExternalDescriptors.Record',
            workflow=ARCHIVE_WORKFLOW_SHIP,
        )


class TombstoneRecord(FileRecord):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('ec2891dc-c843-5060-818c-21b0212023e9'),
            name='Tarav.Archive.Artifact.Tombstone.Record',
            workflow=ARCHIVE_WORKFLOW_SHIP,
        )


ARCHIVE_RECORD_TYPES = (
    ArchiveRecord,
    ArtifactRecord,
    LocatorRecord,
    GitHintRecord,
    GitCoordinateRecord,
    FileVersionRecord,
    ExternalDescriptorsRecord,
    TombstoneRecord,
)


def record_registry() -> TypeRegistry[TaravObject]:
    return TypeRegistry(TaravObject, ARCHIVE_RECORD_TYPES)
