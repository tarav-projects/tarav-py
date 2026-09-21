"""Typed records retained by Breadcrumb workflows."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import ConfigDict, Field

from tarav.harness import DirectoryRecord, TaravObject, TypeShip
from tarav.references import FilePositionReference


BreadcrumbId = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class Breadcrumb(DirectoryRecord):
    """Stable identity for one surface anchor."""

    type_ship = TypeShip("0ea69933-56a5-4e93-ade6-157ae70731d8")
    type_name = "Tarav.Breadcrumb"

    class RecordInterface(DirectoryRecord.RecordInterface):
        model_config = ConfigDict(strict=True, extra="forbid")

        type: Literal["Tarav.Breadcrumb"]
        id: BreadcrumbId

    @classmethod
    def json_example(cls) -> dict[str, object]:
        return {"type": cls.type_name, "id": "0" * 64}


class LocatorHints(TaravObject.RecordInterface):
    model_config = ConfigDict(strict=True, extra="forbid")

    previous_line: str | None = None
    next_line: str | None = None


class LocatorObservation(TaravObject):
    """One append-only observation of a Breadcrumb's file position."""

    type_ship = TypeShip("4a9dcdfb-31d6-46ab-9b86-d18667114ad8")
    type_name = "Tarav.Breadcrumb.LocatorObservation"

    class RecordInterface(TaravObject.RecordInterface):
        model_config = ConfigDict(strict=True, extra="forbid")

        type: Literal["Tarav.Breadcrumb.LocatorObservation"]
        breadcrumb_id: BreadcrumbId
        observed_at: str
        locator: FilePositionReference.RecordInterface
        hints: LocatorHints | None = None

    @classmethod
    def json_example(cls) -> dict[str, object]:
        return {
            "type": cls.type_name,
            "breadcrumb_id": "0" * 64,
            "observed_at": "1970-01-01T00:00:00Z",
            "locator": FilePositionReference.json_example(),
        }


__all__ = [
    "Breadcrumb",
    "BreadcrumbId",
    "LocatorHints",
    "LocatorObservation",
]
