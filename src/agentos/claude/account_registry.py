from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentos._core.errors import CliError
from agentos._core.path_validation import validate_string_for_path
from agentos._core.process import run_process
from agentos.agent.account_registry import (
    account_exists,
    append_artifact,
    append_verification,
    artifacts_dir,
    load_account,
    load_accounts,
    record_account_event,
    read_artifacts,
    upsert_account,
)

CLAUDE_PROVIDER = "claude-code"
CLAUDE_AUTH_KIND = "ambient-browser-login"
CLAUDE_OAUTH_TOKEN_AUTH_KIND = "oauth-token-env"
CLAUDE_AMBIENT_ARTIFACT_SCHEMA_VERSION = 1
CLAUDE_CREDENTIALS_SERVICE_SUFFIX = "-credentials"
DEFAULT_CLAUDE_KEYCHAIN_TIMEOUT_SEC = 5


@dataclass(frozen=True)
class ClaudeOAuthTokenInfo:
    artifact_id: str
    token: str
    source: str

    def safe_payload(self) -> dict[str, object]:
        return {
            "artifact_id": self.artifact_id,
            "sha256": self.artifact_id,
            "source": self.source,
        }


@dataclass(frozen=True)
class ClaudeOAuthTokenMaterialization:
    account: str
    artifact_id: str
    token: str
    artifact_file: str

    def safe_display_value(self) -> str:
        return f"<managed:{CLAUDE_PROVIDER}/{self.account}:{self.artifact_id[:8]}>"


@dataclass(frozen=True)
class ClaudeSecureStorageInfo:
    home: Path
    payload: dict[str, Any]
    storage_kind: str
    keychain_service: str | None = None
    credentials_path: Path | None = None

    def safe_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "home": str(self.home),
            "storage_kind": self.storage_kind,
        }
        if self.keychain_service is not None:
            payload["keychain_service"] = self.keychain_service
        if self.credentials_path is not None:
            payload["credentials_path"] = str(self.credentials_path)
        return payload


@dataclass(frozen=True)
class ClaudeAmbientAuthInfo:
    home: Path
    artifact_id: str
    identity: dict[str, object]
    secure_storage: dict[str, Any]
    storage_kind: str
    keychain_service: str | None = None
    credentials_path: Path | None = None

    def artifact_payload(self) -> dict[str, object]:
        return _ambient_artifact_payload(
            identity=self.identity,
            secure_storage=self.secure_storage,
        )

    def metadata_payload(self) -> dict[str, object]:
        payload: dict[str, object] = dict(self.identity)
        payload["storage_kind"] = self.storage_kind
        if self.keychain_service is not None:
            payload["keychain_service"] = self.keychain_service
        if self.credentials_path is not None:
            payload["credentials_path"] = str(self.credentials_path)
        return payload

    def safe_payload(self) -> dict[str, object]:
        return {
            "artifact_id": self.artifact_id,
            "sha256": self.artifact_id,
            "home": str(self.home),
            "identity": dict(self.identity),
            "storage_kind": self.storage_kind,
            "keychain_service": self.keychain_service,
            "credentials_path": (
                str(self.credentials_path) if self.credentials_path is not None else None
            ),
        }


@dataclass(frozen=True)
class ClaudeAmbientAuthMaterialization:
    account: str
    artifact_id: str
    artifact_file: str
    identity: dict[str, object]
    secure_storage: dict[str, Any]


