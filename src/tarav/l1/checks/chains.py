"""Situation Chains: Situation → Check → POI → Action → Closing, modeled as one thing.

A chain is a set of Types that implement the relationships between those
links. Blessing is one Closing of a chain's Action, not a model of its own.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import ClassVar

from tarav.l0.kernel import LiteRecord, TaravClass, TaravObject, TypeShip, entity
from tarav.l1.poi import fingerprint

from . import CHECKS_WORKFLOW_SHIP, CheckPOI, Situation, SituationCheck


# tarav.breadcrumb fca16d458df9
# tarav.breadcrumb caab41739e07
class SituationChain(TaravObject):
    """The Types of one chain and, as an instance, one situation of it.

    `Check` is the chain's atomic Check, built with the situation its caller
    creates; `POIs` are the POI Types it may raise. Each POI Type names its
    Action Type (`action`), and an Action Type its Closings by its exits.
    Defining a chain binds `chain` on its Check and POI Types; a link belongs
    to one chain.

    An instance is one situation. Its identity, like that of every object of
    the chain, is its Type and that situation, hashed. Consumers decide what
    they instantiate; nothing requires a chain to be instantiated.
    """

    Check: ClassVar[type[SituationCheck]]
    POIs: ClassVar[tuple[type[CheckPOI], ...]] = ()

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("59204ccd-d558-49eb-8db8-60bacd68af87"),
                          name="Tarav.Checks.SituationChain", workflow=CHECKS_WORKFLOW_SHIP)

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        if "Check" not in cls.__dict__:
            return  # a family of chains, not a chain
        for link in (cls.Check, *cls.POIs):
            bound = link.__dict__.get("chain")
            if bound is not None and bound is not cls:
                raise TypeError(f"{entity(link).name} already belongs to {entity(bound).name}")
        for link in (cls.Check, *cls.POIs):
            link.chain = cls

    def __init__(self, situation: Mapping[str, object] | LiteRecord) -> None:
        super().__init__()
        situation_type = type(self).Check.SituationType
        if not issubclass(situation_type, Situation):
            raise TypeError("A chain's situation is a Situation")
        self.situation = situation_type(situation)

    @property
    def identity(self) -> str:
        return fingerprint([str(entity(type(self)).id), self.situation.to_json_value()])

    def check(self, **resources) -> SituationCheck:
        """The chain's Check over this situation; `resources` are what it reads, not what it is about."""
        return type(self).Check(situation=self.situation, **resources)


__all__ = ["SituationChain"]
