"""The `Auth.Data.Activation` primitive — point `Active.Auth.Data` at a chosen ref.

`activate` resolves a (possibly abbreviated) `Auth.Ref` against the
`account/method` capture pool, checks its payload is resolvable, and sets the
active pointer. Registry-only: it never reads or writes a home. The CLI
`activate` handler is a thin consumer of this primitive.
"""

from __future__ import annotations

from dataclasses import dataclass

from agentos._core.errors import CliError
from agentos.agent import auth_registry as R


@dataclass(frozen=True)
class ActivateResult:
    provider: str
    account: str
    method: str
    ref_id: str  # the resolved, now-active Auth.Ref id


def activate(provider: str, account: str, method: str, ref_prefix: str) -> ActivateResult:
    """Activate the ref matching ``ref_prefix`` for ``account/method``.

    ``ref_prefix`` is resolved against the capture pool (a unique prefix or a full
    ref); ambiguous/no match raises `CliError`. The resolved ref's payload must be
    present in the registry, else `CliError`.
    """

    ref = R.resolve_ref_prefix(provider, account, method, ref_prefix)
    if R.auth_data_for_ref(provider, account, method, ref) is None:
        raise CliError(f"no captured Auth.Data for ref: {ref}")
    R.set_active(provider, account, method, ref)
    return ActivateResult(provider=provider, account=account, method=method, ref_id=ref)


__all__ = ["ActivateResult", "activate"]
