"""The agent profile-check primitive — the read-only pre-run fitness gate.

It answers one question: "is this fully-specified agent fit to run *right now*?" —
without spawning, writing a home, or making a provider call. It runs a fixed set of
canonical checkpoints over a resolved agent and reports each as pass/fail with a reason.

`profile_check` is exposed as the `agent.profile_check()` capability method
(`RunnableMixin`); this module owns the checkpoint logic and the `_profile_check`
assembler behind it. Consumers call `agent.profile_check()`, never `_profile_check`.

Fitness is distinct from legality: the resolve-time span checks
(`profile_scope.validate_account_override` / `select_allowed_home`) gate which
account/home a profile *may* use; these checkpoints gate whether the named home/account
match reality.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agentos.agent import auth_registry as R
from agentos.agent.account_status_report import HomeTarget, status_for_home


@dataclass(frozen=True)
class CheckpointResult:
    id: str
    passed: bool
    reason: str | None  # None iff passed


@dataclass(frozen=True)
class ProfileCheck:
    checkpoints: tuple[CheckpointResult, ...]
    ok: bool  # True iff every checkpoint passed


def _account_registered(provider: str, account: str | None) -> CheckpointResult:
    if account is None:
        return CheckpointResult("account_registered", False, "no account bound to the agent")
    if R.account_exists(provider, account):
        return CheckpointResult("account_registered", True, None)
    return CheckpointResult(
        "account_registered", False, f"account not registered: {provider}.{account}"
    )


def _home_exists(home: Path | str | None) -> CheckpointResult:
    if home is None:
        return CheckpointResult("home_exists", False, "no home bound to the agent")
    if Path(home).expanduser().is_dir():
        return CheckpointResult("home_exists", True, None)
    return CheckpointResult("home_exists", False, f"home does not exist: {home}")


def _home_aligned(
    provider: str, home: Path | str | None, account: str | None
) -> CheckpointResult:
    if home is None:
        return CheckpointResult("home_aligned", False, "no home to check")
    candidates = frozenset({account}) if account else frozenset()
    target = HomeTarget(
        home=Path(home).expanduser(), provider=provider, candidates=candidates
    )
    entry = status_for_home(target)
    status = str(entry.get("status"))
    if status == "aligned":
        return CheckpointResult("home_aligned", True, None)
    reason = entry.get("reason")
    detail = f"{status}: {reason}" if reason else status
    return CheckpointResult("home_aligned", False, detail)


def _account_id(account: object) -> str | None:
    return getattr(account, "account", None)


def _profile_check(agent) -> ProfileCheck:
    """Run the canonical checkpoints over ``agent`` and assemble the report.

    Collect-all — every checkpoint runs so the report shows all failures at once.
    """
    provider = agent.provider
    account = _account_id(agent.account)
    home = agent.home
    checkpoints = (
        _account_registered(provider, account),
        _home_exists(home),
        _home_aligned(provider, home, account),
    )
    return ProfileCheck(
        checkpoints=checkpoints, ok=all(c.passed for c in checkpoints)
    )


__all__ = ["CheckpointResult", "ProfileCheck"]
