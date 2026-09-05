"""Tarav Assertion Scoring public domain surface."""

from .model import (
    GROUNDING_ASSERTION_TYPE,
    GROUNDING_TASK_TYPE,
    POOL_TYPE,
    RESULT_TYPE,
    RUN_TYPE,
    SCORE_COMPUTATION_TYPE,
    SCORE_DEFINITION_TYPE,
    ScoringError,
    WIN_RATE_SCORE,
    builtin_score_definition,
    compute_win_rate_score,
    create_grounding_task,
    create_pool,
    create_result,
    create_run,
    render_task,
    validate_record,
)
from .repository import ScoringRepository, default_scoring_root


__all__ = [
    "GROUNDING_ASSERTION_TYPE",
    "GROUNDING_TASK_TYPE",
    "POOL_TYPE",
    "RESULT_TYPE",
    "RUN_TYPE",
    "SCORE_COMPUTATION_TYPE",
    "SCORE_DEFINITION_TYPE",
    "ScoringError",
    "ScoringRepository",
    "WIN_RATE_SCORE",
    "builtin_score_definition",
    "compute_win_rate_score",
    "create_grounding_task",
    "create_pool",
    "create_result",
    "create_run",
    "default_scoring_root",
    "render_task",
    "validate_record",
]
