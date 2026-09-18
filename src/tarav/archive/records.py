"""Archive-owned Record authorities and serialization contracts."""

from tarav.harness import (
    DirectoryRecord,
    FileRecord,
    TaravRecord,
    TypeRegistry,
    TypeShip,
)


class ArchiveRecord(DirectoryRecord):
    type_name = "Tarav.Archive"
    type_ship = TypeShip("c3b994e9-1907-5cf4-8f6e-3efd6e1fd352")


class ArtifactRecord(DirectoryRecord):
    type_name = "Tarav.Archive.Artifact.Registration.Record"
    type_ship = TypeShip("683fd453-7425-5a91-a382-5753a986e324")

    @property
    def doi(self) -> str:
        return str(self.record["id"])

    @property
    def contract(self) -> object:
        return self.record["contract"]


class LocatorRecord(FileRecord):
    type_name = "Tarav.Archive.Artifact.Locator.Record"
    type_ship = TypeShip("af6c9c8e-ef25-5023-b1ce-33c4dfd4d05d")


class GitHintRecord(FileRecord):
    type_name = "Tarav.Archive.Artifact.GitHint.Record"
    type_ship = TypeShip("408cd6d8-02b2-55a5-bbd8-797b4c04c864")


class GitCoordinateRecord(FileRecord):
    type_name = "Tarav.Archive.Artifact.GitCoordinate.Record"
    type_ship = TypeShip("2542f5e3-8ecd-5093-86c3-24e731a9cee5")


class FileVersionRecord(FileRecord):
    type_name = "Tarav.Archive.Artifact.FileVersion.Record"
    type_ship = TypeShip("b0ceadb7-73cf-5bf8-9374-86d579ff9c60")


class ExternalDescriptorsRecord(FileRecord):
    type_name = "Tarav.Archive.Artifact.ExternalDescriptors.Record"
    type_ship = TypeShip("b0747b7b-0561-55c6-a273-39e0f4caa1ac")


class TombstoneRecord(FileRecord):
    type_name = "Tarav.Archive.Artifact.Tombstone.Record"
    type_ship = TypeShip("ec2891dc-c843-5060-818c-21b0212023e9")


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


def record_registry() -> TypeRegistry[TaravRecord]:
    return TypeRegistry(TaravRecord, ARCHIVE_RECORD_TYPES)
