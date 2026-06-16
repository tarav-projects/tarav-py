from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
from dataclasses import dataclass, replace
from pathlib import Path

from agentos._core.errors import CliError
from agentos._core.path_validation import validate_string_for_path
from agentos.agent.account_registry import (
    account_provider_root,
    append_artifact,
    append_verification,
    artifacts_dir,
    load_account,
    load_accounts,
    record_account_event,
    read_artifacts,
    upsert_account,
)

CODEX_AUTH_FILENAME = "auth.json"
CODEX_PROVIDER = "codex"
CODEX_AUTH_KIND = "auth-json"


@dataclass(frozen=True)
class CodexAuthInfo:
    path: Path
    sha256: str
    auth_mode: str | None
    account_id: str
    email: str | None
    last_refresh: str | None
    jwt_iat: int | None
    mtime: float

    def metadata_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {}
        if self.auth_mode is not None:
            payload["auth_mode"] = self.auth_mode
        if self.email is not None:
            payload["email"] = self.email
        if self.last_refresh is not None:
            payload["last_refresh"] = self.last_refresh
        if self.jwt_iat is not None:
            payload["jwt_iat"] = self.jwt_iat
        return payload

    def safe_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "path": str(self.path),
            "sha256": self.sha256,
            "artifact_id": self.sha256,
            "account_id": self.account_id,
            "mtime": self.mtime,
        }
        payload.update(self.metadata_payload())
        return payload


def register_codex_account_from_auth_file(
    *,
    auth_file: Path,
    account: str,
    email: str | None = None,
    register_only: bool = False,
    argv: list[str] | tuple[str, ...] = (),
) -> dict[str, object]:
    normalized_account = validate_string_for_path(account, field_name="account")
    info = _apply_manual_metadata(read_codex_auth_info(auth_file.expanduser()), email=email)
    existing = _load_account_or_none(normalized_account)
    _validate_account_identity(existing, account=normalized_account, info=info)
    stored_file = _store_artifact(info)
    artifact_entry, artifact_appended = _append_artifact_entry(
        account=normalized_account,
        info=info,
        source_auth_file=info.path,
    )
    account_record = _write_account(
        account=normalized_account,
        info=info,
        activate=not register_only,
        existing=existing,
    )
    result = {
        "status": "ok",
        "command": "agent accounts register",
        "provider": CODEX_PROVIDER,
        "account": normalized_account,
        "auth_file": str(info.path),
        "auth": info.safe_payload(),
        "provider_root": str(_provider_root()),
        "stored_file": str(stored_file),
        "artifact_entry": artifact_entry,
        "artifact_appended": artifact_appended,
        "register_only": register_only,
        "account_record": account_record,
    }
    record_account_event(
        event_type="agent.accounts.register",
        command="agent accounts register",
        argv=argv,
        status="ok",
        payload={
            "provider": CODEX_PROVIDER,
            "account": normalized_account,
            "account_id": info.account_id,
            "email": info.email,
            "auth_file": str(info.path),
            "artifact_id": info.sha256,
            "stored_file": _artifact_relative_file(info.sha256),
            "artifact_appended": artifact_appended,
            "register_only": register_only,
            "active_updated": not register_only,
        },
    )
    return result


