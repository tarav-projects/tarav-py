"""tarav.lines.references: extracted legacy definitions; identities and storage labels preserved."""

from __future__ import annotations

from pydantic import ConfigDict
from typing import Literal
from tarav.l0.kernel import Ship
from tarav.l0.kernel import TaravObject
from tarav.unsorted.primitives import _uuid
from pydantic import field_validator
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any
    from collections.abc import Mapping

class DiagramLocationInterface(TaravObject.RecordInterface):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    model_ship: str
    block_ship: str
    line_ship: str

    @field_validator("model_ship", "block_ship", "line_ship")
    @classmethod
    def validate_uuid(cls, value: str) -> str:
        return _uuid(value, field="Annotation.location")


class DiagramBlockLocationInterface(TaravObject.RecordInterface):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    model_ship: str
    block_ship: str

    @field_validator("model_ship", "block_ship")
    @classmethod
    def validate_uuid(cls, value: str) -> str:
        return _uuid(value, field="Annotation.location")


class DiagramArgumentReferenceInterface(TaravObject.RecordInterface):
    """Stable reference used by a free-standing Line.Annotation."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    namespace_id: str
    kind: Literal["ship", "edition", "annotation"]
    id: str

    @field_validator("namespace_id", "id")
    @classmethod
    def validate_uuid(cls, value: str) -> str:
        return _uuid(value, field="Argument.Reference")


class DiagramHostReferenceInterface(TaravObject.RecordInterface):
    """Organizational host of one Diagram Ship edition."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    kind: Literal["model", "collection"]
    id: str

    @field_validator("id")
    @classmethod
    def validate_uuid(cls, value: str) -> str:
        return _uuid(value, field="Edition.host.id")


def _record_host(
    record: Mapping[str, Any], model_ship: str
) -> DiagramHostReferenceInterface:
    value = record.get("host")
    return (
        DiagramHostReferenceInterface.model_validate(value)
        if value is not None
        else DiagramHostReferenceInterface(kind="model", id=model_ship)
    )


def _location_ships(
    location: DiagramLocationInterface | DiagramBlockLocationInterface,
) -> tuple[Ship, ...]:
    return tuple(Ship(value) for value in location.model_dump(mode="json").values())
