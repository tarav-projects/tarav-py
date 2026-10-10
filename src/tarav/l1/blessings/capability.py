"""Blessability as an explicit POI subtype capability."""

from copy import deepcopy

from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l1.poi import IdentifiedPOI
from tarav.l1.poi.actionable import DismissablePOI

from .workflow import BLESSINGS_WORKFLOW_SHIP


# tarav.breadcrumb 55f9796bac28bfd6786d615eea8b77fad9bd2686d8af652ee50392e01d5cddad
class BlessablePOI(DismissablePOI):
    """A POI whose identified situation can receive an attributed blessing.

    What may be blessed may be dismissed: a blessing is the earlier form of
    dismissing the POI's action, and this capability carries both until the
    blessing records are retired.
    """

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("7d28d632-2ec5-4c5a-997f-224ad508ce9d"),
            name="Tarav.Blessings.BlessablePOI",
            workflow=BLESSINGS_WORKFLOW_SHIP,
        )

    def blessing_snapshot(self) -> dict:
        if not isinstance(self, IdentifiedPOI):
            raise TypeError("BlessablePOI must also provide IdentifiedPOI occurrence data")
        return deepcopy(self.as_dict(detail=True))
