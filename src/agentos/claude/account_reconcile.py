from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agentos._core.errors import CliError
from agentos._core.path_validation import validate_string_for_path
from agentos._core.project import agentos_home_dir
from agentos.agent.account_reconcile import (
    AccountReconcileAction,
    AccountReconcileRequest,
    AccountReconcileResult,
    AccountReconcileWarning,
)
from agentos.agent.account_registry import (
    load_accounts,
    record_account_event,
)
from agentos.agent.config import load_agent_configs
from agentos.claude.account_registry import (
    CLAUDE_AUTH_KIND,
    CLAUDE_PROVIDER,
    inspect_claude_account_home,
    link_claude_account_to_home,
    register_claude_ambient_auth_from_home,
)


@dataclass(frozen=True)
class _KnownHome:
    home: Path
    source: str
    account: str | None = None
    system_managed: bool = False

    def summary(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "home": str(self.home),
            "source": self.source,
            "system_managed": self.system_managed,
        }
        if self.account is not None:
            payload["account"] = self.account
        return payload


def reconcile_claude_accounts(
    *,
    account: str | None = None,
    home: Path | None = None,
    start_path: Path | str = ".",
    register_discovered: bool = True,
    sync_homes: bool = True,
    check: bool = False,
    record_event: bool = True,
    argv: list[str] | tuple[str, ...] = (),
) -> dict[str, object]:
    request = AccountReconcileRequest(
        provider=CLAUDE_PROVIDER,
        account=_normalize_optional_account(account),
        home=home.expanduser().resolve() if home is not None else None,
        start_path=start_path,
        register_discovered=register_discovered,
        sync_homes=sync_homes,
        check=check,
        argv=tuple(argv),
    )
    result = _reconcile_claude_accounts(request)
    payload = result.summary()
    if record_event and not check:
        record_account_event(
            event_type="agent.accounts.reconcile",
            command="agent accounts reconcile",
            argv=argv,
            status="ok",
            payload={
                "provider": CLAUDE_PROVIDER,
                "account": request.account,
                "home": str(request.home) if request.home is not None else None,
                "scanned_count": len(result.scanned_homes),
                "action_count": len(result.actions),
                "warning_count": len(result.warnings),
            },
        )
    return payload


def discover_claude_reconcile_homes(
    *,
    account: str | None = None,
    home: Path | None = None,
    start_path: Path | str = ".",
) -> tuple[dict[str, object], ...]:
    request = AccountReconcileRequest(
        provider=CLAUDE_PROVIDER,
        account=_normalize_optional_account(account),
        home=home.expanduser().resolve() if home is not None else None,
        start_path=start_path,
        register_discovered=False,
        sync_homes=False,
        check=True,
    )
    return tuple(known_home.summary() for known_home in _known_claude_homes(request))


def _reconcile_claude_accounts(
    request: AccountReconcileRequest,
) -> AccountReconcileResult:
    known_homes = _known_claude_homes(request)
    inspected = tuple(_inspect_known_home(known_home) for known_home in known_homes)
    actions: list[AccountReconcileAction] = []
    warnings: list[AccountReconcileWarning] = []

    fresh_by_account: dict[str, list[tuple[_KnownHome, dict[str, object]]]] = {}
    for known_home, status in inspected:
        classification = _string_or_none(status.get("classification"))
        if classification == "known-account-new-hash":
            matched_account = _single_matching_account(status)
            if matched_account is None:
                warnings.append(
                    _warning(
                        "ambiguous_known_account",
                        known_home=known_home,
                        message="claude auth matched no unique registered account alias",
                        status=status,
                    )
                )
                continue
            if request.account is not None and matched_account != request.account:
                continue
            fresh_by_account.setdefault(matched_account, []).append((known_home, status))
        elif classification == "unknown":
            warnings.append(
                _warning(
                    "unknown_account_auth",
                    known_home=known_home,
                    message="claude auth belongs to an unregistered account; no mutation performed",
                    status=status,
                )
            )
        elif classification == "broken":
            warnings.append(
                _warning(
                    "broken_auth",
                    known_home=known_home,
                    message="claude auth could not be read; no mutation performed",
                    status=status,
                )
            )

    if request.register_discovered:
        actions.extend(
            _register_fresh_artifacts(
                request,
                fresh_by_account=fresh_by_account,
                warnings=warnings,
            )
        )

    if request.sync_homes:
        inspected = tuple(_inspect_known_home(known_home) for known_home in known_homes)
        actions.extend(
            _sync_claude_homes(
                request,
                inspected,
                planned_active_artifacts=_planned_active_artifacts(actions),
            )
        )

    return AccountReconcileResult(
        provider=CLAUDE_PROVIDER,
        scanned_homes=tuple(
            _scanned_home_summary(known_home, status)
            for known_home, status in inspected
        ),
        actions=tuple(actions),
        warnings=tuple(warnings),
        active_artifacts=_active_artifacts(request.account),
        check=request.check,
    )


