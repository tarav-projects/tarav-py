"""Minimal capability for objects that expose identified Assertions."""

from abc import ABC, abstractmethod
from collections.abc import Mapping

from tarav.l0.kernel import TaravClass, TaravEntity, TaravType, TypeShip

from .workflow import ASSERTIONS_WORKFLOW_SHIP


class Assertable(TaravType, ABC):
    """A subject that exposes identified Assertions under durable labels."""

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip('9e2c02a0-5ebc-460b-bb8a-829f8c42dddf'),
            name='Tarav.Assertions.Assertable',
            workflow=ASSERTIONS_WORKFLOW_SHIP,
        )

    @property
    @abstractmethod
    def assertions(self) -> Mapping[str, TaravEntity]:
        """Return labeled Assertions for this exact subject edition."""
