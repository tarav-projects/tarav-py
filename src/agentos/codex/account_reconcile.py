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
    load_links,
    record_account_event,
)
from agentos.agent.config import load_agent_configs
from agentos.codex.account_registry import (
    CODEX_PROVIDER,
    inspect_codex_account_home,
    link_codex_account_to_home,
    register_codex_account_from_auth_file,
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


def reconcile_codex_accounts(
    *,
    account: str | None = None,
    home: Path | None = None,
    start_path: Path | str = ".",
    register_discovered: bool = True,
    sync_stale_links: bool = True,
    check: bool = False,
    record_event: bool = True,
    argv: list[str] | tuple[str, ...] = (),
) -> dict[str, object]:
    request = AccountReconcileRequest(
        provider=CODEX_PROVIDER,
        account=_normalize_optional_account(account),
        home=home.expanduser().resolve() if home is not None else None,
        start_path=start_path,
        register_discovered=register_discovered,
        sync_stale_links=sync_stale_links,
        check=check,
        argv=tuple(argv),
    )
    result = _reconcile_codex_accounts(request)
    payload = result.summary()
    if record_event and not check:
        record_account_event(
            event_type="agent.accounts.reconcile",
            command="agent accounts reconcile",
            argv=argv,
            status="ok",
            payload={
                "provider": CODEX_PROVIDER,
                "account": request.account,
                "home": str(request.home) if request.home is not None else None,
                "scanned_count": len(result.scanned_homes),
                "action_count": len(result.actions),
                "warning_count": len(result.warnings),
            },
        )
    return payload


def discover_codex_reconcile_homes(
    *,
    account: str | None = None,
    home: Path | None = None,
    start_path: Path | str = ".",
) -> tuple[dict[str, object], ...]:
    request = AccountReconcileRequest(
        provider=CODEX_PROVIDER,
        account=_normalize_optional_account(account),
        home=home.expanduser().resolve() if home is not None else None,
        start_path=start_path,
        register_discovered=False,
        sync_stale_links=False,
        check=True,
    )
    return tuple(known_home.summary() for known_home in _known_codex_homes(request))


def _reconcile_codex_accounts(request: AccountReconcileRequest) -> AccountReconcileResult:
    known_homes = _known_codex_homes(request)
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
                        message="codex auth matched no unique registered account alias",
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
                    message="codex auth belongs to an unregistered account; no mutation performed",
                    status=status,
                )
            )
        elif classification == "broken":
            warnings.append(
                _warning(
                    "broken_auth",
                    known_home=known_home,
                    message="codex auth could not be read; no mutation performed",
                    status=status,
                )
            )

    if request.register_discovered:
        for matched_account, candidates in sorted(fresh_by_account.items()):
            selected = _select_activation_candidate(matched_account, candidates)
            if len(candidates) > 1:
                warnings.append(
                    AccountReconcileWarning(
                        kind="multiple_fresh_artifacts",
                        account=matched_account,
                        message="multiple fresh codex auth artifacts were observed; selected newest metadata",
                        detail={
                            "artifact_ids": [
                                _artifact_id_from_status(status)
                                for _, status in candidates
                                if _artifact_id_from_status(status) is not None
                            ],
                            "selected_artifact_id": _artifact_id_from_status(selected[1])
                            if selected is not None
                            else _active_artifact_id(matched_account),
                        },
                    )
                )
            for known_home, status in sorted(
                candidates,
                key=lambda item: str(item[0].home),
            ):
                artifact_id = _artifact_id_from_status(status)
                if request.check:
                    actions.append(
                        AccountReconcileAction(
                            kind="would_register_artifact",
                            account=matched_account,
                            home=str(known_home.home),
                            artifact_id=artifact_id,
                        )
                    )
                    if selected is not None and (known_home, status) == selected:
                        actions.append(
                            AccountReconcileAction(
                                kind="would_activate_artifact",
                                account=matched_account,
                                artifact_id=artifact_id,
                            )
                        )
                    continue
                payload = register_codex_account_from_auth_file(
                    auth_file=Path(str(status["auth_path"])),
                    account=matched_account,
                    register_only=selected is None or (known_home, status) != selected,
                    argv=request.argv,
                )
                actions.append(
                    AccountReconcileAction(
                        kind="registered_artifact",
                        account=matched_account,
                        home=str(known_home.home),
                        artifact_id=artifact_id,
                        detail={
                            "artifact_appended": bool(payload.get("artifact_appended")),
                            "activated": selected is not None
                            and (known_home, status) == selected,
                        },
                    )
                )

    if request.sync_stale_links:
        inspected = tuple(_inspect_known_home(known_home) for known_home in known_homes)
        actions.extend(_sync_codex_homes(request, inspected, planned_active_artifacts=_planned_active_artifacts(actions)))

    return AccountReconcileResult(
        provider=CODEX_PROVIDER,
        scanned_homes=tuple(_scanned_home_summary(known_home, status) for known_home, status in inspected),
        actions=tuple(actions),
        warnings=tuple(warnings),
        active_artifacts=_active_artifacts(request.account),
        check=request.check,
    )


