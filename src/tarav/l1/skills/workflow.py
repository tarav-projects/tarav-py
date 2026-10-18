"""The Skills Workflow: what a skill is, independently of how it is built or used."""

from tarav.l0.kernel import TaravClass, TaravWorkflow, TypeShip, WorkflowShip

SKILLS_WORKFLOW_SHIP = WorkflowShip("3839e290-7fe6-4043-b077-2eb6e66c3f50")


# tarav.breadcrumb 5e85cabc2623
class SkillsWorkflow(TaravWorkflow):
    constitution = ("Represent skills, folders an agent harness loads through their "
                    "SKILL.md, and the primitives every kind of skill shares.")

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip("e401b4d6-ea45-41e8-9d34-fe0827bc7251"),
            name="Tarav.Workflow.Skills",
            workflow=SKILLS_WORKFLOW_SHIP,
        )

    @classmethod
    def _workflow_id(cls):
        return SKILLS_WORKFLOW_SHIP
