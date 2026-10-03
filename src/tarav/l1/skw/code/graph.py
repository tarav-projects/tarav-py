"""Common Type contract for statically analyzed reader routes."""

from abc import ABC, abstractmethod

from tarav.l0.kernel import TaravClass, TaravType, TypeShip
from tarav.l1.skw.identity import SKW_CODE_WORKFLOW_SHIP


class ReadingGraph(TaravType, ABC):
    """A declared probable route through an instruction surface.

    A ReadingGraph describes a route that surface authors intend readers to
    follow. It does not observe or constrain an agent's actual navigation.
    """
    # tarav.breadcrumb 52e07fb3575af6dda9407ec605785cf8835116b08c805ce0069f25d8c50820ce

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("db40788b-bcda-4e18-ba4e-81d041943ede"),
            name="Tarav.SKW.Code.ReadingGraph",
            workflow=SKW_CODE_WORKFLOW_SHIP,
        )

    @abstractmethod
    def analyze(self, **options: object) -> dict[str, object]:
        """Analyze the context available along this graph's declared routes."""
