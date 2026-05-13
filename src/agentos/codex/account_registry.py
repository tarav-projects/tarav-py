from __future__ import annotations

import base64
import datetime
import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from agentos._core.clock import utc_now_iso
from agentos._core.errors import CliError
from agentos._core.path_validation import validate_string_for_path
from agentos._core.project import agentos_home_dir, global_config_path, load_global_config
from agentos._core.project_command_log import record_activity_event

CODEX_AUTH_FILENAME = "auth.json"
CODEX_PROVIDER = "codex"
ACCOUNT_REGISTRY_PATH = ("agent", "account_registry")


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

    def safe_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "path": str(self.path),
            "sha256": self.sha256,
            "account_id": self.account_id,
            "mtime": self.mtime,
        }
        if self.auth_mode is not None:
            payload["auth_mode"] = self.auth_mode
        if self.email is not None:
            payload["email"] = self.email
        if self.last_refresh is not None:
            payload["last_refresh"] = self.last_refresh
        if self.jwt_iat is not None:
            payload["jwt_iat"] = self.jwt_iat
        return payload


def register_codex_account_from_home(
    *,
    home: Path,
    account: str,
    argv: list[str] | tuple[str, ...] = (),
) -> dict[str, object]:
    normalized_home = home.expanduser().resolve()
    normalized_account = validate_string_for_path(account, field_name="account")
    auth_path = _home_auth_path(normalized_home)
    info = read_codex_auth_info(auth_path)
    storage = _account_storage_path(normalized_account)
    snapshot = _store_snapshot(
        info,
        account=normalized_account,
        storage=storage,
        source_home=normalized_home,
    )
    registry_entry = _upsert_account_registry_entry(
        account=normalized_account,
        info=info,
        storage=storage,
    )
    result = {
        "status": "ok",
        "command": "agent accounts register",
        "provider": CODEX_PROVIDER,
        "account": normalized_account,
        "home": str(normalized_home),
        "auth": info.safe_payload(),
        "registry_key": _registry_key(normalized_account),
        "registry_entry": registry_entry,
        "snapshot": snapshot,
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
            "home": str(normalized_home),
            "auth_path": str(auth_path),
            "auth_sha256": info.sha256,
            "snapshot_path": snapshot["path"],
            "snapshot_sha256": snapshot["sha256"],
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
    registry_entry = _load_account_registry_entry(normalized_account)
    account_id = _require_registry_string(registry_entry, "account_id")
    storage = Path(_require_registry_string(registry_entry, "storage")).expanduser().resolve()

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
                        "provider": CODEX_PROVIDER,
                        "account": normalized_account,
                        "account_id": account_id,
                        "home": str(normalized_home),
                        "auth_path": str(auth_path),
                        "previous_home_account_id": existing_info.account_id,
                        "previous_home_auth_sha256": existing_info.sha256,
                    },
                )
                raise CliError(message)
            _store_snapshot(
                existing_info,
                account=normalized_account,
                storage=storage,
                source_home=normalized_home,
            )

        selected = _selected_snapshot(storage)
        destination = _copy_snapshot_to_home(Path(str(selected["path"])), auth_path)
        copied_info = read_codex_auth_info(destination)
        payload = {
            "provider": CODEX_PROVIDER,
            "account": normalized_account,
            "account_id": account_id,
            "email": registry_entry.get("email"),
            "home": str(normalized_home),
            "auth_path": str(auth_path),
            "source_snapshot": selected["path"],
            "source_sha256": selected["sha256"],
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
            "source_snapshot": selected,
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
                payload={
                    "provider": CODEX_PROVIDER,
                    "account": normalized_account,
                    "home": str(normalized_home),
                    "auth_path": str(auth_path),
                    "message": str(exc),
                },
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

    matches = _registry_entries_for_account_id(info.account_id)
    snapshot_match = _snapshot_for_sha(info.sha256, matches)
    base["auth"] = info.safe_payload()
    base["registry_matches"] = matches
    base["registered_snapshot"] = snapshot_match

    if path_kind == "symlink":
        base["classification"] = "legacy-symlink"
        base["symlink_target"] = str(_read_symlink_target(auth_path))
    elif snapshot_match is not None:
        base["classification"] = "registered"
    elif matches:
        base["classification"] = "unregistered-known-account"
    else:
        base["classification"] = "unregistered-unknown-account"

    latest_payload = latest_link.get("payload") if isinstance(latest_link, dict) else None
    if isinstance(latest_payload, dict):
        latest_account_id = latest_payload.get("account_id")
        if isinstance(latest_account_id, str) and latest_account_id != info.account_id:
            base["classification"] = "different-account"
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


def _store_snapshot(
    info: CodexAuthInfo,
    *,
    account: str,
    storage: Path,
    source_home: Path,
) -> dict[str, object]:
    snapshots_dir = storage / "snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = storage / "manifest.json"
    manifest = _load_manifest(manifest_path)
    filename = _snapshot_filename(info)
    snapshot_path = snapshots_dir / filename
    if not snapshot_path.exists():
        shutil.copy2(info.path, snapshot_path)

    snapshot_record = {
        "sha256": info.sha256,
        "path": str(snapshot_path),
        "account_id": info.account_id,
        "auth_mode": info.auth_mode,
        "email": info.email,
        "last_refresh": info.last_refresh,
        "jwt_iat": info.jwt_iat,
        "mtime": info.mtime,
        "source_home": str(source_home),
        "registered_at": utc_now_iso(),
    }
    snapshots = [
        item
        for item in manifest.get("snapshots", [])
        if isinstance(item, dict) and item.get("sha256") != info.sha256
    ]
    snapshots.append(snapshot_record)
    snapshots.sort(key=_snapshot_sort_key, reverse=True)
    selected = snapshots[0]
    manifest.update(
        {
            "schema_version": 1,
            "provider": CODEX_PROVIDER,
            "account": account,
            "account_id": info.account_id,
            "email": info.email,
            "selected_sha256": selected["sha256"],
            "selected_snapshot": selected["path"],
            "updated_at": utc_now_iso(),
            "snapshots": snapshots,
        }
    )
    _write_json_file(manifest_path, manifest)
    return snapshot_record


def _selected_snapshot(storage: Path) -> dict[str, object]:
    manifest = _load_manifest(storage / "manifest.json")
    snapshots = [item for item in manifest.get("snapshots", []) if isinstance(item, dict)]
    if not snapshots:
        raise CliError(f"codex account has no registered auth snapshots: {storage}")
    snapshots.sort(key=_snapshot_sort_key, reverse=True)
    selected = snapshots[0]
    path = _string_or_none(selected.get("path"))
    if path is None:
        raise CliError(f"codex account selected snapshot path is missing: {storage}")
    snapshot_path = Path(path).expanduser().resolve()
    if not snapshot_path.is_file():
        raise CliError(f"codex account selected snapshot does not exist: {snapshot_path}")
    return {**selected, "path": str(snapshot_path)}


def _copy_snapshot_to_home(snapshot_path: Path, auth_path: Path) -> Path:
    auth_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = auth_path.parent / f".{auth_path.name}.agentos-tmp-{os.getpid()}"
    if temp_path.exists() or temp_path.is_symlink():
        temp_path.unlink()
    try:
        shutil.copy2(snapshot_path, temp_path)
        os.replace(temp_path, auth_path)
    finally:
        if temp_path.exists() or temp_path.is_symlink():
            temp_path.unlink()
    return auth_path


def _load_account_registry_entry(account: str) -> dict[str, object]:
    registry = _load_account_registry()
    entry = registry.get(_registry_key(account))
    if not isinstance(entry, dict):
        raise CliError(f"agent account is not registered: codex.{account}")
    return entry


def _upsert_account_registry_entry(
    *,
    account: str,
    info: CodexAuthInfo,
    storage: Path,
) -> dict[str, object]:
    config_path = global_config_path(agentos_home_dir())
    config = _load_or_create_global_config(config_path)
    agent = config.get("agent")
    if agent is None:
        agent = {}
        config["agent"] = agent
    if not isinstance(agent, dict):
        raise CliError("global config field agent must be a JSON object")
    registry = agent.get("account_registry")
    if registry is None:
        registry = {}
        agent["account_registry"] = registry
    if not isinstance(registry, dict):
        raise CliError("global config field agent.account_registry must be a JSON object")

    entry = {
        "provider": CODEX_PROVIDER,
        "account": account,
        "account_id": info.account_id,
        "storage": str(storage),
    }
    if info.email is not None:
        entry["email"] = info.email
    registry[_registry_key(account)] = entry
    _write_json_file(config_path, config)
    return entry


def _load_account_registry() -> dict[str, dict[str, object]]:
    config_path = global_config_path(agentos_home_dir())
    if not config_path.exists():
        return {}
    config = load_global_config(config_path)
    current: object = config
    for part in ACCOUNT_REGISTRY_PATH:
        if not isinstance(current, dict):
            raise CliError(f"global config field {'.'.join(ACCOUNT_REGISTRY_PATH)} must be a JSON object")
        current = current.get(part)
        if current is None:
            return {}
    if not isinstance(current, dict):
        raise CliError("global config field agent.account_registry must be a JSON object")
    return {key: value for key, value in current.items() if isinstance(value, dict)}


def _registry_entries_for_account_id(account_id: str) -> list[dict[str, object]]:
    matches: list[dict[str, object]] = []
    for key, entry in sorted(_load_account_registry().items()):
        if entry.get("provider") == CODEX_PROVIDER and entry.get("account_id") == account_id:
            matches.append({"key": key, **entry})
    return matches


def _snapshot_for_sha(sha256: str, registry_matches: list[dict[str, object]]) -> dict[str, object] | None:
    for entry in registry_matches:
        storage = entry.get("storage")
        if not isinstance(storage, str):
            continue
        manifest = _load_manifest(Path(storage).expanduser().resolve() / "manifest.json")
        for snapshot in manifest.get("snapshots", []):
            if isinstance(snapshot, dict) and snapshot.get("sha256") == sha256:
                return snapshot
    return None


def _load_or_create_global_config(config_path: Path) -> dict[str, object]:
    if config_path.exists():
        return load_global_config(config_path)
    return {"class": "agentos.global.config", "schema_version": 1}


def _load_manifest(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"schema_version": 1, "provider": CODEX_PROVIDER, "snapshots": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CliError(f"invalid codex account manifest JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise CliError(f"codex account manifest must be a JSON object: {path}")
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


def _home_auth_path(home: Path) -> Path:
    return home / CODEX_AUTH_FILENAME


def _account_storage_path(account: str) -> Path:
    return agentos_home_dir() / "accounts" / CODEX_PROVIDER / account


def _registry_key(account: str) -> str:
    return f"{CODEX_PROVIDER}.{account}"


def _require_registry_string(entry: dict[str, object], field: str) -> str:
    value = entry.get(field)
    if not isinstance(value, str) or not value.strip():
        raise CliError(f"registered codex account field {field} must be a non-empty string")
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


def _snapshot_filename(info: CodexAuthInfo) -> str:
    return f"{_snapshot_timetag(info)}-{info.sha256[:12]}.json"


def _snapshot_timetag(info: CodexAuthInfo) -> str:
    if info.last_refresh is not None:
        parsed = _parse_iso_datetime(info.last_refresh)
        if parsed is not None:
            return parsed.strftime("%Y%m%dT%H%M%SZ")
    if info.jwt_iat is not None:
        return datetime.datetime.fromtimestamp(info.jwt_iat, tz=datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return datetime.datetime.fromtimestamp(info.mtime, tz=datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _parse_iso_datetime(value: str) -> datetime.datetime | None:
    try:
        parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(datetime.timezone.utc)


def _snapshot_sort_key(snapshot: object) -> tuple[int, float, str]:
    if not isinstance(snapshot, dict):
        return (0, 0.0, "")
    last_refresh = _string_or_none(snapshot.get("last_refresh"))
    if last_refresh is not None:
        parsed = _parse_iso_datetime(last_refresh)
        if parsed is not None:
            return (3, parsed.timestamp(), str(snapshot.get("sha256", "")))
    jwt_iat = snapshot.get("jwt_iat")
    if isinstance(jwt_iat, int):
        return (2, float(jwt_iat), str(snapshot.get("sha256", "")))
    mtime = snapshot.get("mtime")
    if isinstance(mtime, (int, float)):
        return (1, float(mtime), str(snapshot.get("sha256", "")))
    return (0, 0.0, str(snapshot.get("sha256", "")))


def _path_kind(path: Path) -> str:
    if path.is_symlink():
        return "symlink"
    if path.is_file():
        return "file"
    if path.exists():
        return "other"
    return "missing"


def _read_symlink_target(path: Path) -> Path:
    raw_target = os.readlink(path)
    target = Path(raw_target)
    if target.is_absolute():
        return target
    return (path.parent / target).resolve()


__all__ = [
    "inspect_codex_account_home",
    "link_codex_account_to_home",
    "read_codex_auth_info",
    "register_codex_account_from_home",
]
