"""Assertion Scoring Record registration."""

from tarav.kernel import TaravClass
from tarav.kernel import TypeShip
from tarav.kernel.workflows import TaravWorkflow
from tarav.scoring.identity import SCORING_WORKFLOW_SHIP

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


__all__ = ["ScoringWorkflow"]