def promote_verified_codex_auth_from_home(
    *,
    home: Path,
    account: str,
    source: str,
    start_path: Path | str = ".",
    sync_homes: bool = True,
    argv: list[str] | tuple[str, ...] = (),
) -> dict[str, object]:
    normalized_home = home.expanduser().resolve()
    normalized_account = validate_string_for_path(account, field_name="account")
    normalized_source = validate_string_for_path(source, field_name="source")
    registration = register_codex_account_from_auth_file(
        auth_file=_home_auth_path(normalized_home),
        account=normalized_account,
        register_only=True,
        argv=argv,
    )
    auth = registration.get("auth")
    if not isinstance(auth, dict):
        raise CliError("codex auth registration did not return auth metadata")
    artifact_id = _require_payload_string(auth, "artifact_id")
    verification = append_verification(
        CODEX_PROVIDER,
        {
            "account": normalized_account,
            "artifact_id": artifact_id,
            "auth_kind": CODEX_AUTH_KIND,
            "home": str(normalized_home),
            "source": normalized_source,
        },
    )
    info = read_codex_auth_info(_home_auth_path(normalized_home))
    account_record = upsert_account(
        CODEX_PROVIDER,
        normalized_account,
        {
            "auth_kind": CODEX_AUTH_KIND,
            "account_id": info.account_id,
            "email": info.email,
            **info.metadata_payload(),
            "active_artifact_id": artifact_id,
            "artifact_file": _artifact_relative_file(artifact_id),
            "last_verified_at": verification["verified_at"],
            "last_verified_source": normalized_source,
        },
    )
    synced_homes: list[dict[str, object]] = []
    sync_warnings: list[dict[str, object]] = []
    if sync_homes:
        synced_homes, sync_warnings = _sync_known_homes_from_verified_artifact(
            account=normalized_account,
            source_home=normalized_home,
            start_path=start_path,
            argv=argv,
        )
    record_account_event(
        event_type="agent.accounts.verify",
        command=normalized_source,
        argv=argv,
        status="ok",
        payload={
            "provider": CODEX_PROVIDER,
            "account": normalized_account,
            "auth_kind": CODEX_AUTH_KIND,
            "home": str(normalized_home),
            "artifact_id": artifact_id,
            "source": normalized_source,
            "verified_at": verification["verified_at"],
            "artifact_appended": bool(registration.get("artifact_appended")),
            "synced_count": len(synced_homes),
            "sync_warning_count": len(sync_warnings),
        },
    )
    return {
        "status": "ok",
        "provider": CODEX_PROVIDER,
        "account": normalized_account,
        "home": str(normalized_home),
        "artifact_id": artifact_id,
        "artifact_appended": bool(registration.get("artifact_appended")),
        "verification": verification,
        "account_record": account_record,
        "synced_homes": synced_homes,
        "sync_warnings": sync_warnings,
    }


def materialize_codex_account_to_home(
    *,
    home: Path,
    account: str,
    force: bool = False,
    check: bool = False,
    record_event: bool = True,
    argv: list[str] | tuple[str, ...] = (),
) -> dict[str, object]:
    normalized_home = home.expanduser().resolve()
    normalized_account = validate_string_for_path(account, field_name="account")
    auth_path = _home_auth_path(normalized_home)
    account_record = load_account(CODEX_PROVIDER, normalized_account)
    active_artifact_id = _require_account_string(account_record, "active_artifact_id")
    account_id = _require_account_string(account_record, "account_id")
    source_auth = _artifact_path(active_artifact_id)
    if not source_auth.is_file():
        raise CliError(f"codex account active artifact file does not exist: {source_auth}")

    try:
        target_state = _inspect_target_before_materialization(
            auth_path,
            requested_account=normalized_account,
            force=force,
            argv=argv,
        )
        base_payload = {
            "status": "ok",
            "command": "agent accounts materialize",
            "provider": CODEX_PROVIDER,
            "account": normalized_account,
            "account_id": account_id,
            "home": str(normalized_home),
            "auth_path": str(auth_path),
            "kind": "artifact",
            "force": force,
            "check": check,
            "artifact_id": active_artifact_id,
            "source_auth_file": str(source_auth),
            "target_before_materialization": target_state,
        }
        if check:
            return base_payload

        _copy_auth_to_home(source_auth, auth_path)
        copied_info = read_codex_auth_info(auth_path)
        payload = {
            **base_payload,
            "copied_auth": copied_info.safe_payload(),
            "copied_artifact_id": copied_info.sha256,
        }
        if record_event:
            record_account_event(
                event_type="account.auth.materialized",
                command="agent accounts materialize",
                argv=argv,
                status="ok",
                payload=payload,
            )
        return payload
    except CliError as exc:
        if record_event:
            _record_materialize_failure(
                argv=argv,
                account=normalized_account,
                home=normalized_home,
                auth_path=auth_path,
                message=str(exc),
                payload={"force": force, "check": check},
            )
        raise