def register_claude_account(
    *,
    account: str,
    email: str | None,
    label: str | None = None,
    oauth_token_file: Path | str | None = None,
    argv: list[str] | tuple[str, ...] = (),
) -> dict[str, object]:
    normalized_account = validate_string_for_path(account, field_name="account")
    normalized_email = _string_or_none(email)
    if normalized_email is None:
        raise CliError("agent accounts register --provider claude-code requires --email")
    existing = _load_account_or_none(normalized_account)
    token_info = (
        read_claude_oauth_token_info(oauth_token_file)
        if oauth_token_file is not None
        else None
    )
    new_kind = (
        CLAUDE_OAUTH_TOKEN_AUTH_KIND if token_info is not None else CLAUDE_AUTH_KIND
    )
    if existing is not None:
        existing_kind = existing.get("auth_kind")
        if isinstance(existing_kind, str) and existing_kind != new_kind:
            raise CliError(
                f"account {normalized_account} already registered with auth_kind {existing_kind}; "
                "remove the account before re-registering with a different auth_kind"
            )
    if token_info is None:
        updates: dict[str, object] = {
            "auth_kind": CLAUDE_AUTH_KIND,
            "email": normalized_email,
            "label": _string_or_none(label),
        }
        if existing is None:
            updates["active_artifact_id"] = None
        artifact_entry = None
        artifact_appended = False
        stored_file = None
    else:
        stored_file = _store_oauth_token_artifact(token_info)
        artifact_entry, artifact_appended = _append_oauth_token_artifact_entry(
            account=normalized_account,
            info=token_info,
        )
        updates = {
            "auth_kind": CLAUDE_OAUTH_TOKEN_AUTH_KIND,
            "active_artifact_id": token_info.artifact_id,
            "artifact_file": _artifact_relative_file(token_info.artifact_id),
            "email": normalized_email,
            "label": _string_or_none(label),
        }
    account_record = upsert_account(
        CLAUDE_PROVIDER,
        normalized_account,
        updates,
    )
    record_account_event(
        event_type="agent.accounts.register",
        command="agent accounts register",
        argv=argv,
        status="ok",
        payload={
            "provider": CLAUDE_PROVIDER,
            "account": normalized_account,
            "email": normalized_email,
            "auth_kind": new_kind,
            "artifact_id": token_info.artifact_id if token_info is not None else None,
            "artifact_appended": artifact_appended,
        },
    )
    payload: dict[str, object] = {
        "status": "ok",
        "command": "agent accounts register",
        "provider": CLAUDE_PROVIDER,
        "account": normalized_account,
        "account_record": account_record,
    }
    if token_info is not None:
        payload.update(
            {
                "auth": token_info.safe_payload(),
                "provider_root": str(_provider_root()),
                "stored_file": str(stored_file),
                "artifact_entry": artifact_entry,
                "artifact_appended": artifact_appended,
            }
        )
    return payload


def materialize_claude_account_to_home(
    *,
    account: str,
    home: Path | None = None,
    force: bool = False,
    argv: list[str] | tuple[str, ...] = (),
) -> dict[str, object]:
    normalized_account = validate_string_for_path(account, field_name="account")
    account_record = load_account(CLAUDE_PROVIDER, normalized_account)
    normalized_home = home.expanduser().resolve() if home is not None else None
    if (
        normalized_home is not None
        and account_record.get("auth_kind") == CLAUDE_AUTH_KIND
        and _string_or_none(account_record.get("active_artifact_id")) is not None
    ):
        try:
            materialization = load_claude_ambient_auth_for_account(normalized_account)
            identity_state = write_claude_home_identity(
                home=normalized_home,
                identity=materialization.identity,
                force=force,
            )
            storage_state = write_claude_secure_storage(
                home=normalized_home,
                payload=materialization.secure_storage,
            )
        except CliError as exc:
            record_account_event(
                event_type="account.auth.materialized",
                command="agent accounts materialize",
                argv=argv,
                status="error",
                payload={
                    "provider": CLAUDE_PROVIDER,
                    "account": normalized_account,
                    "home": str(normalized_home),
                    "kind": "artifact",
                    "force": force,
                    "message": str(exc),
                },
            )
            raise
        event_payload = {
            "provider": CLAUDE_PROVIDER,
            "account": normalized_account,
            "home": str(normalized_home),
            "kind": "artifact",
            "force": force,
            "artifact_id": materialization.artifact_id,
            "artifact_file": materialization.artifact_file,
            "storage": storage_state.safe_payload(),
            "identity": identity_state,
        }
        record_account_event(
            event_type="account.auth.materialized",
            command="agent accounts materialize",
            argv=argv,
            status="ok",
            payload=event_payload,
        )
        return {
            "status": "ok",
            "command": "agent accounts materialize",
            "provider": CLAUDE_PROVIDER,
            "account": normalized_account,
            "home": str(normalized_home),
            "kind": "artifact",
            "force": force,
            "artifact_id": materialization.artifact_id,
            "artifact_file": materialization.artifact_file,
            "storage": storage_state.safe_payload(),
            "identity": identity_state,
        }

    event_payload: dict[str, object] = {
        "provider": CLAUDE_PROVIDER,
        "account": normalized_account,
        "kind": "claimed",
        "force": force,
    }
    if normalized_home is not None:
        event_payload["home"] = str(normalized_home)
    record_account_event(
        event_type="account.auth.materialized",
        command="agent accounts materialize",
        argv=argv,
        status="ok",
        payload=event_payload,
    )
    payload: dict[str, object] = {
        "status": "ok",
        "command": "agent accounts materialize",
        "provider": CLAUDE_PROVIDER,
        "account": normalized_account,
        "kind": "claimed",
        "force": force,
    }
    if normalized_home is not None:
        payload["home"] = str(normalized_home)
    return payload


