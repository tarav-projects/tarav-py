from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Iterator

from agentos.wayfinder import WayfinderReference


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
