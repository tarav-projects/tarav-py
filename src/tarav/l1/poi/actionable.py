"""The capability by which a POI also spins an action."""

from typing import ClassVar

from tarav.l0.kernel import TaravClass, TypeShip

from .primitives import POI
from .workflow import POI_WORKFLOW_SHIP


# tarav.breadcrumb 0657ffdfb85fecb0bd4cf27fc287767cbdd1722a20010ee9bf1862a6d21ef0fc
class ActionablePOI(POI):
    """Capability: a POI of an extending Type also spins one action.

    `action` names the Action Type, by default the POI resolution action. The
    POI stays an event; the action is what persists. A Type that sets `action`
    to None spins nothing. The POI workflow knows only the name: the Actions
    workflow resolves it.
    """

    action: ClassVar[str | None] = "Tarav.Actions.POI.Resolution"

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("a9d4e6c2-8f15-4b73-9e0a-5c7b3d1f6e84"),
                          name="Tarav.POI.Actionable", workflow=POI_WORKFLOW_SHIP)


# tarav.breadcrumb 51eb2b0b1a45b063a05bc60031c6c07ba2b6e50c2d22dba73b69f138821a1c21
class DismissablePOI(ActionablePOI):
    """Capability: the action of a POI of an extending Type may be dismissed.

    Dismissing overrules the check for one exact situation, with a reason. It
    is the softest way an action closes, so a Type has to allow it.
    """

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("b21f7c50-0a4d-4e63-9c18-5d7e3f2a6b90"),
                          name="Tarav.POI.Dismissable", workflow=POI_WORKFLOW_SHIP)


__all__ = ["ActionablePOI", "DismissablePOI"]