def inspect_codex_account_home(*, home: Path) -> dict[str, object]:
    normalized_home = home.expanduser().resolve()
    auth_path = _home_auth_path(normalized_home)
    base: dict[str, object] = {
        "status": "ok",
        "command": "agent accounts status",
        "provider": CODEX_PROVIDER,
        "home": str(normalized_home),
        "auth_path": str(auth_path),
        "path_kind": _path_kind(auth_path),
    }
    if not auth_path.exists() and not auth_path.is_symlink():
        base["classification"] = "missing"
        return base

    try:
        info = read_codex_auth_info(auth_path)
    except CliError as exc:
        base["classification"] = "broken"
        base["error"] = str(exc)
        return base

    hash_matches = _artifact_matches(artifact_id=info.sha256)
    account_matches = _accounts_for_account_id(info.account_id)
    active_matches = [
        account_record
        for account_record in account_matches
        if account_record.get("active_artifact_id") == info.sha256
    ]
    base["auth"] = info.safe_payload()
    base["artifact_registry_matches"] = hash_matches
    base["account_registry_matches"] = account_matches
    if active_matches:
        base["classification"] = "matching-active"
    elif hash_matches:
        base["classification"] = "registered"
    elif account_matches:
        base["classification"] = "known-account-new-hash"
    else:
        base["classification"] = "unknown"
    return base