def has_claude_oauth_token_kind(account: str) -> bool:
    normalized_account = validate_string_for_path(account, field_name="account")
    account_record = load_account(CLAUDE_PROVIDER, normalized_account)
    return account_record.get("auth_kind") == CLAUDE_OAUTH_TOKEN_AUTH_KIND


def load_claude_oauth_token_for_account(
    account: str,
) -> ClaudeOAuthTokenMaterialization:
    normalized_account = validate_string_for_path(account, field_name="account")
    account_record = load_account(CLAUDE_PROVIDER, normalized_account)
    if account_record.get("auth_kind") != CLAUDE_OAUTH_TOKEN_AUTH_KIND:
        raise CliError(
            "claude-code account has no oauth token artifact; register one with: "
            "agentos agent accounts register --provider claude-code "
            f"--account {normalized_account} --email <email> --oauth-token-file <path>"
        )
    active_artifact_id = _require_account_string(
        account_record,
        "active_artifact_id",
    )
    artifact_file = _require_account_string(account_record, "artifact_file")
    artifact_path = _provider_root() / artifact_file
    if not artifact_path.is_file():
        raise CliError(f"claude oauth token artifact file does not exist: {artifact_path}")
    token = artifact_path.read_text(encoding="utf-8").strip()
    if not token:
        raise CliError(f"claude oauth token artifact is empty: {artifact_path}")
    return ClaudeOAuthTokenMaterialization(
        account=normalized_account,
        artifact_id=active_artifact_id,
        token=token,
        artifact_file=artifact_file,
    )


def load_claude_ambient_auth_for_account(
    account: str,
) -> ClaudeAmbientAuthMaterialization:
    normalized_account = validate_string_for_path(account, field_name="account")
    account_record = load_account(CLAUDE_PROVIDER, normalized_account)
    if account_record.get("auth_kind") != CLAUDE_AUTH_KIND:
        raise CliError(
            "claude-code account has no ambient browser-login artifact; register one "
            "from a logged-in home before materializing or reconciling"
        )
    active_artifact_id = _require_account_string(
        account_record,
        "active_artifact_id",
    )
    artifact_file = _require_account_string(account_record, "artifact_file")
    artifact_path = _provider_root() / artifact_file
    if not artifact_path.is_file():
        raise CliError(f"claude ambient auth artifact file does not exist: {artifact_path}")
    try:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CliError(f"invalid claude ambient auth artifact JSON: {artifact_path}") from exc
    if not isinstance(payload, dict):
        raise CliError(f"claude ambient auth artifact must be an object: {artifact_path}")
    if payload.get("provider") != CLAUDE_PROVIDER:
        raise CliError(f"claude ambient auth artifact provider mismatch: {artifact_path}")
    if payload.get("auth_kind") != CLAUDE_AUTH_KIND:
        raise CliError(f"claude ambient auth artifact auth_kind mismatch: {artifact_path}")
    identity = payload.get("identity")
    if not isinstance(identity, dict):
        raise CliError(f"claude ambient auth artifact identity must be an object: {artifact_path}")
    secure_storage = payload.get("secure_storage")
    if not isinstance(secure_storage, dict):
        raise CliError(
            f"claude ambient auth artifact secure_storage must be an object: {artifact_path}"
        )
    return ClaudeAmbientAuthMaterialization(
        account=normalized_account,
        artifact_id=active_artifact_id,
        artifact_file=artifact_file,
        identity=identity,
        secure_storage=secure_storage,
    )


def read_claude_ambient_auth_info(home: Path) -> ClaudeAmbientAuthInfo:
    normalized_home = home.expanduser().resolve()
    home_config = read_claude_home_config(normalized_home)
    identity = _claude_identity_from_home_config(home_config, home=normalized_home)
    storage = read_claude_secure_storage_info(normalized_home)
    payload = _ambient_artifact_payload(
        identity=identity,
        secure_storage=storage.payload,
    )
    artifact_id = _sha256_json(payload)
    return ClaudeAmbientAuthInfo(
        home=normalized_home,
        artifact_id=artifact_id,
        identity=identity,
        secure_storage=storage.payload,
        storage_kind=storage.storage_kind,
        keychain_service=storage.keychain_service,
        credentials_path=storage.credentials_path,
    )


