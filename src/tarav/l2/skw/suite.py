"""The Skillware suite: the evaluation of one skill package."""

from tarav.l0.kernel import TaravClass, TypeShip
from tarav.l1.actions.suites import Suite
from tarav.l1.skw.identity import SKW_SKILLS_WORKFLOW_SHIP


# tarav.breadcrumb 3a1966daf2fff7d61e4a8dc15679009f036a14aaf5d7705a3d46883e3029e3de
class SkillwareSuite(Suite):
    """Whatever a skill package's evaluation examines. Its target is the package."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("6c74c235-c1db-4233-8d45-8da10fc3f1cb"),
                          name="Tarav.SKW.Suite", workflow=SKW_SKILLS_WORKFLOW_SHIP)


__all__ = ["SkillwareSuite"]
