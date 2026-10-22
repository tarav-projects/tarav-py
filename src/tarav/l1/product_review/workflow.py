"""Review records describe attention paid, without endorsing product content."""

from pathlib import Path

from tarav.l0.kernel import TaravClass, TaravWorkflow, TypeShip, WorkflowShip

PRODUCT_REVIEW_SHIP = WorkflowShip("049c441b-b6d6-4617-94bf-252f822f58be")


class ProductReviewWorkflow(TaravWorkflow):
    constitution = "Track completed reviews of exact product batches, independently of their outcomes."

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("49bbdc9a-3e47-435f-83f1-a5b3c7604395"),
                          name="Tarav.Workflow.ProductReview", workflow=PRODUCT_REVIEW_SHIP)

    @classmethod
    def _workflow_id(cls):
        return PRODUCT_REVIEW_SHIP

    @classmethod
    def help(cls):
        return {**super().help(), "instructions": str(Path(__file__).with_name("README.md"))}