def _sync_codex_homes(
    request: AccountReconcileRequest,
    inspected: tuple[tuple[_KnownHome, dict[str, object]], ...],
    *,
    planned_active_artifacts: dict[str, str],
) -> list[AccountReconcileAction]:
    actions: list[AccountReconcileAction] = []
    for known_home, status in inspected:
        sync_account = _sync_account_for_home(known_home, status)
        if sync_account is None:
            continue
        if request.account is not None and sync_account != request.account:
            continue
        link_state = _string_or_none(status.get("link_consistency"))
        classification = _string_or_none(status.get("classification"))
        if link_state == "verified" and classification == "matching-active":
            continue
        if not _may_sync_home(known_home, status):
            continue
        active_artifact_id = planned_active_artifacts.get(sync_account) or _active_artifact_id(sync_account)
        if active_artifact_id is None:
            continue
        if request.check:
            actions.append(
                AccountReconcileAction(
                    kind="would_sync_linked_home",
                    account=sync_account,
                    home=str(known_home.home),
                    artifact_id=active_artifact_id,
                )
            )
            continue
        payload = link_codex_account_to_home(
            home=known_home.home,
            account=sync_account,
            argv=request.argv,
        )
        actions.append(
            AccountReconcileAction(
                kind="synced_linked_home",
                account=sync_account,
                home=str(known_home.home),
                artifact_id=active_artifact_id,
                detail={
                    "auth_path": str(payload.get("auth_path")),
                    "previous_link": payload.get("previous_link"),
                },
            )
        )
    return actions


def _known_codex_homes(request: AccountReconcileRequest) -> tuple[_KnownHome, ...]:
    homes: dict[str, _KnownHome] = {}
    for home in _linked_homes(request.account):
        _add_known_home(homes, home)
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
            raise CliError(f"codex reconcile --home is not a known home: {request.home}")
        return (homes[normalized],)
    return tuple(homes[key] for key in sorted(homes))


def _linked_homes(account: str | None) -> tuple[_KnownHome, ...]:
    links = load_links(CODEX_PROVIDER).get("links")
    if not isinstance(links, dict):
        return ()
    homes: list[_KnownHome] = []
    for raw_home, link in links.items():
        if not isinstance(raw_home, str) or not isinstance(link, dict):
            continue
        linked_account = _string_or_none(link.get("account"))
        if account is not None and linked_account != account:
            continue
        homes.append(
            _KnownHome(
                home=Path(raw_home).expanduser().resolve(),
                source="link",
                account=linked_account,
            )
        )
    return tuple(homes)


def _configured_homes(start_path: Path | str) -> tuple[_KnownHome, ...]:
    homes: list[_KnownHome] = []
    for config in load_agent_configs(start_path=start_path):
        if config.provider != CODEX_PROVIDER or config.home is None:
            continue
        homes.append(
            _KnownHome(
                home=config.home.expanduser().resolve(),
                source="configured",
            )
        )
    return tuple(homes)


def _registered_accounts(account: str | None) -> tuple[str, ...]:
    accounts = load_accounts(CODEX_PROVIDER).get("accounts")
    if not isinstance(accounts, dict):
        return ()
    names = [
        raw_account
        for raw_account in accounts
        if isinstance(raw_account, str)
        and (account is None or raw_account == account)
    ]
    return tuple(sorted(names))


def _system_home(account: str) -> Path:
    return agentos_home_dir() / "agent" / "homes" / CODEX_PROVIDER / account


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
        source=",".join(sorted(set(existing.source.split(",") + candidate.source.split(",")))),
        account=existing.account or candidate.account,
        system_managed=existing.system_managed or candidate.system_managed,
    )


def _inspect_known_home(known_home: _KnownHome) -> tuple[_KnownHome, dict[str, object]]:
    return known_home, inspect_codex_account_home(home=known_home.home)


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