def register_claude_ambient_auth_from_home(
    *,
    home: Path,
    account: str,
    register_only: bool = False,
    argv: list[str] | tuple[str, ...] = (),
) -> dict[str, object]:
    normalized_account = validate_string_for_path(account, field_name="account")
    info = read_claude_ambient_auth_info(home)
    existing = _load_account_or_none(normalized_account)
    _validate_ambient_account_identity(
        existing,
        account=normalized_account,
        info=info,
    )
    stored_file = _store_ambient_auth_artifact(info)
    artifact_entry, artifact_appended = _append_ambient_auth_artifact_entry(
        account=normalized_account,
        info=info,
    )
    account_record = _write_ambient_account(
        account=normalized_account,
        info=info,
        activate=not register_only,
        existing=existing,
    )
    result = {
        "status": "ok",
        "command": "agent accounts register",
        "provider": CLAUDE_PROVIDER,
        "account": normalized_account,
        "home": str(info.home),
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
            "provider": CLAUDE_PROVIDER,
            "account": normalized_account,
            "email": _string_or_none(info.identity.get("email")),
            "account_uuid": _string_or_none(info.identity.get("account_uuid")),
            "auth_kind": CLAUDE_AUTH_KIND,
            "home": str(info.home),
            "artifact_id": info.artifact_id,
            "stored_file": _ambient_artifact_relative_file(info.artifact_id),
            "artifact_appended": artifact_appended,
            "register_only": register_only,
            "active_updated": not register_only,
            "storage_kind": info.storage_kind,
            "keychain_service": info.keychain_service,
        },
    )
    return result


