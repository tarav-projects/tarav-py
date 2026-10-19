"""The Action Types of Skillware POIs. The checks that raise them are Situation
Chains (`tarav.l2.skw.chains`); open a POI's Type from finding.help for policy.
"""
from tarav.l0.kernel import TaravClass
from tarav.l0.kernel import TypeShip
from tarav.l1.actions.pois import BlessableResolution
from tarav.l1.skw.identity import SKW_SKILLS_WORKFLOW_SHIP


class StaleContextResolution(BlessableResolution):
    """The action of a StaleContext: an agent may bless it after reviewing the new context."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("0ce3f735-0427-42e6-8e06-db82b3ba7686"),
                          name="Tarav.SKW.POI.StaleContext.Resolution", workflow=SKW_SKILLS_WORKFLOW_SHIP)


class StaleGenerationResolution(BlessableResolution):
    """The action of a StaleGeneration: blessed once the output is assessed acceptable."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("c904ffa1-26c5-40f8-a526-90a5776784e2"),
                          name="Tarav.SKW.POI.StaleGeneration.Resolution", workflow=SKW_SKILLS_WORKFLOW_SHIP)
