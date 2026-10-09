"""The Agents workflow: how Tarav models and asks things of agent harnesses."""

from tarav.l0.kernel import TaravClass, TaravWorkflow, TypeShip
from tarav.l1.agent.identity import AGENTS_WORKFLOW_SHIP


# tarav.breadcrumb 3895998adfc2738344639236b2fb2168692d109b5ddcebc30a3ec651909b4939
class AgentsWorkflow(TaravWorkflow):
    workflow_name = "agents"
    constitution = (
        "Model the agent harnesses Tarav works with and interface with their providers."
    )

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("37cad996-dd42-4169-ba04-cf06550232fb"),
            name="Tarav.Workflow.Agents",
            workflow=AGENTS_WORKFLOW_SHIP,
        )

    @classmethod
    def _workflow_id(cls):
        return AGENTS_WORKFLOW_SHIP
