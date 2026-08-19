# $kw: --from Normalization.Pipeline --note [DC] the trust tier is Delta.Normalization substrate, so it outlives the session model that currently reads it
"""How much of an existing model a `Delta.Normalization` pass re-checks against source.

`Normalization.Trust.Tier` is a `Normalization.Pipeline` concept, not a property of any
one `Normal.Model`: it says how much verification a caller is paying for. It lives here
rather than beside a normalizer because the CLI and the hook set it, the pipeline reads
it, and neither should have to import a session model to reach a context variable.
"""

from __future__ import annotations

from contextvars import ContextVar

TRUST_APPEND = "append"
TRUST_VERIFY = "verify"
TRUST_REBUILD = "rebuild"
TRUST_TIERS = (TRUST_APPEND, TRUST_VERIFY, TRUST_REBUILD)

_TRUST_CONTEXT: ContextVar[str] = ContextVar("chatlas_delta_trust", default=TRUST_VERIFY)


def set_trust_tier(tier: str) -> None:
    if tier not in TRUST_TIERS:
        raise ValueError(
            f"unsupported normalization trust tier: {tier} (choose from {', '.join(TRUST_TIERS)})"
        )
    _TRUST_CONTEXT.set(tier)


def current_trust_tier() -> str:
    return _TRUST_CONTEXT.get()


__all__ = [
    "TRUST_APPEND",
    "TRUST_VERIFY",
    "TRUST_REBUILD",
    "TRUST_TIERS",
    "set_trust_tier",
    "current_trust_tier",
]
