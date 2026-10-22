"""Product-agnostic coordinates maintained across committed states."""

from pathlib import Path

from tarav.l0.kernel import TaravClass, TaravWorkflow, TypeShip, WorkflowShip

PRODUCT_MAPPING_SHIP = WorkflowShip("ef1dc42a-fd98-43b8-a30d-e68bf742de34")


# tarav.breadcrumb 64f143c9cb0b
class ProductMappingWorkflow(TaravWorkflow):
    constitution = (
        "Map committed product bytes to persistent chunk identities; retain exact "
        "states and explicit maintainer decisions without inferring semantic identity."
    )

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("7ce330af-8b67-4b6e-8af1-42a1432f8fb9"),
                          name="Tarav.Workflow.ProductMapping", workflow=PRODUCT_MAPPING_SHIP)

    @classmethod
    def _workflow_id(cls):
        return PRODUCT_MAPPING_SHIP

    @classmethod
    def help(cls):
        return {**super().help(), "instructions": str(Path(__file__).with_name("README.md"))}
