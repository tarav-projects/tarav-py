"""DOI references load maintained registry objects, not external artifact bytes."""
# tarav.breadcrumb 5034083e41f2

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Annotated

from pydantic import Field, model_validator

from tarav.l0.kernel import TaravClass, TaravObject, TypeShip, entity
from tarav.l1.references import Reference
from . import Archive, default_archive_root
from .identity import ARCHIVE_WORKFLOW_SHIP
from .model import RepositoryDOI


class DOILocator(TaravObject.RecordInterface):
    registry: str
    doi: str


class DOIReference(Reference):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("e97230bd-6730-4b09-97c4-180d7ac15fe7"),
                          name="Tarav.Archive.Reference.DOI", workflow=ARCHIVE_WORKFLOW_SHIP)

    class RecordInterface(Reference.RecordInterface):
        locator: DOILocator
        check: None = None

    def __init__(self, doi: str | Mapping, *, registry=None):
        super().__init__()
        self._records = None
        self._fields = (dict(doi) if isinstance(doi, Mapping) else
                        {"type": entity(type(self)).name,
                         "locator": {"registry": str(registry or default_archive_root()), "doi": doi}})

    def _bind_record_loader(self, loader):
        self._records = getattr(loader, "__self__", None)

    def locate(self, locator):
        location = DOILocator.model_validate(locator)
        return Archive.open(location.registry, records=getattr(self, "_records", None)).read(location.doi)

    def check_target(self, target, check):
        if check is not None:
            raise ValueError("DOI lookup provides maintained information; checks are separate")
        return True

    class Records(Reference.Records):
        def record_example(self):
            return {"type": entity(self._owner).name,
                    "locator": {"registry": "/example/registry", "doi": "a" * 64}}


GitHash = Annotated[str, Field(pattern=r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")]


class RepositoryLocator(DOILocator):
    """A captured coordinate, not an instruction to access the repository."""

    commit: GitHash
    tree: GitHash
    change_id: Annotated[str, Field(pattern=r"^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$")] | None = None
    path: str | None = None

    @model_validator(mode="after")
    def canonical_path(self):
        if self.path is not None:
            path = PurePosixPath(self.path)
            if (not self.path or path.is_absolute() or ".." in path.parts or
                    str(path) != self.path or "\0" in self.path):
                raise ValueError("Repository selection needs a canonical relative path")
        if len(self.commit) != len(self.tree):
            raise ValueError("Commit and tree must use the same Git object format")
        return self


@dataclass(frozen=True)
class RepositoryTarget:
    repository: RepositoryDOI
    coordinate: RepositoryLocator


class RepositoryReference(DOIReference):
    """Return a maintained repository declaration with captured Git coordinates."""
    # tarav.breadcrumb 8b0caa81cbb1

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("46c9d01f-c070-4554-bfe0-509ae05b1c3c"),
                          name="Tarav.Archive.Reference.Repository", workflow=ARCHIVE_WORKFLOW_SHIP)

    class RecordInterface(DOIReference.RecordInterface):
        locator: RepositoryLocator

    def __init__(self, record: Mapping):
        super().__init__(record)
        RepositoryLocator.model_validate(self.locator)

    def locate(self, locator):
        coordinate = RepositoryLocator.model_validate(locator)
        repository = super().locate({"registry": coordinate.registry, "doi": coordinate.doi})
        if not isinstance(repository, RepositoryDOI):
            raise ValueError("Repository reference requires a Repository DOI")
        return RepositoryTarget(repository, coordinate)

    class Records(DOIReference.Records):
        def record_example(self):
            return {"type": entity(self._owner).name,
                    "locator": {"registry": "/example/registry", "doi": "a" * 64,
                                "commit": "0" * 40, "tree": "1" * 40}}