def _select_activation_candidate(
    account: str,
    candidates: list[tuple[_KnownHome, dict[str, object]]],
) -> tuple[_KnownHome, dict[str, object]] | None:
    selected = max(
        candidates,
        key=lambda item: (
            _last_refresh_from_status(item[1]) or "",
            _jwt_iat_from_status(item[1]) or -1,
            _mtime_from_status(item[1]) or -1.0,
            str(item[0].home),
        ),
    )
    current_key = _active_refresh_key(account)
    selected_key = (
        _last_refresh_from_status(selected[1]) or "",
        _jwt_iat_from_status(selected[1]) or -1,
    )
    if _active_artifact_id(account) is None or selected_key > current_key:
        return selected
    return None


def _planned_active_artifacts(actions: list[AccountReconcileAction]) -> dict[str, str]:
    planned: dict[str, str] = {}
    for action in actions:
        if action.kind != "would_activate_artifact":
            continue
        if action.account is None or action.artifact_id is None:
            continue
        planned[action.account] = action.artifact_id
    return planned


def _active_refresh_key(account: str) -> tuple[str, int]:
    record = _account_record(account)
    if record is None:
        return "", -1
    last_refresh = _string_or_none(record.get("last_refresh")) or ""
    jwt_iat = record.get("jwt_iat")
    return last_refresh, jwt_iat if isinstance(jwt_iat, int) else -1


def _sync_account_for_home(known_home: _KnownHome, status: dict[str, object]) -> str | None:
    link = status.get("link")
    if isinstance(link, dict):
        linked_account = _string_or_none(link.get("account"))
        if linked_account is not None:
            return linked_account
    if known_home.system_managed:
        return known_home.account
    return None


def _may_sync_home(known_home: _KnownHome, status: dict[str, object]) -> bool:
    if known_home.system_managed:
        return True
    link = status.get("link")
    if not isinstance(link, dict) or link.get("kind") != "artifact":
        return False
    return _string_or_none(status.get("link_consistency")) in {"missing", "stale"}


def _active_artifact_id(account: str) -> str | None:
    record = _account_record(account)
    if record is None:
        return None
    return _string_or_none(record.get("active_artifact_id"))


def _active_artifacts(account: str | None) -> tuple[dict[str, object], ...]:
    accounts = load_accounts(CODEX_PROVIDER).get("accounts")
    if not isinstance(accounts, dict):
        return ()
    payloads: list[dict[str, object]] = []
    for raw_account, record in sorted(accounts.items()):
        if not isinstance(raw_account, str) or not isinstance(record, dict):
            continue
        if account is not None and raw_account != account:
            continue
        payloads.append(
            {
                "account": raw_account,
                "active_artifact_id": record.get("active_artifact_id"),
                "account_id": record.get("account_id"),
                "email": record.get("email"),
            }
        )
    return tuple(payloads)


def _account_record(account: str) -> dict[str, object] | None:
    accounts = load_accounts(CODEX_PROVIDER).get("accounts")
    if not isinstance(accounts, dict):
        return None
    record = accounts.get(account)
    return record if isinstance(record, dict) else None


def _scanned_home_summary(known_home: _KnownHome, status: dict[str, object]) -> dict[str, object]:
    payload = known_home.summary()
    payload.update(
        {
            "classification": status.get("classification"),
            "link_consistency": status.get("link_consistency"),
            "auth_path": status.get("auth_path"),
        }
    )
    auth = status.get("auth")
    if isinstance(auth, dict):
        payload["artifact_id"] = auth.get("artifact_id")
        payload["account_id"] = auth.get("account_id")
        if isinstance(auth.get("email"), str):
            payload["email"] = auth.get("email")
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
            "link_consistency": status.get("link_consistency"),
            "auth_path": status.get("auth_path"),
            "error": status.get("error"),
        },
    )


def _artifact_id_from_status(status: dict[str, object]) -> str | None:
    auth = status.get("auth")
    if not isinstance(auth, dict):
        return None
    return _string_or_none(auth.get("artifact_id"))


def _last_refresh_from_status(status: dict[str, object]) -> str | None:
    auth = status.get("auth")
    if not isinstance(auth, dict):
        return None
    return _string_or_none(auth.get("last_refresh"))


def _jwt_iat_from_status(status: dict[str, object]) -> int | None:
    auth = status.get("auth")
    if not isinstance(auth, dict):
        return None
    value = auth.get("jwt_iat")
    return value if isinstance(value, int) else None


def _mtime_from_status(status: dict[str, object]) -> float | None:
    auth = status.get("auth")
    if not isinstance(auth, dict):
        return None
    value = auth.get("mtime")
    if isinstance(value, int | float):
        return float(value)
    return None


def _normalize_optional_account(account: str | None) -> str | None:
    if account is None:
        return None
    return validate_string_for_path(account, field_name="account")


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


__all__ = [
    "discover_codex_reconcile_homes",
    "reconcile_codex_accounts",
]