def promote_verified_claude_ambient_auth_from_home(
    *,
    home: Path,
    account: str,
    source: str,
    start_path: Path | str = ".",
    sync_homes: bool = True,
    argv: list[str] | tuple[str, ...] = (),
) -> dict[str, object]:
    normalized_account = validate_string_for_path(account, field_name="account")
    normalized_source = validate_string_for_path(source, field_name="source")
    registration = register_claude_ambient_auth_from_home(
        home=home,
        account=normalized_account,
        register_only=True,
        argv=argv,
    )
    auth = registration.get("auth")
    if not isinstance(auth, dict):
        raise CliError("claude ambient auth registration did not return auth metadata")
    artifact_id = _require_payload_string(auth, "artifact_id")
    verification = append_verification(
        CLAUDE_PROVIDER,
        {
            "account": normalized_account,
            "artifact_id": artifact_id,
            "auth_kind": CLAUDE_AUTH_KIND,
            "home": str(Path(home).expanduser().resolve()),
            "source": normalized_source,
            "storage_kind": auth.get("storage_kind"),
        },
    )
    account_record = upsert_account(
        CLAUDE_PROVIDER,
        normalized_account,
        {
            "auth_kind": CLAUDE_AUTH_KIND,
            "active_artifact_id": artifact_id,
            "artifact_file": _ambient_artifact_relative_file(artifact_id),
            "last_verified_at": verification["verified_at"],
            "last_verified_source": normalized_source,
        },
    )
    synced_homes: list[dict[str, object]] = []
    sync_warnings: list[dict[str, object]] = []
    if sync_homes:
        synced_homes, sync_warnings = _sync_known_homes_from_verified_artifact(
            account=normalized_account,
            source_home=Path(home).expanduser().resolve(),
            start_path=start_path,
            argv=argv,
        )
    record_account_event(
        event_type="agent.accounts.verify",
        command=normalized_source,
        argv=argv,
        status="ok",
        payload={
            "provider": CLAUDE_PROVIDER,
            "account": normalized_account,
            "auth_kind": CLAUDE_AUTH_KIND,
            "home": str(Path(home).expanduser().resolve()),
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
        "provider": CLAUDE_PROVIDER,
        "account": normalized_account,
        "home": str(Path(home).expanduser().resolve()),
        "artifact_id": artifact_id,
        "artifact_appended": bool(registration.get("artifact_appended")),
        "verification": verification,
        "account_record": account_record,
        "synced_homes": synced_homes,
        "sync_warnings": sync_warnings,
    }


def inspect_claude_account_home(*, home: Path) -> dict[str, object]:
    normalized_home = home.expanduser().resolve()
    base: dict[str, object] = {
        "status": "ok",
        "command": "agent accounts status",
        "provider": CLAUDE_PROVIDER,
        "home": str(normalized_home),
    }
    if not normalized_home.exists():
        base["classification"] = "missing"
        return base

    try:
        info = read_claude_ambient_auth_info(normalized_home)
    except CliError as exc:
        base["classification"] = "broken"
        base["error"] = str(exc)
        return base

    hash_matches = _ambient_artifact_matches(artifact_id=info.artifact_id)
    account_matches = _accounts_for_ambient_identity(info.identity)
    active_matches = [
        account_record
        for account_record in account_matches
        if account_record.get("active_artifact_id") == info.artifact_id
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


def read_claude_oauth_token_info(path: Path | str) -> ClaudeOAuthTokenInfo:
    source = str(path)
    if source == "-":
        raw_token = sys.stdin.read()
    else:
        token_path = Path(path).expanduser()
        if not token_path.exists():
            raise CliError(f"claude oauth token file does not exist: {token_path}")
        if not token_path.is_file():
            raise CliError(f"claude oauth token path is not a file: {token_path}")
        raw_token = token_path.read_text(encoding="utf-8")
        source = str(token_path.resolve())
    token = raw_token.strip()
    if not token:
        raise CliError("claude oauth token is empty")
    artifact_id = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return ClaudeOAuthTokenInfo(
        artifact_id=artifact_id,
        token=token,
        source=source,
    )


def read_claude_home_config(home: Path) -> dict[str, object]:
    path = home / ".claude.json"
    if not path.is_file():
        raise CliError(f"claude-code home config does not exist: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CliError(f"invalid claude-code home config JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise CliError(f"claude-code home config must be an object: {path}")
    return payload


def read_claude_secure_storage(home: Path) -> dict[str, Any]:
    return read_claude_secure_storage_info(home).payload


def read_claude_secure_storage_info(home: Path) -> ClaudeSecureStorageInfo:
    normalized_home = home.expanduser().resolve()
    if sys.platform == "darwin":
        keychain_data = _read_claude_keychain_storage(normalized_home)
        if keychain_data is not None:
            service_name, payload = keychain_data
            return ClaudeSecureStorageInfo(
                home=normalized_home,
                payload=payload,
                storage_kind="macos-keychain",
                keychain_service=service_name,
            )
    credentials_path = normalized_home / ".credentials.json"
    if credentials_path.is_file():
        try:
            payload = json.loads(credentials_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CliError(f"invalid claude-code credentials file: {credentials_path}") from exc
        if isinstance(payload, dict):
            return ClaudeSecureStorageInfo(
                home=normalized_home,
                payload=payload,
                storage_kind="credentials-json",
                credentials_path=credentials_path,
            )
        raise CliError(f"claude-code credentials file must be an object: {credentials_path}")
    raise CliError(f"claude-code OAuth secure storage was not found for home: {normalized_home}")


def write_claude_secure_storage(
    *,
    home: Path,
    payload: dict[str, Any],
) -> ClaudeSecureStorageInfo:
    if not isinstance(payload, dict):
        raise CliError("claude-code secure storage payload must be an object")
    normalized_home = home.expanduser().resolve()
    normalized_home.mkdir(parents=True, exist_ok=True)
    if sys.platform == "darwin":
        service_name = claude_keychain_service_names(normalized_home)[0]
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        result = run_process(
            (
                "security",
                "add-generic-password",
                "-U",
                "-a",
                os.environ.get("USER", ""),
                "-s",
                service_name,
                "-w",
                raw,
            ),
            mode="capture",
            timeout_sec=DEFAULT_CLAUDE_KEYCHAIN_TIMEOUT_SEC,
        )
        if result.exit_code != 0:
            stderr = (result.stderr or "").strip()
            raise CliError(
                "failed to write claude-code credentials to macOS Keychain"
                + (f": {stderr}" if stderr else "")
            )
        return ClaudeSecureStorageInfo(
            home=normalized_home,
            payload=payload,
            storage_kind="macos-keychain",
            keychain_service=service_name,
        )
    credentials_path = normalized_home / ".credentials.json"
    _write_json_file_atomic(credentials_path, payload, mode=0o600)
    return ClaudeSecureStorageInfo(
        home=normalized_home,
        payload=payload,
        storage_kind="credentials-json",
        credentials_path=credentials_path,
    )


def write_claude_home_identity(
    *,
    home: Path,
    identity: dict[str, object],
    force: bool = False,
) -> dict[str, object]:
    normalized_home = home.expanduser().resolve()
    normalized_home.mkdir(parents=True, exist_ok=True)
    path = normalized_home / ".claude.json"
    if path.exists():
        try:
            config = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            if not force:
                raise CliError(f"invalid claude-code home config JSON: {path}") from exc
            config = {}
        if not isinstance(config, dict):
            if not force:
                raise CliError(f"claude-code home config must be an object: {path}")
            config = {}
    else:
        config = {}
    oauth_account = config.get("oauthAccount")
    if oauth_account is not None and not isinstance(oauth_account, dict):
        if not force:
            raise CliError(f"claude-code home oauthAccount must be an object: {path}")
        oauth_account = {}
    if oauth_account is None:
        oauth_account = {}
    target_identity = _oauth_account_from_identity(identity)
    mismatch = _home_identity_mismatch(oauth_account, target_identity)
    if mismatch is not None and not force:
        field, existing_value, incoming_value = mismatch
        raise CliError(
            "refusing to replace claude-code home identity without --force: "
            f"{path} has {field} {existing_value}, artifact has {incoming_value}"
        )
    oauth_account.update(target_identity)
    config["oauthAccount"] = oauth_account
    _write_json_file_atomic(path, config)
    return {
        "home_config": str(path),
        "action": "written",
        "forced": force,
        "identity": dict(identity),
    }


def claude_keychain_service_names(home: Path) -> tuple[str, ...]:
    normalized_home = home.expanduser().resolve()
    home_hash = hashlib.sha256(str(normalized_home).encode("utf-8")).hexdigest()[:8]
    return (
        f"Claude Code{CLAUDE_CREDENTIALS_SERVICE_SUFFIX}-{home_hash}",
        f"Claude Code{CLAUDE_CREDENTIALS_SERVICE_SUFFIX}",
    )


def _store_oauth_token_artifact(info: ClaudeOAuthTokenInfo) -> Path:
    destination = _artifact_path(info.artifact_id)
    if destination.exists():
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path = destination.parent / f".{destination.name}.agentos-tmp-{os.getpid()}"
    if temp_path.exists() or temp_path.is_symlink():
        temp_path.unlink()
    try:
        temp_path.write_text(info.token, encoding="utf-8")
        temp_path.chmod(0o600)
        os.replace(temp_path, destination)
    finally:
        if temp_path.exists() or temp_path.is_symlink():
            temp_path.unlink()
    return destination


def _append_oauth_token_artifact_entry(
    *,
    account: str,
    info: ClaudeOAuthTokenInfo,
) -> tuple[dict[str, object], bool]:
    return append_artifact(
        CLAUDE_PROVIDER,
        {
            "account": account,
            "artifact_id": info.artifact_id,
            "auth_kind": CLAUDE_OAUTH_TOKEN_AUTH_KIND,
            "file": _artifact_relative_file(info.artifact_id),
            "source": info.source,
        },
    )


def _write_ambient_account(
    *,
    account: str,
    info: ClaudeAmbientAuthInfo,
    activate: bool,
    existing: dict[str, object] | None,
) -> dict[str, object]:
    updates: dict[str, object] = {
        "auth_kind": CLAUDE_AUTH_KIND,
    }
    for key in ("email", "account_uuid", "display_name", "organization_uuid"):
        value = _string_or_none(info.identity.get(key))
        if value is not None:
            updates[key] = value
    if activate:
        updates["active_artifact_id"] = info.artifact_id
        updates["artifact_file"] = _ambient_artifact_relative_file(info.artifact_id)
    elif existing is None:
        updates["active_artifact_id"] = None
    return upsert_account(
        CLAUDE_PROVIDER,
        account,
        updates,
    )


def _store_ambient_auth_artifact(info: ClaudeAmbientAuthInfo) -> Path:
    destination = _ambient_artifact_path(info.artifact_id)
    if destination.exists():
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path = destination.parent / f".{destination.name}.agentos-tmp-{os.getpid()}"
    if temp_path.exists() or temp_path.is_symlink():
        temp_path.unlink()
    try:
        temp_path.write_text(
            json.dumps(info.artifact_payload(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temp_path.chmod(0o600)
        os.replace(temp_path, destination)
    finally:
        if temp_path.exists() or temp_path.is_symlink():
            temp_path.unlink()
    return destination


def _append_ambient_auth_artifact_entry(
    *,
    account: str,
    info: ClaudeAmbientAuthInfo,
) -> tuple[dict[str, object], bool]:
    entry: dict[str, object] = {
        "account": account,
        "artifact_id": info.artifact_id,
        "auth_kind": CLAUDE_AUTH_KIND,
        "file": _ambient_artifact_relative_file(info.artifact_id),
        "source_home": str(info.home),
    }
    entry.update(info.metadata_payload())
    return append_artifact(CLAUDE_PROVIDER, entry)


def _read_claude_keychain_storage(
    home: Path,
) -> tuple[str, dict[str, Any]] | None:
    for service_name in claude_keychain_service_names(home):
        result = run_process(
            (
                "security",
                "find-generic-password",
                "-a",
                os.environ.get("USER", ""),
                "-s",
                service_name,
                "-w",
            ),
            mode="capture",
            timeout_sec=DEFAULT_CLAUDE_KEYCHAIN_TIMEOUT_SEC,
        )
        if result.exit_code != 0:
            continue
        raw = result.stdout or ""
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return service_name, payload
    return None


def _write_json_file_atomic(
    path: Path,
    payload: dict[str, Any],
    *,
    mode: int | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.parent / f".{path.name}.agentos-tmp-{os.getpid()}"
    if temp_path.exists() or temp_path.is_symlink():
        temp_path.unlink()
    try:
        temp_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if mode is not None:
            temp_path.chmod(mode)
        os.replace(temp_path, path)
    finally:
        if temp_path.exists() or temp_path.is_symlink():
            temp_path.unlink()


def _oauth_account_from_identity(identity: dict[str, object]) -> dict[str, object]:
    payload: dict[str, object] = {}
    field_map = {
        "account_uuid": "accountUuid",
        "email": "emailAddress",
        "display_name": "displayName",
        "organization_uuid": "organizationUuid",
    }
    for source, target in field_map.items():
        value = _string_or_none(identity.get(source))
        if value is not None:
            payload[target] = value
    if "accountUuid" not in payload and "emailAddress" not in payload:
        raise CliError("claude-code ambient artifact identity must include account_uuid or email")
    return payload


def _home_identity_mismatch(
    existing: dict[str, object],
    incoming: dict[str, object],
) -> tuple[str, str, str] | None:
    for field in ("accountUuid", "emailAddress"):
        existing_value = _string_or_none(existing.get(field))
        incoming_value = _string_or_none(incoming.get(field))
        if existing_value is not None and incoming_value is not None and existing_value != incoming_value:
            return field, existing_value, incoming_value
    return None


def _claude_identity_from_home_config(
    home_config: dict[str, object],
    *,
    home: Path,
) -> dict[str, object]:
    oauth_account = home_config.get("oauthAccount")
    if not isinstance(oauth_account, dict):
        raise CliError(f"claude-code home config is missing oauthAccount: {home / '.claude.json'}")
    identity = {
        key: value
        for key, value in {
            "account_uuid": _string_or_none(oauth_account.get("accountUuid")),
            "email": _string_or_none(oauth_account.get("emailAddress")),
            "display_name": _string_or_none(oauth_account.get("displayName")),
            "organization_uuid": _string_or_none(oauth_account.get("organizationUuid")),
        }.items()
        if value is not None
    }
    if not identity.get("account_uuid") and not identity.get("email"):
        raise CliError(
            "claude-code home oauthAccount must include accountUuid or emailAddress: "
            f"{home / '.claude.json'}"
        )
    return identity


def _ambient_artifact_payload(
    *,
    identity: dict[str, object],
    secure_storage: dict[str, Any],
) -> dict[str, object]:
    return {
        "schema_version": CLAUDE_AMBIENT_ARTIFACT_SCHEMA_VERSION,
        "provider": CLAUDE_PROVIDER,
        "auth_kind": CLAUDE_AUTH_KIND,
        "identity": identity,
        "secure_storage": secure_storage,
    }


def _sha256_json(payload: dict[str, object]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _validate_ambient_account_identity(
    existing: dict[str, object] | None,
    *,
    account: str,
    info: ClaudeAmbientAuthInfo,
) -> None:
    if existing is None:
        return
    existing_kind = existing.get("auth_kind")
    if isinstance(existing_kind, str) and existing_kind != CLAUDE_AUTH_KIND:
        raise CliError(
            f"account {account} already registered with auth_kind {existing_kind}; "
            "remove the account before registering ambient browser-login auth"
        )
    for field in ("email", "account_uuid"):
        existing_value = _string_or_none(existing.get(field))
        info_value = _string_or_none(info.identity.get(field))
        if existing_value is not None and info_value is not None and existing_value != info_value:
            raise CliError(
                f"claude-code account alias {account} is already registered with "
                f"{field} {existing_value}; refusing auth for {info_value}"
            )


def _ambient_artifact_matches(*, artifact_id: str) -> list[dict[str, object]]:
    return [
        entry
        for entry in read_artifacts(CLAUDE_PROVIDER)
        if entry.get("artifact_id") == artifact_id
        and entry.get("auth_kind") == CLAUDE_AUTH_KIND
    ]


def _accounts_for_ambient_identity(identity: dict[str, object]) -> list[dict[str, object]]:
    registry = load_accounts(CLAUDE_PROVIDER)
    accounts = registry.get("accounts")
    if not isinstance(accounts, dict):
        return []
    email = _string_or_none(identity.get("email"))
    account_uuid = _string_or_none(identity.get("account_uuid"))
    matches = []
    for record in accounts.values():
        if not isinstance(record, dict) or record.get("auth_kind") != CLAUDE_AUTH_KIND:
            continue
        record_email = _string_or_none(record.get("email"))
        record_account_uuid = _string_or_none(record.get("account_uuid"))
        if account_uuid is not None and record_account_uuid == account_uuid:
            matches.append(record)
        elif email is not None and record_email == email:
            matches.append(record)
    return sorted(matches, key=lambda record: str(record.get("account", "")))


def _load_account_or_none(account: str) -> dict[str, object] | None:
    if not account_exists(CLAUDE_PROVIDER, account):
        return None
    return load_account(CLAUDE_PROVIDER, account)


def _provider_root() -> Path:
    from agentos.agent.account_registry import account_provider_root

    return account_provider_root(CLAUDE_PROVIDER)


def _artifact_path(artifact_id: str) -> Path:
    return artifacts_dir(CLAUDE_PROVIDER) / f"{artifact_id}.oauth-token"


def _artifact_relative_file(artifact_id: str) -> str:
    return f"artifacts/{artifact_id}.oauth-token"


def _ambient_artifact_path(artifact_id: str) -> Path:
    return artifacts_dir(CLAUDE_PROVIDER) / f"{artifact_id}.ambient-auth.json"


def _ambient_artifact_relative_file(artifact_id: str) -> str:
    return f"artifacts/{artifact_id}.ambient-auth.json"


def _require_account_string(account: dict[str, object], field: str) -> str:
    value = account.get(field)
    if not isinstance(value, str) or not value.strip():
        raise CliError(f"claude-code account field {field} must be a non-empty string")
    return value.strip()


def _require_payload_string(payload: dict[str, object], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise CliError(f"claude-code payload field {field} must be a non-empty string")
    return value.strip()


def _sync_known_homes_from_verified_artifact(
    *,
    account: str,
    source_home: Path,
    start_path: Path | str,
    argv: list[str] | tuple[str, ...],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    from agentos.claude.account_reconcile import discover_claude_reconcile_homes

    synced_homes: list[dict[str, object]] = []
    warnings: list[dict[str, object]] = []
    for home_summary in discover_claude_reconcile_homes(
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
            payload = materialize_claude_account_to_home(
                home=target_home,
                account=account,
                argv=argv,
            )
        except CliError as exc:
            warnings.append(
                {
                    "home": str(target_home),
                    "message": str(exc),
                }
            )
            continue
        synced_homes.append(
            {
                "home": str(target_home),
                "artifact_id": payload.get("artifact_id"),
            }
        )
    return synced_homes, warnings


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


__all__ = [
    "CLAUDE_AUTH_KIND",
    "CLAUDE_OAUTH_TOKEN_AUTH_KIND",
    "ClaudeAmbientAuthInfo",
    "ClaudeAmbientAuthMaterialization",
    "ClaudeOAuthTokenMaterialization",
    "ClaudeSecureStorageInfo",
    "claude_keychain_service_names",
    "inspect_claude_account_home",
    "materialize_claude_account_to_home",
    "load_claude_ambient_auth_for_account",
    "load_claude_oauth_token_for_account",
    "promote_verified_claude_ambient_auth_from_home",
    "read_claude_ambient_auth_info",
    "read_claude_home_config",
    "read_claude_oauth_token_info",
    "read_claude_secure_storage",
    "read_claude_secure_storage_info",
    "register_claude_ambient_auth_from_home",
    "register_claude_account",
    "write_claude_home_identity",
    "write_claude_secure_storage",
]