def _register_fresh_artifacts(
    request: AccountReconcileRequest,
    *,
    fresh_by_account: dict[str, list[tuple[_KnownHome, dict[str, object]]]],
    warnings: list[AccountReconcileWarning],
) -> list[AccountReconcileAction]:
    actions: list[AccountReconcileAction] = []
    for matched_account, candidates in sorted(fresh_by_account.items()):
        registration_candidates = _dedupe_candidates_by_artifact_id(candidates)
        selected = _select_activation_candidate(
            matched_account,
            registration_candidates,
        )
        if len(registration_candidates) > 1:
            warnings.append(
                _multiple_fresh_artifacts_warning(
                    matched_account,
                    registration_candidates,
                )
            )
        actions.extend(
            _register_candidate_actions(
                request,
                account=matched_account,
                candidates=registration_candidates,
                selected=selected,
            )
        )
    return actions


def _multiple_fresh_artifacts_warning(
    account: str,
    candidates: list[tuple[_KnownHome, dict[str, object]]],
) -> AccountReconcileWarning:
    return AccountReconcileWarning(
        kind="multiple_fresh_artifacts",
        account=account,
        message=(
            "multiple fresh claude auth artifacts were observed; "
            "registered them without changing the active artifact"
        ),
        detail={
            "artifact_ids": [
                artifact_id
                for _, status in candidates
                if (artifact_id := _artifact_id_from_status(status)) is not None
            ],
        },
    )


def _register_candidate_actions(
    request: AccountReconcileRequest,
    *,
    account: str,
    candidates: list[tuple[_KnownHome, dict[str, object]]],
    selected: tuple[_KnownHome, dict[str, object]] | None,
) -> list[AccountReconcileAction]:
    actions: list[AccountReconcileAction] = []
    for known_home, status in sorted(candidates, key=lambda item: str(item[0].home)):
        artifact_id = _artifact_id_from_status(status)
        activate = selected is not None and (known_home, status) == selected
        if request.check:
            actions.extend(
                _planned_register_candidate_actions(
                    account=account,
                    known_home=known_home,
                    artifact_id=artifact_id,
                    activate=activate,
                )
            )
            continue
        payload = register_claude_ambient_auth_from_home(
            home=known_home.home,
            account=account,
            register_only=not activate,
            argv=request.argv,
        )
        actions.append(
            AccountReconcileAction(
                kind="registered_artifact",
                account=account,
                home=str(known_home.home),
                artifact_id=artifact_id,
                detail={
                    "artifact_appended": bool(payload.get("artifact_appended")),
                    "activated": activate,
                },
            )
        )
    return actions


def _planned_register_candidate_actions(
    *,
    account: str,
    known_home: _KnownHome,
    artifact_id: str | None,
    activate: bool,
) -> list[AccountReconcileAction]:
    actions = [
        AccountReconcileAction(
            kind="would_register_artifact",
            account=account,
            home=str(known_home.home),
            artifact_id=artifact_id,
        )
    ]
    if activate:
        actions.append(
            AccountReconcileAction(
                kind="would_activate_artifact",
                account=account,
                artifact_id=artifact_id,
            )
        )
    return actions


