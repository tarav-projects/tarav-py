"""A shallow result object for scoring workflows."""

from tarav.l0.kernel import TaravClass, TaravObject, TypeShip

from .identity import SCORING_WORKFLOW_SHIP


class Score(TaravObject):
    """A typed scoring result; particular methods define its payload."""
    # tarav.context 6734aba0:33c08d1be038423c

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip('cc7bae4f-ba4e-4693-b0e9-2fa4049b9ef3'),
            name='Tarav.Scoring.Score',
            workflow=SCORING_WORKFLOW_SHIP,
        )
