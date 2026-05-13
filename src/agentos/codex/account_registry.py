from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
from dataclasses import dataclass, replace
from pathlib import Path

from agentos._core.clock import utc_now_iso
from agentos._core.errors import CliError
from agentos._core.path_validation import validate_string_for_path
from agentos._core.project import agentos_home_dir
from agentos._core.project_command_log import record_activity_event

CODEX_AUTH_FILENAME = "auth.json"
CODEX_PROVIDER = "codex"


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
    info = read_codex_auth_info(auth_file.expanduser())
    info = _apply_manual_metadata(info, email=email)
    provider_root = _provider_root()
    account_dir = _account_dir(normalized_account)
    manifest_path = account_dir / "manifest.json"
    _validate_account_identity(manifest_path, account=normalized_account, info=info)
    preserved_pointer = _preserve_existing_account_pointer(account_dir, normalized_account, info.account_id)
    stored_file = _store_provider_file(info)
    registry_entry, appended = _append_registry_entry(
        account=normalized_account,
        info=info,
        source_auth_file=info.path,
    )
    manifest = _write_account_manifest(
        account=normalized_account,
        info=info,
    )
    _replace_account_pointer(account_dir, info.sha256)
    result = {
        "status": "ok",
        "command": "agent accounts register",
        "provider": CODEX_PROVIDER,
        "account": normalized_account,
        "auth_file": str(info.path),
        "auth": info.safe_payload(),
        "provider_root": str(provider_root),
        "stored_file": str(stored_file),
        "registry_entry": registry_entry,
        "registry_appended": appended,
        "manifest": manifest,
    }
    if preserved_pointer is not None:
        result["preserved_previous_pointer"] = preserved_pointer
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
            "auth_sha256": info.sha256,
            "stored_file": _registry_file(info.sha256),
            "registry_appended": appended,
        },
    )
    return result


def link_codex_account_to_home(
    *,
    home: Path,
    account: str,
    argv: list[str] | tuple[str, ...] = (),
) -> dict[str, object]:
    normalized_home = home.expanduser().resolve()
    normalized_account = validate_string_for_path(account, field_name="account")
    auth_path = _home_auth_path(normalized_home)
    manifest = _load_account_manifest(normalized_account)
    account_id = _require_manifest_string(manifest, "account_id")
    previous_auth: dict[str, object] | None = None

    try:
        if auth_path.exists() or auth_path.is_symlink():
            existing_info = read_codex_auth_info(auth_path)
            previous_auth = existing_info.safe_payload()
            if existing_info.account_id != account_id:
                message = (
                    "refusing to replace codex auth for a different account: "
                    f"{auth_path} has {existing_info.account_id}, expected {account_id}"
                )
                _record_link_failure(
                    argv=argv,
                    account=normalized_account,
                    home=normalized_home,
                    auth_path=auth_path,
                    message=message,
                    payload={
                        "account_id": account_id,
                        "previous_home_account_id": existing_info.account_id,
                        "previous_home_auth_sha256": existing_info.sha256,
                    },
                )
                raise CliError(message)
            register_codex_account_from_auth_file(
                auth_file=auth_path,
                account=normalized_account,
                argv=argv,
            )
            manifest = _load_account_manifest(normalized_account)

        source_auth = _active_auth_path(manifest)
        destination = _copy_auth_to_home(source_auth, auth_path)
        copied_info = read_codex_auth_info(destination)
        payload = {
            "provider": CODEX_PROVIDER,
            "account": normalized_account,
            "account_id": account_id,
            "email": manifest.get("email"),
            "home": str(normalized_home),
            "auth_path": str(auth_path),
            "source_auth_file": str(source_auth),
            "source_sha256": copied_info.sha256,
            "copied_sha256": copied_info.sha256,
            "previous_home_auth": previous_auth,
            "action": "copied",
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
            "source_auth_file": str(source_auth),
            "copied_auth": copied_info.safe_payload(),
            "previous_home_auth": previous_auth,
        }
    except CliError as exc:
        if not _link_failure_already_logged(exc):
            _record_link_failure(
                argv=argv,
                account=normalized_account,
                home=normalized_home,
                auth_path=auth_path,
                message=str(exc),
                payload={"message": str(exc)},
            )
        raise


