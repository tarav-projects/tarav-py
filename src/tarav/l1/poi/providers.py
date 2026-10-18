"""Optional capability for objects that can describe current POIs."""

from tarav.l0.kernel import TaravClass, TaravType, TypeShip

from .workflow import POI_WORKFLOW_SHIP


# tarav.breadcrumb b36fb9bdd621
class POIProvider(TaravType):
    """Expose POIs without collecting, persisting, or raising them."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("4db20a18-a698-4d77-b4f8-5687024870ca"),
            name="Tarav.POI.Provider",
            workflow=POI_WORKFLOW_SHIP,
        )

    def pois(self):
        raise NotImplementedError
