# $kw: ^tournament-public --from Agentos.Tournament --note [DF] the public import surface for the domain-blind comparative-evaluation engine ^<anchor-on-landing>
"""Domain-blind comparative evaluation: pairwise matches judged by an agent."""

from .depot import resolve_depot_root
from .tickets import Ticket, TicketError, TicketStore
from .contract import (
    MAX_ARITY,
    OUTCOME_NO_CONTEST,
    POSITION_LABELS,
    REFUSAL_REASON_FIELD,
    ContractError,
    parse_judge_answer,
    validate,
    validate_verdict_answer,
)
from .hooks import (
    HookContext,
    HookError,
    HookLoadError,
    HookPurityError,
    HookReturnError,
    TournamentDefinition,
    load_definition,
    open_definition,
)
from .model import (
    EnvelopeShadowedError,
    MatchIdentityRequiredError,
    Tournament,
    TournamentError,
    Verdict,
    VerdictOutcome,
)
from .report import tournament_report
from .runner import JudgeSpawn, MatchResult, compose_verbatim, run_match, run_pool
from .store import TournamentNotFoundError, TournamentStore

__all__ = [
    "MAX_ARITY",
    "OUTCOME_NO_CONTEST",
    "POSITION_LABELS",
    "REFUSAL_REASON_FIELD",
    "ContractError",
    "EnvelopeShadowedError",
    "HookContext",
    "HookError",
    "HookLoadError",
    "HookPurityError",
    "HookReturnError",
    "JudgeSpawn",
    "MatchIdentityRequiredError",
    "MatchResult",
    "Tournament",
    "TournamentDefinition",
    "TournamentError",
    "TournamentNotFoundError",
    "Ticket",
    "TicketError",
    "TicketStore",
    "TournamentStore",
    "compose_verbatim",
    "resolve_depot_root",
    "Verdict",
    "VerdictOutcome",
    "load_definition",
    "open_definition",
    "parse_judge_answer",
    "tournament_report",
    "run_match",
    "run_pool",
    "validate",
    "validate_verdict_answer",
]
