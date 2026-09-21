"""Assertion Scoring Record registration."""

from tarav.harness.workflows import Workflow

from .model import SCORING_RECORD_TYPES


class ScoringWorkflow(Workflow):
    name = "scoring"
    record_types = SCORING_RECORD_TYPES


__all__ = ["ScoringWorkflow"]
