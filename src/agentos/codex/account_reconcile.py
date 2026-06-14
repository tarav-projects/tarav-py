from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

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
    read_artifacts,
    read_verifications,
    upsert_account,
)
from agentos.agent.config import load_agent_configs
from agentos.agent.run_runtime import AgentCommandConfig, AgentRunConfig
from agentos.codex.account_registry import (
    CODEX_AUTH_KIND,
    CODEX_PROVIDER,
    inspect_codex_account_home,
    link_codex_account_to_home,
    promote_verified_codex_auth_from_home,
    register_codex_account_from_auth_file,
)

_PING_NUMBER_PATTERN = re.compile(r"(?<![\d.])-?\d+(?![\d.])")


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
    sync_homes: bool = True,
    ping: bool = False,
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
        sync_homes=sync_homes,
        ping=ping,
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
                "ping": request.ping,
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
        sync_homes=False,
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
            for known_home, status in sorted(
                _dedupe_candidates_by_artifact_id(candidates),
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
                    continue
                payload = register_codex_account_from_auth_file(
                    auth_file=Path(str(status["auth_path"])),
                    account=matched_account,
                    register_only=True,
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
                            "activated": False,
                        },
                    )
                )

    actions.extend(
        _activate_verified_artifacts(
            request,
            fresh_by_account=fresh_by_account,
        )
    )

    if request.ping:
        actions.extend(
            _ping_verify_candidates(
                request,
                inspected=inspected,
                warnings=warnings,
            )
        )

    if request.sync_homes:
        inspected = tuple(_inspect_known_home(known_home) for known_home in known_homes)
        actions.extend(
            _sync_codex_homes(
                request,
                inspected,
                planned_active_artifacts=_planned_active_artifacts(actions),
                warnings=warnings,
            )
        )

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
    warnings: list[AccountReconcileWarning],
) -> list[AccountReconcileAction]:
    actions: list[AccountReconcileAction] = []
    warned_unverified: set[str] = set()
    for known_home, status in inspected:
        sync_account = _sync_account_for_home(known_home, status)
        if sync_account is None:
            continue
        if request.account is not None and sync_account != request.account:
            continue
        classification = _string_or_none(status.get("classification"))
        if classification == "matching-active" and _active_home_account(status) == sync_account:
            continue
        if not _may_sync_home(known_home, status):
            continue
        active_artifact_id = planned_active_artifacts.get(sync_account) or _active_artifact_id(sync_account)
        if active_artifact_id is None:
            continue
        if active_artifact_id not in _verified_artifacts_for_account(sync_account):
            if sync_account not in warned_unverified:
                warnings.append(
                    AccountReconcileWarning(
                        kind="active_artifact_unverified",
                        account=sync_account,
                        message=(
                            "codex active artifact has no verification evidence; "
                            "skipping automatic home sync"
                        ),
                        detail={"artifact_id": active_artifact_id},
                    )
                )
                warned_unverified.add(sync_account)
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
        payload = link_codex_account_to_home(
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
                    "auth_path": str(payload.get("auth_path")),
                },
            )
        )
    return actions


def _activate_verified_artifacts(
    request: AccountReconcileRequest,
    *,
    fresh_by_account: dict[str, list[tuple[_KnownHome, dict[str, object]]]],
) -> list[AccountReconcileAction]:
    actions: list[AccountReconcileAction] = []
    observed_artifacts = _observed_artifacts_by_account(fresh_by_account)
    for account, verification in _latest_verified_artifacts(request.account).items():
        artifact_id = _string_or_none(verification.get("artifact_id"))
        if artifact_id is None:
            continue
        if not _artifact_is_registered(account, artifact_id) and artifact_id not in observed_artifacts.get(account, set()):
            continue
        if _active_artifact_id(account) == artifact_id:
            continue
        if request.check:
            actions.append(
                AccountReconcileAction(
                    kind="would_activate_verified_artifact",
                    account=account,
                    artifact_id=artifact_id,
                    detail={
                        "verified_at": verification.get("verified_at"),
                        "source": verification.get("source"),
                    },
                )
            )
            continue
        upsert_account(
            CODEX_PROVIDER,
            account,
            {
                "auth_kind": CODEX_AUTH_KIND,
                "active_artifact_id": artifact_id,
                "artifact_file": f"artifacts/{artifact_id}.auth.json",
                "last_verified_at": verification.get("verified_at"),
                "last_verified_source": verification.get("source"),
            },
        )
        actions.append(
            AccountReconcileAction(
                kind="activated_verified_artifact",
                account=account,
                artifact_id=artifact_id,
                detail={
                    "verified_at": verification.get("verified_at"),
                    "source": verification.get("source"),
                },
            )
        )
    return actions


