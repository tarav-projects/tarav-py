"""Typed provider navigation over a virtual root of registered collections."""

from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from tarav.harness import DIRECTORY_ENTRY_PATH, TaravObject, TypeRegistry, TypeShip
from tarav.harness.workflows import Workflow
from tarav.poi import POI, POIFinding


class ProviderError(POI):
    """A provider operation could not produce a valid navigation result."""

    type_name = "Tarav.Navigation.ProviderError"
    type_ship = TypeShip("8980b4de-fb5f-4aa1-8ff3-5e6c82246ce3")


@dataclass(frozen=True)
class Entry:
    name: str
    kind: str


@dataclass(frozen=True)
class NavigationResult:
    value: object = None
    findings: tuple[POIFinding, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.findings


class RecordProvider:
    """A provider owns listing and loading semantics for its collection."""

    def list(self, address: str = "") -> tuple[Entry, ...]:
        raise NotImplementedError

    def load(self, address: str) -> TaravObject:
        raise NotImplementedError


class FilesystemProvider(RecordProvider):
    """Browse an explicitly registered local collection; no content guessing."""

    def __init__(self, root: Path, records: TypeRegistry[TaravObject]) -> None:
        self.root = root.expanduser().resolve()
        self.records = records

    def path(self, address: str) -> Path:
        relative = PurePosixPath(address)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Provider address must remain relative to its root")
        target = (self.root / address).resolve()
        if not target.is_relative_to(self.root):
            raise ValueError("Provider address escapes its root")
        return target

    def list(self, address: str = "") -> tuple[Entry, ...]:
        entries = []
        for path in sorted(self.path(address).iterdir()):
            if path.name.startswith("."):
                continue
            if path.is_dir():
                kind = (
                    "directory-record"
                    if any((path / name).exists() for name in DIRECTORY_ENTRY_PATH)
                    else "collection"
                )
            else:
                kind = "record" if path.suffix == ".json" else "artifact"
            entries.append(Entry(path.name, kind))
        return tuple(entries)

    def load(self, address: str) -> TaravObject:
        return self.records.load(self.path(address))


class Navigation(Workflow):
    name = "navigation"

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

    def list(self, path: str = "/") -> NavigationResult:
        if path == "/":
            return NavigationResult(
                tuple(Entry(name, "provider") for name in self.providers)
            )
        return self._call("list", path)

    def load(self, path: str) -> NavigationResult:
        return self._call("load", path)

    def _call(self, operation: str, path: str) -> NavigationResult:
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
            return NavigationResult(value)
        except Exception as exc:
            return NavigationResult(
                findings=(
                    ProviderError.finding(
                        {"path": path, "operation": operation},
                        evidence={"error": type(exc).__name__, "message": str(exc)},
                    ),
                )
            )