def inspect_codex_account_home(*, home: Path) -> dict[str, object]:
    normalized_home = home.expanduser().resolve()
    auth_path = _home_auth_path(normalized_home)
    path_kind = _path_kind(auth_path)
    base: dict[str, object] = {
        "status": "ok",
        "command": "agent accounts status",
        "provider": CODEX_PROVIDER,
        "home": str(normalized_home),
        "auth_path": str(auth_path),
        "path_kind": path_kind,
    }
    latest_link = _latest_link_event_for_home(normalized_home)
    if latest_link is not None:
        base["latest_link_event"] = latest_link
    if path_kind == "missing":
        base["classification"] = "missing"
        return base

    try:
        info = read_codex_auth_info(auth_path)
    except CliError as exc:
        base["classification"] = "broken"
        base["error"] = str(exc)
        return base

    entries = _registry_entries()
    hash_matches = [entry for entry in entries if entry.get("sha256") == info.sha256]
    account_matches = [entry for entry in entries if entry.get("account_id") == info.account_id]
    active_matches = [
        entry
        for entry in hash_matches
        if _manifest_active_sha(_string_or_none(entry.get("account"))) == info.sha256
    ]
    base["auth"] = info.safe_payload()
    base["registry_matches"] = hash_matches
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


def _apply_manual_metadata(info: CodexAuthInfo, *, email: str | None) -> CodexAuthInfo:
    normalized_email = _string_or_none(email)
    if normalized_email is None:
        return info
    return replace(info, email=normalized_email)


def _validate_account_identity(manifest_path: Path, *, account: str, info: CodexAuthInfo) -> None:
    if not manifest_path.exists():
        return
    manifest = _load_json_object(manifest_path, description="codex account manifest")
    existing_account_id = _string_or_none(manifest.get("account_id"))
    if existing_account_id is not None and existing_account_id != info.account_id:
        raise CliError(
            f"codex account alias {account} is already registered for account_id "
            f"{existing_account_id}; refusing auth for {info.account_id}"
        )


def _preserve_existing_account_pointer(
    account_dir: Path,
    account: str,
    expected_account_id: str,
) -> dict[str, object] | None:
    pointer = account_dir / CODEX_AUTH_FILENAME
    if not pointer.exists() or pointer.is_symlink():
        return None
    info = read_codex_auth_info(pointer)
    manifest_path = account_dir / "manifest.json"
    if manifest_path.exists():
        manifest = _load_json_object(manifest_path, description="codex account manifest")
        account_id = _string_or_none(manifest.get("account_id"))
        if account_id is not None and account_id != info.account_id:
            raise CliError(
                f"existing codex account auth pointer for {account} has account_id "
                f"{info.account_id}, expected {account_id}"
            )
    elif info.account_id != expected_account_id:
        raise CliError(
            f"existing codex account auth pointer for {account} has account_id "
            f"{info.account_id}, expected {expected_account_id}"
        )
    stored_file = _store_provider_file(info)
    registry_entry, appended = _append_registry_entry(
        account=account,
        info=info,
        source_auth_file=pointer.resolve(),
    )
    return {
        "sha256": info.sha256,
        "stored_file": str(stored_file),
        "registry_entry": registry_entry,
        "registry_appended": appended,
    }


def _store_provider_file(info: CodexAuthInfo) -> Path:
    files_dir = _provider_root() / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    destination = files_dir / f"{info.sha256}.auth.json"
    if destination.exists():
        return destination
    _copy_file_atomic(info.path, destination)
    return destination


def _append_registry_entry(
    *,
    account: str,
    info: CodexAuthInfo,
    source_auth_file: Path,
) -> tuple[dict[str, object], bool]:
    entries = _registry_entries()
    existing = _matching_registry_entry(entries, account=account, sha256=info.sha256)
    if existing is not None:
        return existing, False

    entry = _registry_entry(account=account, info=info, source_auth_file=source_auth_file)
    registry_path = _registry_path()
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    with registry_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n")
    return entry, True


def _matching_registry_entry(
    entries: list[dict[str, object]],
    *,
    account: str,
    sha256: str,
) -> dict[str, object] | None:
    for entry in entries:
        if (
            entry.get("provider") == CODEX_PROVIDER
            and entry.get("account") == account
            and entry.get("sha256") == sha256
        ):
            return entry
    return None


def _registry_entry(
    *,
    account: str,
    info: CodexAuthInfo,
    source_auth_file: Path,
) -> dict[str, object]:
    entry: dict[str, object] = {
        "registered_at": utc_now_iso(),
        "provider": CODEX_PROVIDER,
        "account": account,
        "account_id": info.account_id,
        "sha256": info.sha256,
        "file": _registry_file(info.sha256),
        "source_auth_file": str(source_auth_file),
    }
    entry.update(info.metadata_payload())
    return entry