def _ping_verify_candidates(
    request: AccountReconcileRequest,
    *,
    inspected: tuple[tuple[_KnownHome, dict[str, object]], ...],
    warnings: list[AccountReconcileWarning],
) -> list[AccountReconcileAction]:
    actions: list[AccountReconcileAction] = []
    for account, candidates in _ping_candidates_by_account(request, inspected).items():
        for known_home, status in _dedupe_candidates_by_artifact_id(candidates):
            artifact_id = _artifact_id_from_status(status)
            if artifact_id is None:
                continue
            if request.check:
                actions.append(
                    AccountReconcileAction(
                        kind="would_ping",
                        account=account,
                        home=str(known_home.home),
                        artifact_id=artifact_id,
                    )
                )
                continue
            try:
                _run_reconcile_ping(
                    account=account,
                    home=known_home.home,
                    start_path=request.start_path,
                )
                payload = promote_verified_codex_auth_from_home(
                    home=known_home.home,
                    account=account,
                    source="accounts.reconcile.ping",
                    start_path=request.start_path,
                    sync_homes=False,
                    argv=request.argv,
                )
            except CliError as exc:
                warnings.append(
                    AccountReconcileWarning(
                        kind="ping_verification_failed",
                        account=account,
                        home=str(known_home.home),
                        message=str(exc),
                        detail={"artifact_id": artifact_id},
                    )
                )
                actions.append(
                    AccountReconcileAction(
                        kind="ping_failed",
                        account=account,
                        home=str(known_home.home),
                        artifact_id=artifact_id,
                    )
                )
                continue
            actions.append(
                AccountReconcileAction(
                    kind="verified_artifact",
                    account=account,
                    home=str(known_home.home),
                    artifact_id=str(payload.get("artifact_id") or artifact_id),
                    detail={
                        "source": "accounts.reconcile.ping",
                        "artifact_appended": bool(payload.get("artifact_appended")),
                    },
                )
            )
    return actions


def _known_codex_homes(request: AccountReconcileRequest) -> tuple[_KnownHome, ...]:
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
            raise CliError(f"codex reconcile --home is not a known home: {request.home}")
        return (homes[normalized],)
    return tuple(homes[key] for key in sorted(homes))


