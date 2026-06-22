"""`materialize` — the only explicit home-write primitive.

Resolve an account's active `Auth.Data.Artifact` for a method and write its
`Auth.Data` into a home via ``Auth.Method.materialize``. Pure write — no
read-back, no sync, no promote. By `Capture.Over.Materialization` this is the
sole path that mutates a home. See the `Account.Management` appendix in `agentos-pkg`.
"""

from __future__ import annotations

from pathlib import Path

from agentos._core.errors import CliError
from agentos.agent.account_model import active_artifact_id, read_artifact
from agentos.agent.auth_method import AuthMethod


def materialize_active(method: AuthMethod, account: str, home: Path) -> str:
    """Materialize the account's active artifact for ``method`` into ``home``.

    Returns the materialized artifact id. Raises if there is no active artifact
    or its payload is missing. Does not touch the registry or the active pointer.
    """

    artifact_id = active_artifact_id(method.provider, account, method.name)
    if artifact_id is None:
        raise CliError(f"no active artifact to materialize: {method.provider}.{account}.{method.name}")
    auth_data = read_artifact(method.provider, artifact_id)
    if auth_data is None:
        raise CliError(f"active artifact payload missing: {method.provider}/{artifact_id}")
    method.materialize(auth_data, home)
    return artifact_id


__all__ = ["materialize_active"]
