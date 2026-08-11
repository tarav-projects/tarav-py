# $kw: --from Account.Management
"""The `Auth.Data.Materialization` primitive — push `Active.Auth.Data` into homes.

`materialize_account` is the singular primitive: archive whatever a home currently
holds (`Capture.Over.Materialization`), then write the account/method's active
`Auth.Ref` payload into that home — unless the home already holds it (the stale
gate: an aligned home is left untouched). `materialize_all` is the fleet
reconciler — it loops the profile homes `status`/`capture` collect and
materializes each home's resolved account/method, skipping homes with no safe
target. The CLI is a thin consumer of these primitives.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agentos._core.errors import CliError
from agentos.agent import auth_registry as R
from agentos.agent.account_status_report import collect_home_targets
from agentos.agent.accounts_log import append_account_event
from agentos.agent.auth_method_registry import auth_method_for_class, read_home_auth


@dataclass(frozen=True)
class MaterializeResult:
    provider: str
    account: str
    method: str
    home: Path
    active_ref: str | None
    captured_ref: str | None
    status: str


def materialize_account(
    provider: str, account: str, method: str, home: Path, *, check: bool = False
) -> MaterializeResult:
    """Materialize ``account/method``'s active `Auth.Ref` into ``home``.

    Captures the home's live `Auth.Data` first. If the home already holds the active
    ref it is left untouched (``status="aligned"``). ``check`` previews without
    writing the home (``status="check"``). Raises `CliError` when the auth method is
    unknown, there is no active ref, or its payload cannot be resolved.
    """

    auth_class = R.method_class(provider, account, method)
    auth_method = auth_method_for_class(provider, auth_class) if auth_class else None
    if auth_method is None:
        raise CliError(f"unknown auth method for {provider} {account}/{method}")

    active_id = R.active_ref(provider, account, method)
    if active_id is None:
        raise CliError(f"no active Auth.Ref for {provider} {account}/{method}")
    artifact = R.auth_data_for_ref(provider, account, method, active_id)
    if artifact is None:
        raise CliError(f"active Auth.Data payload not found for ref: {active_id}")


    captured_id = None
    aligned = False
    live = auth_method.read_auth_data(home)
    if live is not None:
        live_ref = auth_method.ref_id(live)
        captured_id = R.store_artifact(provider, live)
        identity = auth_method.extract_identity(live)
        if identity is not None and not R.is_captured(provider, account, method, live_ref):
            R.append_capture(
                provider, account=account, method=method, auth_class=auth_method.name,
                auth_ref=identity, ref_id=live_ref, artifact_id=captured_id,
            )
        aligned = live_ref == active_id


    if aligned:
        status = "aligned"
    elif check:
        status = "check"
    else:
        auth_method.materialize(artifact, home)
        status = "materialized"
        append_account_event(
            event="materialize", provider=provider, account=account, method=method,
            home=home, payload={"active_ref": active_id, "captured_ref": captured_id},
        )

    return MaterializeResult(
        provider=provider, account=account, method=method, home=home,
        active_ref=active_id, captured_ref=captured_id, status=status,
    )


def _home_target_account_method(provider: str, home: Path, candidates: frozenset[str]) -> tuple[str, str] | None:
    """Resolve the listed ``account/method`` a home belongs to from its content.

    Reads the home, resolves the identity to an account, and returns it only when it
    matches one of the home's profile candidates. None when the home is empty, or its
    identity is an orphan / not among the candidate accounts (no safe target).
    """

    candidate_accounts = {c.split("/", 1)[0] for c in candidates}
    found = read_home_auth(provider, home)
    if found is None:
        return None
    account = R.resolve_account_by_identity(provider, found.identity) if found.identity is not None else None
    if account is None or account not in candidate_accounts:
        return None
    method = R.method_for_class(provider, account, found.method.name)
    if method is None:
        return None
    return account, method


def materialize_all(provider: str, *, check: bool = False) -> list[MaterializeResult]:
    """Reconcile every profile home for ``provider`` to its active `Auth.Ref`.

    For each home, resolve which listed ``account/method`` it belongs to from its
    current content, then `materialize_account` it (stale-only via the gate). Homes
    that read as empty / orphan / unlisted have no safe target and are skipped.
    """

    results: list[MaterializeResult] = []
    for target in collect_home_targets(provider):
        resolved = _home_target_account_method(provider, target.home, target.candidates)
        if resolved is None:
            results.append(MaterializeResult(
                provider=provider, account="", method="", home=target.home,
                active_ref=None, captured_ref=None, status="skipped",
            ))
            continue
        account, method = resolved
        results.append(materialize_account(provider, account, method, target.home, check=check))
    return results


__all__ = ["MaterializeResult", "materialize_account", "materialize_all"]