def read_codex_auth_info(path: Path) -> CodexAuthInfo:
    if not path.exists():
        raise CliError(f"codex auth file does not exist: {path}")
    if not path.is_file():
        raise CliError(f"codex auth path is not a file: {path}")
    raw = path.read_bytes()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CliError(f"invalid codex auth JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise CliError(f"codex auth JSON must be an object: {path}")
    tokens = payload.get("tokens")
    if not isinstance(tokens, dict):
        raise CliError(f"codex auth tokens must be an object: {path}")
    account_id = _string_or_none(tokens.get("account_id"))
    if account_id is None:
        raise CliError(f"codex auth tokens.account_id is required: {path}")
    claims = _jwt_claims(tokens)
    return CodexAuthInfo(
        path=path.expanduser().resolve(),
        sha256=hashlib.sha256(raw).hexdigest(),
        auth_mode=_string_or_none(payload.get("auth_mode")),
        account_id=account_id,
        email=_claim_string(claims, "email"),
        last_refresh=_string_or_none(payload.get("last_refresh")),
        jwt_iat=_claim_int(claims, "iat"),
        mtime=path.stat().st_mtime,
    )


def _inspect_target_before_materialization(
    auth_path: Path,
    *,
    requested_account: str,
    force: bool,
    argv: list[str] | tuple[str, ...],
) -> dict[str, object] | None:
    if not auth_path.exists() and not auth_path.is_symlink():
        return None
    try:
        info = read_codex_auth_info(auth_path)
    except CliError:
        if force:
            return {"classification": "broken", "action": "overwritten-by-force"}
        raise

    account = _single_account_for_account_id(info.account_id)
    if account is None:
        if force:
            return {
                "classification": "unknown",
                "action": "overwritten-by-force",
                "auth": info.safe_payload(),
            }
        raise CliError(
            "refusing to replace unregistered codex auth: "
            f"{info.path} belongs to account_id {info.account_id}, which is not in the registry. "
            "Register it first with: "
            f"agentos agent accounts register --provider codex --account <alias> --auth-file {info.path}"
        )

    artifact_known = bool(_artifact_matches(artifact_id=info.sha256))
    if not artifact_known:
        register_codex_account_from_auth_file(auth_file=auth_path, account=account, argv=argv)
    classification = "requested-account" if account == requested_account else "known-different-account"
    return {
        "classification": classification,
        "action": "registered" if not artifact_known else "already-registered",
        "account": account,
        "auth": info.safe_payload(),
    }


def _write_account(
    *,
    account: str,
    info: CodexAuthInfo,
    activate: bool,
    existing: dict[str, object] | None,
) -> dict[str, object]:
    updates: dict[str, object] = {
        "auth_kind": CODEX_AUTH_KIND,
        "account_id": info.account_id,
        "email": info.email,
        **info.metadata_payload(),
    }
    if activate:
        updates["active_artifact_id"] = info.sha256
        updates["artifact_file"] = _artifact_relative_file(info.sha256)
    elif existing is None:
        updates["active_artifact_id"] = None
    return upsert_account(
        CODEX_PROVIDER,
        account,
        updates,
    )


def _append_artifact_entry(
    *,
    account: str,
    info: CodexAuthInfo,
    source_auth_file: Path,
) -> tuple[dict[str, object], bool]:
    entry: dict[str, object] = {
        "account": account,
        "artifact_id": info.sha256,
        "auth_kind": CODEX_AUTH_KIND,
        "account_id": info.account_id,
        "file": _artifact_relative_file(info.sha256),
        "source_auth_file": str(source_auth_file),
    }
    entry.update(info.metadata_payload())
    return append_artifact(CODEX_PROVIDER, entry)


def _store_artifact(info: CodexAuthInfo) -> Path:
    destination = _artifact_path(info.sha256)
    if destination.exists():
        return destination
    _copy_file_atomic(info.path, destination)
    return destination


def _copy_auth_to_home(source_auth: Path, auth_path: Path) -> Path:
    _copy_file_atomic(source_auth, auth_path)
    return auth_path


def _copy_file_atomic(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path = destination.parent / f".{destination.name}.agentos-tmp-{os.getpid()}"
    if temp_path.exists() or temp_path.is_symlink():
        temp_path.unlink()
    try:
        shutil.copy2(source, temp_path)
        os.replace(temp_path, destination)
    finally:
        if temp_path.exists() or temp_path.is_symlink():
            temp_path.unlink()


def _validate_account_identity(
    existing: dict[str, object] | None,
    *,
    account: str,
    info: CodexAuthInfo,
) -> None:
    if existing is None:
        return
    existing_account_id = _string_or_none(existing.get("account_id"))
    if existing_account_id is not None and existing_account_id != info.account_id:
        raise CliError(
            f"codex account alias {account} is already registered for account_id "
            f"{existing_account_id}; refusing auth for {info.account_id}"
        )


def _load_account_or_none(account: str) -> dict[str, object] | None:
    try:
        return load_account(CODEX_PROVIDER, account)
    except CliError as exc:
        if str(exc) == f"agent account is not registered: {CODEX_PROVIDER}.{account}":
            return None
        raise


def _artifact_matches(*, artifact_id: str) -> list[dict[str, object]]:
    return [entry for entry in read_artifacts(CODEX_PROVIDER) if entry.get("artifact_id") == artifact_id]


def _accounts_for_account_id(account_id: str) -> list[dict[str, object]]:
    registry = load_accounts(CODEX_PROVIDER)
    accounts = registry.get("accounts")
    if not isinstance(accounts, dict):
        return []
    matches = [
        record
        for record in accounts.values()
        if isinstance(record, dict) and record.get("account_id") == account_id
    ]
    return sorted(matches, key=lambda record: str(record.get("account", "")))


def _single_account_for_account_id(account_id: str) -> str | None:
    matches = _accounts_for_account_id(account_id)
    accounts = sorted(
        {
            account
            for record in matches
            if (account := _string_or_none(record.get("account"))) is not None
        }
    )
    if not accounts:
        return None
    if len(accounts) > 1:
        raise CliError(
            "refusing to replace codex auth with ambiguous registered account aliases: "
            f"account_id {account_id} is registered as {', '.join(accounts)}"
        )
    return accounts[0]


def _path_kind(path: Path) -> str:
    if path.is_symlink():
        return "symlink"
    if path.is_file():
        return "file"
    if path.exists():
        return "other"
    return "missing"


def _apply_manual_metadata(info: CodexAuthInfo, *, email: str | None) -> CodexAuthInfo:
    normalized_email = _string_or_none(email)
    if normalized_email is None:
        return info
    return replace(info, email=normalized_email)


def _record_materialize_failure(
    *,
    argv: list[str] | tuple[str, ...],
    account: str,
    home: Path,
    auth_path: Path,
    message: str,
    payload: dict[str, object],
) -> None:
    record_account_event(
        event_type="account.auth.materialized",
        command="agent accounts materialize",
        argv=argv,
        status="error",
        payload={
            "provider": CODEX_PROVIDER,
            "account": account,
            "home": str(home),
            "auth_path": str(auth_path),
            "message": message,
            **payload,
        },
    )


def _provider_root() -> Path:
    return account_provider_root(CODEX_PROVIDER)


def _artifact_path(artifact_id: str) -> Path:
    return artifacts_dir(CODEX_PROVIDER) / f"{artifact_id}.auth.json"


def _artifact_relative_file(artifact_id: str) -> str:
    return f"artifacts/{artifact_id}.auth.json"


def _home_auth_path(home: Path) -> Path:
    return home / CODEX_AUTH_FILENAME


def _require_account_string(account: dict[str, object], field: str) -> str:
    value = account.get(field)
    if not isinstance(value, str) or not value.strip():
        raise CliError(f"codex account field {field} must be a non-empty string")
    return value.strip()


def _require_payload_string(payload: dict[str, object], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise CliError(f"codex payload field {field} must be a non-empty string")
    return value.strip()


def _sync_known_homes_from_verified_artifact(
    *,
    account: str,
    source_home: Path,
    start_path: Path | str,
    argv: list[str] | tuple[str, ...],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    from agentos.codex.account_reconcile import discover_codex_reconcile_homes

    synced_homes: list[dict[str, object]] = []
    warnings: list[dict[str, object]] = []
    for home_summary in discover_codex_reconcile_homes(
        account=account,
        start_path=start_path,
    ):
        raw_home = home_summary.get("home")
        if not isinstance(raw_home, str):
            continue
        target_home = Path(raw_home).expanduser().resolve()
        if target_home == source_home:
            continue
        try:
            payload = materialize_codex_account_to_home(
                home=target_home,
                account=account,
                record_event=False,
                argv=argv,
            )
        except CliError as exc:
            warnings.append({"home": str(target_home), "message": str(exc)})
            continue
        synced_homes.append(
            {
                "home": str(target_home),
                "artifact_id": payload.get("artifact_id"),
            }
        )
    return synced_homes, warnings


def _jwt_claims(tokens: dict[str, object]) -> dict[str, object]:
    claims: dict[str, object] = {}
    for key in ("id_token", "access_token"):
        token = _string_or_none(tokens.get(key))
        if token is None:
            continue
        decoded = _decode_jwt_payload(token)
        claims.update({claim_key: claim_value for claim_key, claim_value in decoded.items() if claim_key not in claims})
    return claims


def _decode_jwt_payload(token: str) -> dict[str, object]:
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1]
    padding = "=" * (-len(payload) % 4)
    try:
        decoded = base64.urlsafe_b64decode((payload + padding).encode("ascii"))
        parsed = json.loads(decoded.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {}
    if not isinstance(parsed, dict):
        return {}
    return parsed


def _claim_string(claims: dict[str, object], key: str) -> str | None:
    return _string_or_none(claims.get(key))


def _claim_int(claims: dict[str, object], key: str) -> int | None:
    value = claims.get(key)
    if isinstance(value, int):
        return value
    return None


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


__all__ = [
    "materialize_codex_account_to_home",
    "promote_verified_codex_auth_from_home",
    "read_codex_auth_info",
    "register_codex_account_from_auth_file",
    "inspect_codex_account_home",
]
