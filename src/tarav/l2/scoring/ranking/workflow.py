"""Ranking Workflow identity and parentage."""

from tarav.l0.kernel import TaravClass, TypeShip, WorkflowShip

from ..workflow import ScoringWorkflow


RANKING_WORKFLOW_SHIP = WorkflowShip('0ba6e2ad-156c-458c-9ee8-57f4046226fe')


class RankingWorkflow(ScoringWorkflow):
    """Score closed cases through comparisons within named tribunals."""
    # tarav.context 6734aba0:3bbb5c37b31f548c

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip('47152e10-395c-488f-ba41-3ea1a89dae15'),
            name='Tarav.Workflow.Ranking',
            workflow=RANKING_WORKFLOW_SHIP,
        )

    @classmethod
    def _workflow_id(cls):
        return RANKING_WORKFLOW_SHIP

    @property
    def workflow(self):
        return ScoringWorkflow()

    constitution = 'Compare closed cases within a tribunal and derive relative scores.'
