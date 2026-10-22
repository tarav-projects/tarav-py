"""Project integration with typed Records and their standard registry."""

from tarav.l0.kernel import TaravEntity, entity
from tarav.l0.kernel.current import current_records


# tarav.breadcrumb f0c72094487a
class RecordsManager(TaravEntity.Records):
    """Preserve Record projection/loading and select storage for Project integrations."""

    @property
    def types(self):
        return current_records()

    @property
    def registry(self):
        """The standard Record storage, without provisioning a partition."""
        from tarav.l1.records import RecordRegistry

        return RecordRegistry(records=self.types)

    def record_example(self):
        return {"type": entity(self._owner).name,
                "project_id": "20c26be7-a8e5-4974-9ec0-0b5a3a125a94",
                "created_at": "2026-01-01T00:00:00Z"}


__all__ = ["RecordsManager"]
