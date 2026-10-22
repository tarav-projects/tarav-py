"""Archive's typed DOI registry; lookup never accesses external resources."""
# tarav.breadcrumb 5800ece33211

from pathlib import Path

from tarav.l1.records.registry import RecordMap, default_records_root
from .identity import ARCHIVE_WORKFLOW_SHIP
from .model import DOI, RepositoryDOI, DOI_RECORD_TYPES


class Archive:
    """Explicit persistence for maintained DOI declarations."""

    def __init__(self, root=None, *, records=None):
        root = Path(root) if root is not None else default_archive_root()
        self.store = RecordMap(root, ARCHIVE_WORKFLOW_SHIP, records)

    @property
    def root(self):
        return self.store.root

    @classmethod
    def create(cls, root=None, *, records=None):
        archive = cls(root, records=records)
        archive.store.create()
        return archive

    @classmethod
    def open(cls, root=None, *, records=None):
        archive = cls(root, records=records)
        archive.store.open()
        return archive

    def register(self, doi: DOI):
        if not isinstance(doi, DOI):
            raise TypeError("Archive registers DOI objects")
        self.store.insert(doi.id, doi)
        return doi

    def read(self, identity: str):
        DOI.validate_id(identity)
        doi = self.store.load(identity)
        if not isinstance(doi, DOI) or doi.id != identity:
            raise ValueError("DOI Record does not match its registry key")
        return doi

    def update(self, doi: DOI):
        previous = self.read(doi.id)
        if type(previous) is not type(doi):
            raise ValueError("A DOI cannot be rebound to another Type")
        self.store.replace(doi.id, doi)
        return doi

    def ids(self):
        if not self.store.marker.exists():
            return ()
        return self.store.names()

    def commit(self, message: str):
        return self.store.commit(self.ids(), message)


def default_archive_root():
    return default_records_root() / str(ARCHIVE_WORKFLOW_SHIP)


__all__ = ["Archive", "DOI", "RepositoryDOI", "DOI_RECORD_TYPES", "default_archive_root"]
