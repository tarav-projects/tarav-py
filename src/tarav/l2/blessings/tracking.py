"""The blessing axis of a POI track record, contributed by the Blessings workflow."""

from collections.abc import Mapping

from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l1.blessings import BlessingStore
from tarav.l1.blessings.workflow import BLESSINGS_WORKFLOW_SHIP
from tarav.l1.poi_tracking import TrackAxis


# tarav.breadcrumb 286722e6e27778b13a37ca19e36843a13d6f5c0c5bb3283693a4722f674c3d6a
class BlessingAxis(TrackAxis):
    """Whether the POI's situation holds a blessing, read from a blessing store.

    The store and its rules are unchanged; this axis only reports its answer
    at the time the axis object was made. Blessing never changes observation:
    a POI can be active and blessed, or passed and blessed.
    """

    key = "blessing"
    values = ("blessed", "unblessed")
    caller_writable = False

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("b66c9c10-5492-4c82-87b1-6d4e1fbd1168"),
                          name="Tarav.Blessings.TrackAxis", workflow=BLESSINGS_WORKFLOW_SHIP)

    def __init__(self, store: BlessingStore) -> None:
        if not isinstance(store, BlessingStore):
            raise TypeError("Expected a BlessingStore")
        self.store = store
        self._blessed: frozenset[str] | None = None

    def derive(self, record: Mapping[str, object]) -> object:
        if self._blessed is None:
            self._blessed = frozenset(
                str(row["poi"]["id"]) for row in self.store.snapshot()["records"]
                if isinstance(row.get("poi"), dict) and row["poi"].get("id"))
        return "blessed" if record["poi_id"] in self._blessed else "unblessed"


__all__ = ["BlessingAxis"]
