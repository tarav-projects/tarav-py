"""Typed records retained by Breadcrumb workflows."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import ConfigDict, Field

from tarav.l0.kernel import TypedState
from tarav.l0.kernel import TaravClass, entity
from tarav.l0.kernel import DirectoryRecord, TaravObject, TypeShip
from tarav.l1.references import FilePositionReference
from tarav.l1.references.git import GitCommitMessagePositionReference
from tarav.l1.breadcrumbs.identity import BREADCRUMBS_WORKFLOW_SHIP


BreadcrumbId = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class Breadcrumb(TypedState, DirectoryRecord):
    """Stable identity for one surface anchor."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('0ea69933-56a5-4e93-ade6-157ae70731d8'),
            name='Tarav.Breadcrumb',
            workflow=BREADCRUMBS_WORKFLOW_SHIP,
        )
    class RecordInterface(DirectoryRecord.RecordInterface):
        model_config = ConfigDict(strict=True, extra="forbid")

        type: Literal["Tarav.Breadcrumb"]
        id: BreadcrumbId

    class Records(DirectoryRecord.Records):
        def record_example(self) -> dict[str, object]:
            cls = self._owner
            return {"type": entity(cls).name, "id": "0" * 64}



class LocatorHints(TaravObject.RecordInterface):
    model_config = ConfigDict(strict=True, extra="forbid")

    previous_line: str | None = None
    next_line: str | None = None


class LocatorObservation(TypedState, TaravObject):
    """One append-only observation of a Breadcrumb's file position."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('4a9dcdfb-31d6-46ab-9b86-d18667114ad8'),
            name='Tarav.Breadcrumb.LocatorObservation',
            workflow=BREADCRUMBS_WORKFLOW_SHIP,
        )
    class RecordInterface(TaravObject.RecordInterface):
        model_config = ConfigDict(strict=True, extra="forbid")

        type: Literal["Tarav.Breadcrumb.LocatorObservation"]
        breadcrumb_id: BreadcrumbId
        observed_at: str
        locator: (
            FilePositionReference.RecordInterface
            | GitCommitMessagePositionReference.RecordInterface
        )
        hints: LocatorHints | None = None

    class Records(TaravObject.Records):
        def record_example(self) -> dict[str, object]:
            cls = self._owner
            return {
                "type": entity(cls).name,
                "breadcrumb_id": "0" * 64,
                "observed_at": "1970-01-01T00:00:00Z",
                "locator": FilePositionReference.records.record_example(),
            }



__all__ = [
    "Breadcrumb",
    "BreadcrumbId",
    "LocatorHints",
    "LocatorObservation",
]
