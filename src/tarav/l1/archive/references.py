"""DOI references load maintained registry objects, not external artifact bytes."""
# tarav.breadcrumb 5034083e41f2

from collections.abc import Mapping

from tarav.l0.kernel import TaravClass, TaravObject, TypeShip, entity
from tarav.l1.references import Reference
from . import Archive, default_archive_root
from .identity import ARCHIVE_WORKFLOW_SHIP


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
