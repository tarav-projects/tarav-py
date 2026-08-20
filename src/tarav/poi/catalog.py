# $kw: ^poi-catalog-completeness --from POI.System --from POI.Linter --note [CT] an optional catalog can provide explicit class registration and completeness checks without becoming required POI machinery ^c20260729-49u ^c20260820-2u
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Iterator

from tarav.wayfinder import WayfinderReference


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

    def missing(self, finding_codes: Iterable[str]) -> tuple[str, ...]:
        return tuple(
            code for code in dict.fromkeys(finding_codes) if code not in self._by_code
        )

    def require_complete(self, finding_codes: Iterable[str]) -> None:
        missing = self.missing(finding_codes)
        if missing:
            raise UnknownPOIClass(
                "no POI class registered for finding code(s): " + ", ".join(missing)
            )

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
