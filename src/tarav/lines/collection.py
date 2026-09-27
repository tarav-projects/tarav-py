"""tarav.lines.collection: extracted legacy definitions; identities and storage labels preserved."""

from __future__ import annotations

from tarav.unsorted.contracts import Finding
from tarav.unsorted.primitives import _optional_timestamp
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tarav.lines.records import CollectionEditionRecord
    from tarav.lines.references import DiagramArgumentReferenceInterface
    from tarav.lines.references import DiagramHostReferenceInterface
    from tarav.unsorted.constants import JsonObject

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
    findings: tuple[Finding, ...]

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

    def mechanical_findings(self) -> tuple[Finding, ...]:
        return ()


class ImplReqCollection(DiagramCollection):
    @property
    def state(self) -> str | None:
        current = self.current_edition
        if current is None:
            return None
        value = current.data.get("state")
        return value if isinstance(value, str) else None

    def mechanical_findings(self) -> tuple[Finding, ...]:
        findings: list[Finding] = []
        previous: CollectionEditionRecord | None = None
        for edition in self.editions:
            state = edition.data.get("state")
            if state not in {"Open", "Closed"}:
                findings.append(
                    Finding(
                        "impl-req-state-invalid",
                        f"collection.{self.ship}.edition.{edition.id}.data.state",
                        "Impl.Req.Collection state must be Open or Closed.",
                    )
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
                    findings.append(
                        Finding(
                            "impl-req-reopen-window-invalid",
                            f"collection.{self.ship}.edition.{edition.id}",
                            "Impl.Req.Collection reopening is outside its declared window.",
                        )
                    )
            previous = edition
        return tuple(findings)
