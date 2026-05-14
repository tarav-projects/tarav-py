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
from agentos._core.project_command_log import record_activity_event
from agentos.agent.account_registry import (
    account_provider_root,
    append_artifact,
    artifacts_dir,
    load_account,
    load_accounts,
    load_links,
    read_artifacts,
    upsert_account,
    upsert_link,
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
        "account_record": account_record,
    }
    _record_account_event(
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
        },
    )
    return result


def link_codex_account_to_home(
    *,
    home: Path,
    account: str,
    force: bool = False,
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
        target_state = _inspect_target_before_link(
            auth_path,
            requested_account=normalized_account,
            force=force,
            argv=argv,
        )
        _copy_auth_to_home(source_auth, auth_path)
        copied_info = read_codex_auth_info(auth_path)
        previous_link, link_record = upsert_link(
            CODEX_PROVIDER,
            normalized_home,
            {
                "kind": "artifact",
                "account": normalized_account,
                "account_id": account_id,
                "artifact_id": active_artifact_id,
                "auth_path": str(auth_path),
            },
        )
        payload = {
            "provider": CODEX_PROVIDER,
            "account": normalized_account,
            "account_id": account_id,
            "home": str(normalized_home),
            "auth_path": str(auth_path),
            "kind": "artifact",
            "force": force,
            "artifact_id": active_artifact_id,
            "copied_artifact_id": copied_info.sha256,
            "target_before_link": target_state,
            "previous_link": previous_link,
            "link": link_record,
        }
        _record_account_event(
            event_type="agent.accounts.link",
            command="agent accounts link",
            argv=argv,
            status="ok",
            payload=payload,
        )
        return {
            "status": "ok",
            "command": "agent accounts link",
            "provider": CODEX_PROVIDER,
            "account": normalized_account,
            "home": str(normalized_home),
            "auth_path": str(auth_path),
            "kind": "artifact",
            "force": force,
            "source_auth_file": str(source_auth),
            "copied_auth": copied_info.safe_payload(),
            "target_before_link": target_state,
            "previous_link": previous_link,
            "link": link_record,
        }
    except CliError as exc:
        _record_link_failure(
            argv=argv,
            account=normalized_account,
            home=normalized_home,
            auth_path=auth_path,
            message=str(exc),
            payload={"force": force},
        )
        raise


def inspect_codex_account_home(*, home: Path) -> dict[str, object]:
    normalized_home = home.expanduser().resolve()
    auth_path = _home_auth_path(normalized_home)
    link = _link_for_home(normalized_home)
    base: dict[str, object] = {
        "status": "ok",
        "command": "agent accounts status",
        "provider": CODEX_PROVIDER,
        "home": str(normalized_home),
        "auth_path": str(auth_path),
        "path_kind": _path_kind(auth_path),
        "link": link,
    }
    if not auth_path.exists() and not auth_path.is_symlink():
        base["classification"] = "missing"
        base["link_consistency"] = "missing" if link is not None else "unlinked"
        return base

    try:
        info = read_codex_auth_info(auth_path)
    except CliError as exc:
        base["classification"] = "broken"
        base["link_consistency"] = "broken" if link is not None else "unlinked-broken"
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
    base["link_consistency"] = _codex_link_consistency(link, info)
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


def _inspect_target_before_link(
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


def _write_account(*, account: str, info: CodexAuthInfo) -> dict[str, object]:
    return upsert_account(
        CODEX_PROVIDER,
        account,
        {
            "auth_kinds": [CODEX_AUTH_KIND],
            "active_artifact_id": info.sha256,
            "account_id": info.account_id,
            "email": info.email,
            "artifact_file": _artifact_relative_file(info.sha256),
            **info.metadata_payload(),
        },
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


def _link_for_home(home: Path) -> dict[str, object] | None:
    links = load_links(CODEX_PROVIDER).get("links")
    if not isinstance(links, dict):
        return None
    link = links.get(str(home.expanduser().resolve()))
    return link if isinstance(link, dict) else None


def _codex_link_consistency(link: dict[str, object] | None, info: CodexAuthInfo) -> str:
    if link is None:
        return "unlinked"
    if link.get("kind") != "artifact":
        return "mismatched-kind"
    artifact_id = _string_or_none(link.get("artifact_id"))
    account = _string_or_none(link.get("account"))
    if artifact_id == info.sha256:
        return "verified"
    if account is not None:
        try:
            account_record = load_account(CODEX_PROVIDER, account)
        except CliError:
            return "stale"
        if account_record.get("account_id") == info.account_id:
            return "stale"
    return "mismatched"


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


def _record_account_event(
    *,
    event_type: str,
    command: str,
    argv: list[str] | tuple[str, ...],
    status: str,
    payload: dict[str, object],
) -> None:
    record_activity_event(
        event_type=event_type,
        command=command,
        argv=argv,
        status=status,
        payload=payload,
    )


def _record_link_failure(
    *,
    argv: list[str] | tuple[str, ...],
    account: str,
    home: Path,
    auth_path: Path,
    message: str,
    payload: dict[str, object],
) -> None:
    _record_account_event(
        event_type="agent.accounts.link",
        command="agent accounts link",
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
    "link_codex_account_to_home",
    "read_codex_auth_info",
    "register_codex_account_from_auth_file",
    "inspect_codex_account_home",
]
