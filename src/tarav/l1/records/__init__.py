"""TaravRecords workflow over contributed Record sources."""

from dataclasses import dataclass

from tarav.l0.kernel import Ship, TaravClass, TaravEntity
from tarav.l0.kernel import TaravObject, TypeShip
from tarav.l0.kernel.space import Entry, RecordProvider
from tarav.l0.kernel.workflows import TaravWorkflow
from .identity import RECORDS_WORKFLOW_SHIP
from tarav.l1.poi import SituationPOI, plain


class ProviderError(SituationPOI):
    """A provider operation could not produce a valid navigation result.

    `error` is what the provider raised: the exception's name and its text.
    """

    # tarav.breadcrumb eed2a0b9b7d67e1cfde3cc88d674ea28580a7ecc6a13c96de7f2835b44359cc1
    def __init__(self, message: str, *, situation, error: dict | None = None) -> None:
        super().__init__(message, situation=situation)
        self.error = dict(error or {})

    class RecordInterface(SituationPOI.RecordInterface):
        error: dict

    def _to_record(self) -> dict[str, object]:
        return {**super()._to_record(), "error": plain(self.error)}

    @classmethod
    def _from_record(cls, record_data):
        result = super()._from_record(record_data)
        result.error = record_data.error
        return result

    class Records(SituationPOI.Records):
        def record_example(self) -> dict[str, object]:
            return {**super().record_example(), "error": {}}

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('8980b4de-fb5f-4aa1-8ff3-5e6c82246ce3'),
            name='Tarav.Records.ProviderError',
            workflow=RECORDS_WORKFLOW_SHIP,
        )


@dataclass(frozen=True)
class RecordsResult:
    value: object = None
    pois: tuple[ProviderError, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.pois


class TaravRecords(TaravWorkflow):
    # tarav.breadcrumb fd99c99a4196cf1d25b402a022670b59b1bd39145222792422d9c0aacb5b3f71
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('085bb59e-6833-42d4-a21b-e8df8bad4460'),
            name='Tarav.Workflow.Records',
            workflow=RECORDS_WORKFLOW_SHIP,
        )

    @classmethod
    def _workflow_id(cls):
        return RECORDS_WORKFLOW_SHIP
    workflow_name = "records"
    constitution = (
        "Provide reusable Record storage mechanics and navigation across "
        "workflow-contributed sources."
    )

    @staticmethod
    def service() -> "RecordsService":
        return RecordsService()

    @staticmethod
    def registry(root=None, records=None):
        """Select the standard Registry or the same layout at a custom root."""
        from .registry import RecordRegistry

        return RecordRegistry(root, records)

    @classmethod
    def provider(cls, root, records):
        from .registry import RegistryProvider

        return RegistryProvider(root, records)


class RecordsService:
    """Runtime-specific source mounts; no per-Record registration."""
    # tarav.breadcrumb 4a8b0623da410c2cb9c0530a2ad3b8d20cad023ad4bb246692c1f7afd8305804

    def __init__(self) -> None:
        self.providers: dict[str, RecordProvider] = {}

    def mount(self, name: str, provider: RecordProvider) -> None:
        if not name or "/" in name or name in {".", ".."}:
            raise ValueError("Provider name must be one nonempty path component")
        if name in self.providers:
            raise ValueError(f"Provider already registered: {name}")
        if not isinstance(provider, RecordProvider):
            raise TypeError("Provider must implement RecordProvider")
        self.providers[name] = provider

    def explore(self):
        """Open a stateful route without scanning any contributed source."""
        from .explorer import RecordsExplorer

        return RecordsExplorer(self)

    def entities(self, ship: Ship | str | None = None) -> RecordsResult:
        """Discover retained Entity occurrences in mounted sources on demand."""
        # tarav.breadcrumb ed832bc96480596c451c72addcea0bd76be577209bb8d3eb0d89ed54a6307e5d
        from .explorer import RecordsEntry

        selected = str(Ship(str(ship))) if ship is not None else None
        matches: list[RecordsEntry] = []
        pois: list[ProviderError] = []
        for name in self.providers:
            stack = [f"/{name}"]
            while stack:
                parent = stack.pop()
                listing = self.list(parent)
                if not listing.ok:
                    pois.extend(listing.pois)
                    continue
                for item in listing.value:
                    entry = RecordsEntry(self, parent, item.name, item.kind)
                    if item.kind in {"record", "directory-record"}:
                        loaded = self.load(entry.path)
                        if not loaded.ok:
                            pois.extend(loaded.pois)
                        elif isinstance(loaded.value, TaravEntity) and (
                            selected is None or str(loaded.value.id) == selected
                        ):
                            matches.append(entry)
                    if entry.navigable:
                        stack.append(entry.path)
        return RecordsResult(tuple(matches), tuple(pois))

    def list(self, path: str = "/") -> RecordsResult:
        if path == "/":
            return RecordsResult(
                tuple(Entry(name, "provider") for name in self.providers)
            )
        return self._call("list", path)

    def load(self, path: str) -> RecordsResult:
        return self._call("load", path)

    def _call(self, operation: str, path: str) -> RecordsResult:
        try:
            name, _, address = path.lstrip("/").partition("/")
            provider = self.providers[name]
            value = getattr(provider, operation)(address)
            if operation == "load" and not isinstance(value, TaravObject):
                raise TypeError("Provider did not return a Record")
            if operation == "list" and (
                not isinstance(value, tuple)
                or not all(isinstance(item, Entry) for item in value)
            ):
                raise TypeError("Provider did not return a tuple of navigation Entries")
            if operation == "list" and any(
                not item.name or item.name in {".", ".."}
                or "/" in item.name or "\\" in item.name
                for item in value
            ):
                raise ValueError("Provider returned an invalid Record entry name")
            return RecordsResult(value)
        except Exception as exc:
            return RecordsResult(
                pois=(
                    ProviderError(
                        str(exc),
                        situation={"path": path, "operation": operation},
                        error={"type": type(exc).__name__, "message": str(exc)},
                    ),
                )
            )


from .explorer import (  # noqa: E402
    RecordsEntry, RecordsExplorer, RecordsFolder, RecordsRoot,
)
from .registry import (  # noqa: E402
    RecordMap, RecordRegistry, RegistryProvider, default_records_root,
)
from .storage import write_typed_record  # noqa: E402


RECORDS_TYPES = (RecordsEntry, RecordsFolder, RecordsRoot)

__all__ = [
    "ProviderError", "RECORDS_TYPES", "RECORDS_WORKFLOW_SHIP", "RecordsEntry",
    "RecordsExplorer", "RecordsFolder", "RecordsResult", "RecordsRoot",
    "RecordsService", "TaravRecords", "RecordMap", "RecordRegistry",
    "RegistryProvider", "default_records_root", "write_typed_record",
]
