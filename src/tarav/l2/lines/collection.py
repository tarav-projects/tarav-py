"""tarav.l2.lines.collection: extracted legacy definitions; identities and storage labels preserved."""

from __future__ import annotations

# tarav.breadcrumb 7400548a1999

import tarav.l2.unsorted.pois as diagram_pois

from tarav.l2.unsorted.pois import DiagramPOI
from tarav.l2.unsorted.primitives import _optional_timestamp
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tarav.l2.lines.records import CollectionEditionRecord
    from tarav.l2.lines.references import DiagramArgumentReferenceInterface
    from tarav.l2.lines.references import DiagramHostReferenceInterface
    from tarav.l2.unsorted.constants import JsonObject

@dataclass(frozen=True, slots=True)
class DiagramHostedEdition:
    kind: str
    ship: str
    edition: str

    def to_dict(self) -> JsonObject:
        return {"kind": self.kind, "ship": self.ship, "edition": self.edition}


@dataclass(frozen=True, slots=True)
class DiagramCollection:
    ship: str
    model_ship: str
    editions: tuple[CollectionEditionRecord, ...]
    type_ids: tuple[str, ...]
    hosted_editions: tuple[DiagramHostedEdition, ...]
    pois: tuple[DiagramPOI, ...]

    @property
    def object_type(self) -> str | None:
        return self.type_ids[-1] if self.type_ids else None

    @property
    def current_edition(self) -> CollectionEditionRecord | None:
        return self.editions[-1] if self.editions else None

    @property
    def labels(self) -> tuple[str, ...]:
        return tuple(item.label for item in self.editions)

    @property
    def current_label(self) -> str | None:
        current = self.current_edition
        return current.label if current is not None else None

    @property
    def host(self) -> DiagramHostReferenceInterface | None:
        current = self.current_edition
        return current.host if current is not None else None

    @property
    def references(self) -> tuple[DiagramArgumentReferenceInterface, ...]:
        current = self.current_edition
        return current.references if current is not None else ()

    def mechanical_pois(self) -> tuple[DiagramPOI, ...]:
        return ()


class ImplReqCollection(DiagramCollection):
    @property
    def state(self) -> str | None:
        current = self.current_edition
        if current is None:
            return None
        value = current.data.get("state")
        return value if isinstance(value, str) else None

    def mechanical_pois(self) -> tuple[DiagramPOI, ...]:
        pois: list[DiagramPOI] = []
        previous: CollectionEditionRecord | None = None
        for edition in self.editions:
            state = edition.data.get("state")
            if state not in {"Open", "Closed"}:
                pois.append(
                    diagram_pois.ImplReqStateInvalid(path=f'collection.{self.ship}.edition.{edition.id}.data.state', message='Impl.Req.Collection state must be Open or Closed.')
                )
            if (
                previous is not None
                and previous.data.get("state") == "Closed"
                and state == "Open"
            ):
                reopened_at = _optional_timestamp(edition.data.get("reopened_at"))
                reopen_until = _optional_timestamp(previous.data.get("reopen_until"))
                if (
                    reopened_at is None
                    or reopen_until is None
                    or reopened_at > reopen_until
                ):
                    pois.append(
                        diagram_pois.ImplReqReopenWindowInvalid(path=f'collection.{self.ship}.edition.{edition.id}', message='Impl.Req.Collection reopening is outside its declared window.')
                    )
            previous = edition
        return tuple(pois)
