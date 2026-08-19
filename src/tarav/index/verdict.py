# $kw: --from State.Estimation --note [DF] a state is minimally a value + err/unknown pair, so an assertion returns a verdict rather than a defect
# $kw: --from State.Estimation --note [DC] the three-valued vocabulary is the old design's CheckStatus; only the evaluator axis is new
# $kw: --from Convergent.Justification --note [DC] the unproduced Evaluator tiers are declared so adding one later cannot silently change what an existing passed meant
"""Verdicts — what an assertion actually produces.

A state is minimally a `value + err/unknown` pair, and using one without estimating that pair
is the antipattern this module exists to prevent. An assertion is the estimator: it tests a
fundamental of the state and reports which of three things it found.

```text
passed     checked, and it holds
failed     checked, and it does not
blocked    could not check
```

Two-valued checking cannot distinguish `passed` from `blocked`, so it reports *clean* for an
index nothing verified — the same defect the states themselves were being cured of, one level
up.

**The vocabulary is the old design's.** `tarav.chatlas.index_check_model` already carries
`CheckStatus = passed | failed | blocked` and a `GateResult` declaring why a check could not
run, so this is not a new idea and does not get a new name. What this design changes is *where the
verdict lives*: the old design blocked a whole check, this one also lets a single subject be blocked,
because the err/unknown pair belongs to the **state** and not only to the checker.

`Evaluator` is the genuinely new axis. `passed` from cheap deterministic code and `passed`
from an agent's semantic judgment are different amounts of trust, and a system that prints
them identically is lying by omission. Only `CODE` is produced today; naming the axis now
means adding a tier later cannot silently change what an existing `passed` meant.

There is deliberately no `severity`. tarav1's `LinterFinding` carries `error | warning`;
this design drops it under `Signal.Not.Semantics` — ranking what a finding *means* is the agent's
work, and a severity field is the route by which semantics would be smuggled back into the
signal.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Status(StrEnum):
    #: The assertion ran and holds.
    PASSED = "passed"
    #: The assertion ran and does not hold.
    FAILED = "failed"
    #: The assertion could not run. Not a defect, and not clean either.
    BLOCKED = "blocked"


class Evaluator(StrEnum):
    """What decided the verdict — cheap, semantic, or authoritative.

    The escalation ladder: code overdetects into the agent's inbox, the agent escalates into
    the user's. Each tier is allowed to be wrong in the direction of the next one.
    """

    CODE = "code"
    AGENT = "agent"
    USER = "user"


@dataclass(frozen=True, slots=True)
class GateResult:
    """Whether a check can run at all — tarav1's shape, kept.

    A precondition the check cannot supply for itself: the archive is absent, the project is
    not a git repository. Unmet, the check reports `blocked` once rather than emitting a
    blocked finding per subject.
    """

    allowed: bool
    reason: str | None = None

    @classmethod
    def ok(cls) -> GateResult:
        return cls(allowed=True)

    @classmethod
    def blocked(cls, reason: str) -> GateResult:
        return cls(allowed=False, reason=reason)


__all__ = ["Evaluator", "GateResult", "Status"]