def _write_account_manifest(*, account: str, info: CodexAuthInfo) -> dict[str, object]:
    updated_at = utc_now_iso()
    manifest: dict[str, object] = {
        "schema_version": 1,
        "provider": CODEX_PROVIDER,
        "account": account,
        "account_id": info.account_id,
        "active_sha256": info.sha256,
        "active_file": _account_relative_file(info.sha256),
        "updated_at": updated_at,
    }
    manifest.update(info.metadata_payload())
    _write_json_file(_account_dir(account) / "manifest.json", manifest)
    return manifest


def _replace_account_pointer(account_dir: Path, sha256: str) -> None:
    account_dir.mkdir(parents=True, exist_ok=True)
    pointer = account_dir / CODEX_AUTH_FILENAME
    temp_pointer = account_dir / f".{CODEX_AUTH_FILENAME}.agentos-tmp-{os.getpid()}"
    if temp_pointer.exists() or temp_pointer.is_symlink():
        temp_pointer.unlink()
    os.symlink(_account_relative_file(sha256), temp_pointer)
    os.replace(temp_pointer, pointer)


def _load_account_manifest(account: str) -> dict[str, object]:
    manifest_path = _account_dir(account) / "manifest.json"
    if not manifest_path.exists():
        raise CliError(f"agent account is not registered: codex.{account}")
    manifest = _load_json_object(manifest_path, description="codex account manifest")
    if manifest.get("provider") != CODEX_PROVIDER or manifest.get("account") != account:
        raise CliError(f"codex account manifest does not match account: {manifest_path}")
    return manifest


def _active_auth_path(manifest: dict[str, object]) -> Path:
    sha256 = _require_manifest_string(manifest, "active_sha256")
    path = _provider_root() / "files" / f"{sha256}.auth.json"
    if not path.is_file():
        raise CliError(f"codex account active auth file does not exist: {path}")
    return path


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


def _registry_entries() -> list[dict[str, object]]:
    registry_path = _registry_path()
    if not registry_path.exists():
        return []
    entries: list[dict[str, object]] = []
    for line_number, line in enumerate(registry_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CliError(f"invalid codex registry JSONL at {registry_path}:{line_number}") from exc
        if not isinstance(payload, dict):
            raise CliError(f"codex registry entry must be a JSON object: {registry_path}:{line_number}")
        entries.append(payload)
    return entries


def _manifest_active_sha(account: str | None) -> str | None:
    if account is None:
        return None
    try:
        manifest = _load_account_manifest(account)
    except CliError:
        return None
    return _string_or_none(manifest.get("active_sha256"))


def _load_json_object(path: Path, *, description: str) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CliError(f"invalid {description} JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise CliError(f"{description} must be a JSON object: {path}")
    return payload


def _write_json_file(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.parent / f".{path.name}.agentos-tmp-{os.getpid()}"
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temp_path, path)


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
        payload={key: value for key, value in payload.items() if value is not None},
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


def _link_failure_already_logged(exc: CliError) -> bool:
    return str(exc).startswith("refusing to replace codex auth for a different account:")


def _latest_link_event_for_home(home: Path) -> dict[str, object] | None:
    activity_root = agentos_home_dir() / "activity"
    if not activity_root.exists():
        return None
    latest: dict[str, object] | None = None
    for path in sorted(activity_root.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            if event.get("event_type") != "agent.accounts.link":
                continue
            payload = event.get("payload")
            if not isinstance(payload, dict):
                continue
            if payload.get("provider") != CODEX_PROVIDER:
                continue
            if payload.get("home") != str(home):
                continue
            latest = _safe_activity_event(event)
    return latest


def _safe_activity_event(event: dict[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in event.items()
        if key in {"schema_version", "timetag", "event_type", "command", "argv", "status", "payload"}
    }


def _provider_root() -> Path:
    return agentos_home_dir() / "accounts" / CODEX_PROVIDER


def _registry_path() -> Path:
    return _provider_root() / "registry.jsonl"


def _account_dir(account: str) -> Path:
    return _provider_root() / "accounts" / account


def _home_auth_path(home: Path) -> Path:
    return home / CODEX_AUTH_FILENAME


def _registry_file(sha256: str) -> str:
    return f"files/{sha256}.auth.json"


def _account_relative_file(sha256: str) -> str:
    return f"../../files/{sha256}.auth.json"


def _require_manifest_string(manifest: dict[str, object], field: str) -> str:
    value = manifest.get(field)
    if not isinstance(value, str) or not value.strip():
        raise CliError(f"codex account manifest field {field} must be a non-empty string")
    return value


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


def _path_kind(path: Path) -> str:
    if path.is_symlink():
        return "symlink"
    if path.is_file():
        return "file"
    if path.exists():
        return "other"
    return "missing"


__all__ = [
    "inspect_codex_account_home",
    "link_codex_account_to_home",
    "read_codex_auth_info",
    "register_codex_account_from_auth_file",
]
