"""Navigation workflow over registered Record-space providers."""

from dataclasses import dataclass

from tarav.l0.kernel import TaravClass
from tarav.l0.kernel import TaravObject, TypeShip
from tarav.l0.kernel.space import Entry, RecordProvider
from tarav.l0.kernel.workflows import TaravWorkflow
from tarav.navigation.identity import NAVIGATION_WORKFLOW_SHIP
from tarav.poi import POI, POIFinding


class ProviderError(POI):
    """A provider operation could not produce a valid navigation result."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('8980b4de-fb5f-4aa1-8ff3-5e6c82246ce3'),
            name='Tarav.Navigation.ProviderError',
            workflow=NAVIGATION_WORKFLOW_SHIP,
        )


@dataclass(frozen=True)
class NavigationResult:
    value: object = None
    findings: tuple[POIFinding, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.findings


class Navigation(TaravWorkflow):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('085bb59e-6833-42d4-a21b-e8df8bad4460'),
            name='Tarav.Workflow.Navigation',
            workflow=NAVIGATION_WORKFLOW_SHIP,
        )

    @classmethod
    def _workflow_id(cls):
        return NAVIGATION_WORKFLOW_SHIP
    workflow_name = "navigation"
    constitution = "Mount Record providers into a navigable virtual space."

    @staticmethod
    def service() -> "NavigationService":
        return NavigationService()


class NavigationService:
    """Runtime-specific provider mounts."""

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
