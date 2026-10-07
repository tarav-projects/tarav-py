"""Assertion Scoring Record registration."""

from tarav.l0.kernel import TaravClass
from tarav.l0.kernel import TypeShip
from tarav.l0.kernel.workflows import TaravWorkflow
from tarav.l2.scoring.identity import SCORING_WORKFLOW_SHIP

class ScoringWorkflow(TaravWorkflow):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('01eafc16-1a9b-4a19-b27c-422d3c3e8a0b'),
            name='Tarav.Workflow.Scoring',
            workflow=SCORING_WORKFLOW_SHIP,
        )

    @classmethod
    def _workflow_id(cls):
        return SCORING_WORKFLOW_SHIP
    workflow_name = "scoring"
    constitution = "Assess semantic assertions and expose their scores and findings."

    @classmethod
    def provider(cls, root, records):
        # tarav.breadcrumb 530e96e33eeddd3f67ddfa11f935401172ced777a6c7085b4b666b907934869c
        from .provider import ScoringProvider

        return ScoringProvider(root, records)


__all__ = ["ScoringWorkflow"]