def _sync_claude_homes(
    request: AccountReconcileRequest,
    inspected: tuple[tuple[_KnownHome, dict[str, object]], ...],
    *,
    planned_active_artifacts: dict[str, str],
) -> list[AccountReconcileAction]:
    actions: list[AccountReconcileAction] = []
    for known_home, status in inspected:
        sync_account = _sync_account_for_home(known_home)
        if sync_account is None:
            continue
        if request.account is not None and sync_account != request.account:
            continue
        classification = _string_or_none(status.get("classification"))
        if classification == "matching-active" and _active_home_account(status) == sync_account:
            continue
        active_artifact_id = (
            planned_active_artifacts.get(sync_account) or _active_artifact_id(sync_account)
        )
        if active_artifact_id is None:
            continue
        if (
            _artifact_id_from_status(status) == active_artifact_id
            and _single_matching_account(status) == sync_account
        ):
            continue
        if request.check:
            actions.append(
                AccountReconcileAction(
                    kind="would_sync_home",
                    account=sync_account,
                    home=str(known_home.home),
                    artifact_id=active_artifact_id,
                )
            )
            continue
        payload = link_claude_account_to_home(
            home=known_home.home,
            account=sync_account,
            argv=request.argv,
        )
        actions.append(
            AccountReconcileAction(
                kind="synced_home",
                account=sync_account,
                home=str(known_home.home),
                artifact_id=active_artifact_id,
                detail={
                    "storage": payload.get("storage"),
                },
            )
        )
    return actions


def _known_claude_homes(request: AccountReconcileRequest) -> tuple[_KnownHome, ...]:
    homes: dict[str, _KnownHome] = {}
    for home in _configured_homes(request.start_path):
        _add_known_home(homes, home)
    for account in _registered_accounts(request.account):
        _add_known_home(
            homes,
            _KnownHome(
                home=_system_home(account),
                source="system",
                account=account,
                system_managed=True,
            ),
        )

    if request.home is not None:
        normalized = str(request.home)
        if normalized not in homes:
            raise CliError(
                f"claude-code reconcile --home is not a known home: {request.home}"
            )
        return (homes[normalized],)
    return tuple(homes[key] for key in sorted(homes))


def _configured_homes(start_path: Path | str) -> tuple[_KnownHome, ...]:
    homes: list[_KnownHome] = []
    for config in load_agent_configs(start_path=start_path):
        if config.provider != CLAUDE_PROVIDER or config.home is None:
            continue
        homes.append(
            _KnownHome(
                home=config.home.expanduser().resolve(),
                source="configured",
                account=config.account.account if config.account is not None else None,
            )
        )
    return tuple(homes)


def _registered_accounts(account: str | None) -> tuple[str, ...]:
    accounts = load_accounts(CLAUDE_PROVIDER).get("accounts")
    if not isinstance(accounts, dict):
        return ()
    names = [
        raw_account
        for raw_account, record in accounts.items()
        if isinstance(raw_account, str)
        and isinstance(record, dict)
        and record.get("auth_kind") == CLAUDE_AUTH_KIND
        and (account is None or raw_account == account)
    ]
    return tuple(sorted(names))


def _system_home(account: str) -> Path:
    return agentos_home_dir() / "agent" / "homes" / CLAUDE_PROVIDER / account


def _add_known_home(homes: dict[str, _KnownHome], known_home: _KnownHome) -> None:
    normalized_home = known_home.home.expanduser().resolve()
    key = str(normalized_home)
    existing = homes.get(key)
    candidate = _KnownHome(
        home=normalized_home,
        source=known_home.source,
        account=known_home.account,
        system_managed=known_home.system_managed,
    )
    if existing is None:
        homes[key] = candidate
        return
    homes[key] = _KnownHome(
        home=existing.home,
        source=",".join(
            sorted(set(existing.source.split(",") + candidate.source.split(",")))
        ),
        account=existing.account or candidate.account,
        system_managed=existing.system_managed or candidate.system_managed,
    )


def _inspect_known_home(known_home: _KnownHome) -> tuple[_KnownHome, dict[str, object]]:
    return known_home, inspect_claude_account_home(home=known_home.home)


def _single_matching_account(status: dict[str, object]) -> str | None:
    matches = status.get("account_registry_matches")
    if not isinstance(matches, list):
        return None
    accounts = sorted(
        {
            account
            for record in matches
            if isinstance(record, dict)
            and (account := _string_or_none(record.get("account"))) is not None
        }
    )
    if len(accounts) != 1:
        return None
    return accounts[0]


def _dedupe_candidates_by_artifact_id(
    candidates: list[tuple[_KnownHome, dict[str, object]]],
) -> list[tuple[_KnownHome, dict[str, object]]]:
    deduped: dict[str, tuple[_KnownHome, dict[str, object]]] = {}
    for known_home, status in sorted(candidates, key=lambda item: str(item[0].home)):
        artifact_id = _artifact_id_from_status(status)
        if artifact_id is None:
            continue
        deduped.setdefault(artifact_id, (known_home, status))
    return [deduped[artifact_id] for artifact_id in sorted(deduped)]