def _configured_homes(start_path: Path | str) -> tuple[_KnownHome, ...]:
    homes: list[_KnownHome] = []
    for config in load_agent_configs(start_path=start_path):
        if config.provider != CODEX_PROVIDER:
            continue
        for home in config.homes:
            homes.append(
                _KnownHome(
                    home=home.expanduser().resolve(),
                    source="configured",
                    account=config.account.account if config.account is not None else None,
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


def _ping_candidates_by_account(
    request: AccountReconcileRequest,
    inspected: tuple[tuple[_KnownHome, dict[str, object]], ...],
) -> dict[str, list[tuple[_KnownHome, dict[str, object]]]]:
    candidates: dict[str, list[tuple[_KnownHome, dict[str, object]]]] = {}
    for known_home, status in inspected:
        artifact_id = _artifact_id_from_status(status)
        if artifact_id is None:
            continue
        account = known_home.account or _single_matching_account(status) or _active_home_account(status)
        if account is None:
            continue
        if request.account is not None and account != request.account:
            continue
        candidates.setdefault(account, []).append((known_home, status))
    return candidates


def _run_reconcile_ping(
    *,
    account: str,
    home: Path,
    start_path: Path | str,
) -> None:
    agent = _build_registered_account_agent(
        provider=CODEX_PROVIDER,
        account=account,
        home=home,
        start_path=start_path,
    )
    if not agent.ping.enabled:
        raise CliError(
            f"agent {agent.profile_id or '<default>'} for provider {agent.provider} has ping disabled"
        )
    result = agent.run(
        AgentCommandConfig(
            prompt=agent.ping.prompt,
            argv=agent.ping.argv,
            model=agent.ping.model,
            account=None,
            interaction_mode="non_interactive",
            credential_success_source=None,
        ),
        AgentRunConfig(cwd=Path.cwd().resolve(), process_mode="capture"),
    )
    _validate_reconcile_ping_result(result, expected_number=agent.ping.expected_number)


def _build_registered_account_agent(**kwargs):
    from agentos.agent.providers import build_registered_account_agent

    return build_registered_account_agent(**kwargs)


def _validate_reconcile_ping_result(result, *, expected_number: int | None) -> None:
    output = "\n".join(part for part in (result.stdout, result.stderr) if part)
    if result.exit_code != 0:
        detail = output.strip()
        suffix = f": {detail}" if detail else ""
        raise CliError(
            f"agent ping failed: provider command exited with {result.exit_code}{suffix}"
        )
    if expected_number is None:
        return
    numbers = [int(match.group(0)) for match in _PING_NUMBER_PATTERN.finditer(output)]
    if expected_number not in numbers:
        raise CliError(
            f"agent ping failed: expected numeric answer {expected_number} "
            "was not present in provider output"
        )


def _planned_active_artifacts(actions: list[AccountReconcileAction]) -> dict[str, str]:
    planned: dict[str, str] = {}
    for action in actions:
        if action.kind not in {"would_activate_verified_artifact", "activated_verified_artifact", "verified_artifact"}:
            continue
        if action.account is None or action.artifact_id is None:
            continue
        planned[action.account] = action.artifact_id
    return planned


def _observed_artifacts_by_account(
    fresh_by_account: dict[str, list[tuple[_KnownHome, dict[str, object]]]],
) -> dict[str, set[str]]:
    observed: dict[str, set[str]] = {}
    for account, candidates in fresh_by_account.items():
        artifact_ids = {
            artifact_id
            for _, status in candidates
            if (artifact_id := _artifact_id_from_status(status)) is not None
        }
        if artifact_ids:
            observed[account] = artifact_ids
    return observed


def _latest_verified_artifacts(account: str | None) -> dict[str, dict[str, object]]:
    latest: dict[str, dict[str, object]] = {}
    for record in read_verifications(CODEX_PROVIDER):
        if record.get("auth_kind") != CODEX_AUTH_KIND:
            continue
        record_account = _string_or_none(record.get("account"))
        if record_account is None:
            continue
        if account is not None and record_account != account:
            continue
        existing = latest.get(record_account)
        if existing is None or str(record.get("verified_at", "")) >= str(existing.get("verified_at", "")):
            latest[record_account] = record
    return latest


def _verified_artifacts_for_account(account: str) -> set[str]:
    return {
        artifact_id
        for record in read_verifications(CODEX_PROVIDER)
        if record.get("auth_kind") == CODEX_AUTH_KIND
        and record.get("account") == account
        and (artifact_id := _string_or_none(record.get("artifact_id"))) is not None
    }


def _artifact_is_registered(account: str, artifact_id: str) -> bool:
    return any(
        entry.get("account") == account
        and entry.get("artifact_id") == artifact_id
        and entry.get("auth_kind") in {None, CODEX_AUTH_KIND}
        for entry in read_artifacts(CODEX_PROVIDER)
    )


def _sync_account_for_home(known_home: _KnownHome, status: dict[str, object]) -> str | None:
    if known_home.system_managed or known_home.account is not None:
        return known_home.account
    return None


def _may_sync_home(known_home: _KnownHome, status: dict[str, object]) -> bool:
    if known_home.system_managed or known_home.account is not None:
        return True
    return False


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
    accounts = load_accounts(CODEX_PROVIDER).get("accounts")
    if not isinstance(accounts, dict):
        return ()
    payloads: list[dict[str, object]] = []
    for raw_account, record in sorted(accounts.items()):
        if not isinstance(raw_account, str) or not isinstance(record, dict):
            continue
        if account is not None and raw_account != account:
            continue
        verified_artifacts = _verified_artifacts_for_account(raw_account)
        payloads.append(
            {
                "account": raw_account,
                "active_artifact_id": record.get("active_artifact_id"),
                "active_verified": record.get("active_artifact_id") in verified_artifacts,
                "last_verified_at": record.get("last_verified_at"),
                "last_verified_source": record.get("last_verified_source"),
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
