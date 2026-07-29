from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Iterator

from agentos.wayfinder import (
    PACKAGE_SKILL_ROOT_TYPE,
    WayfinderReference,
    WayfinderRegistry,
    poi_class_reference,
)


class POICatalogError(RuntimeError):
    pass


class DuplicatePOIClass(POICatalogError):
    pass


class UnknownPOIClass(POICatalogError):
    pass


@dataclass(frozen=True)
class POIClassRegistration:
    finding_code: str
    reference: WayfinderReference

    def __post_init__(self) -> None:
        if not self.finding_code:
            raise ValueError("POI finding code must be non-empty")

    def as_dict(self) -> dict[str, object]:
        return {
            "finding_code": self.finding_code,
            "reference": self.reference.as_dict(),
        }


class POICatalog:
    def __init__(
        self,
        registrations: Iterable[POIClassRegistration] = (),
    ) -> None:
        self._by_code: dict[str, POIClassRegistration] = {}
        for registration in registrations:
            if registration.finding_code in self._by_code:
                raise DuplicatePOIClass(
                    f"duplicate POI class registration: {registration.finding_code}"
                )
            self._by_code[registration.finding_code] = registration

    def __iter__(self) -> Iterator[POIClassRegistration]:
        return iter(self._by_code.values())

    def __len__(self) -> int:
        return len(self._by_code)

    def get(self, finding_code: str) -> WayfinderReference | None:
        registration = self._by_code.get(finding_code)
        return registration.reference if registration is not None else None

    def require(self, finding_code: str) -> WayfinderReference:
        reference = self.get(finding_code)
        if reference is None:
            raise UnknownPOIClass(
                f"no POI class registered for finding code: {finding_code}"
            )
        return reference

    @classmethod
    def compose(cls, *catalogs: POICatalog) -> POICatalog:
        return cls(registration for catalog in catalogs for registration in catalog)

    @classmethod
    def discover(
        cls,
        *,
        registry: WayfinderRegistry | None = None,
        package_ids: Iterable[str] | None = None,
    ) -> POICatalog:
        """Discover POI classes from registered Package.Skill `poi` chapters."""
        from agentos.index.model import BlockHeading, parse_depot

        selected = set(package_ids) if package_ids is not None else None
        registrations: list[POIClassRegistration] = []
        for entry in (registry or WayfinderRegistry()).entries():
            if entry.root.type != PACKAGE_SKILL_ROOT_TYPE:
                continue
            if selected is not None and entry.root.id not in selected:
                continue
            poi_root = entry.path / "poi"
            if not poi_root.is_dir():
                continue
            depot = parse_depot(entry.path)
            for document in depot.documents:
                if (
                    document.surface_kind != "chapter"
                    or document.path is None
                    or document.path.parent != poi_root
                ):
                    continue
                diagnostics = document.diagnostics()
                if diagnostics:
                    reasons = ", ".join(
                        f"{diagnostic.reason} at line {diagnostic.start_line}"
                        for diagnostic in diagnostics
                    )
                    raise POICatalogError(
                        f"invalid POI chapter {document.path}: {reasons}"
                    )
                for node in document.nodes:
                    if not isinstance(node, BlockHeading):
                        continue
                    block_path = str(node.parsed.get("path", ""))
                    if not node.parsed.get("valid") or not block_path:
                        raise POICatalogError(
                            f"invalid POI class heading in "
                            f"{document.path}:{node.start_line}"
                        )
                    registrations.append(
                        POIClassRegistration(
                            finding_code=block_path,
                            reference=poi_class_reference(entry.root.id, block_path),
                        )
                    )
        return cls(registrations)

    def as_dict(self) -> dict[str, object]:
        return {
            "classes": [registration.as_dict() for registration in self],
        }


__all__ = [
    "DuplicatePOIClass",
    "POICatalog",
    "POICatalogError",
    "POIClassRegistration",
    "UnknownPOIClass",
]