def _select_activation_candidate(
    account: str,
    candidates: list[tuple[_KnownHome, dict[str, object]]],
) -> tuple[_KnownHome, dict[str, object]] | None:
    if len(candidates) != 1:
        return None
    if _active_artifact_id(account) is None:
        return candidates[0]
    return candidates[0]


def _planned_active_artifacts(actions: list[AccountReconcileAction]) -> dict[str, str]:
    planned: dict[str, str] = {}
    for action in actions:
        if action.kind != "would_activate_artifact":
            continue
        if action.account is None or action.artifact_id is None:
            continue
        planned[action.account] = action.artifact_id
    return planned


def _sync_account_for_home(known_home: _KnownHome) -> str | None:
    if known_home.system_managed or known_home.account is not None:
        return known_home.account
    return None


def _active_home_account(status: dict[str, object]) -> str | None:
    if _string_or_none(status.get("classification")) != "matching-active":
        return None
    auth = status.get("auth")
    matches = status.get("account_registry_matches")
    if not isinstance(auth, dict) or not isinstance(matches, list):
        return None
    artifact_id = _string_or_none(auth.get("artifact_id"))
    accounts = sorted(
        account
        for record in matches
        if isinstance(record, dict)
        and record.get("active_artifact_id") == artifact_id
        and (account := _string_or_none(record.get("account"))) is not None
    )
    if len(accounts) == 1:
        return accounts[0]
    return None


def _active_artifact_id(account: str) -> str | None:
    record = _account_record(account)
    if record is None:
        return None
    return _string_or_none(record.get("active_artifact_id"))


def _active_artifacts(account: str | None) -> tuple[dict[str, object], ...]:
    accounts = load_accounts(CLAUDE_PROVIDER).get("accounts")
    if not isinstance(accounts, dict):
        return ()
    payloads: list[dict[str, object]] = []
    for raw_account, record in sorted(accounts.items()):
        if not isinstance(raw_account, str) or not isinstance(record, dict):
            continue
        if record.get("auth_kind") != CLAUDE_AUTH_KIND:
            continue
        if account is not None and raw_account != account:
            continue
        payloads.append(
            {
                "account": raw_account,
                "active_artifact_id": record.get("active_artifact_id"),
                "account_uuid": record.get("account_uuid"),
                "email": record.get("email"),
            }
        )
    return tuple(payloads)


def _account_record(account: str) -> dict[str, object] | None:
    accounts = load_accounts(CLAUDE_PROVIDER).get("accounts")
    if not isinstance(accounts, dict):
        return None
    record = accounts.get(account)
    return record if isinstance(record, dict) else None


def _scanned_home_summary(
    known_home: _KnownHome,
    status: dict[str, object],
) -> dict[str, object]:
    payload = known_home.summary()
    payload.update(
        {
            "classification": status.get("classification"),
        }
    )
    auth = status.get("auth")
    if isinstance(auth, dict):
        payload["artifact_id"] = auth.get("artifact_id")
        identity = auth.get("identity")
        if isinstance(identity, dict):
            payload["account_uuid"] = identity.get("account_uuid")
            payload["email"] = identity.get("email")
        payload["storage_kind"] = auth.get("storage_kind")
    error = status.get("error")
    if isinstance(error, str):
        payload["error"] = error
    return payload


def _warning(
    kind: str,
    *,
    known_home: _KnownHome,
    message: str,
    status: dict[str, object],
) -> AccountReconcileWarning:
    return AccountReconcileWarning(
        kind=kind,
        home=str(known_home.home),
        account=known_home.account or _single_matching_account(status),
        message=message,
        detail={
            "classification": status.get("classification"),
            "error": status.get("error"),
        },
    )


def _artifact_id_from_status(status: dict[str, object]) -> str | None:
    auth = status.get("auth")
    if not isinstance(auth, dict):
        return None
    return _string_or_none(auth.get("artifact_id"))


def _normalize_optional_account(account: str | None) -> str | None:
    if account is None:
        return None
    return validate_string_for_path(account, field_name="account")


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


__all__ = [
    "discover_claude_reconcile_homes",
    "reconcile_claude_accounts",
]
