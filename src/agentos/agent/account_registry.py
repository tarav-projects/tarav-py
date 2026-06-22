from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from agentos._core.clock import utc_now_iso
from agentos._core.errors import CliError
from agentos._core.path_validation import validate_string_for_path
from agentos._core.project import agentos_home_dir
from agentos.agent.session_utils import string_or_none

ACCOUNT_REGISTRY_SCHEMA_VERSION = 1


def account_registry_root() -> Path:
    return agentos_home_dir() / "accounts"


def account_archive_root() -> Path:
    return agentos_home_dir() / "archive"


def archive_account_registry(*, label: str | None = None) -> dict[str, object]:
    """Back up the whole account registry tree before destructive rebuild work.

    Append-only and idempotent: copies ``~/.agentos/accounts`` into
    ``~/.agentos/archive/accounts-<label>``. Never clobbers an existing
    archive and never mutates the source.
    """

    source = account_registry_root()
    archive_label = label or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = account_archive_root() / f"accounts-{archive_label}"
    if not source.exists():
        return {"status": "empty", "source": str(source), "destination": str(destination)}
    if destination.exists():
        return {"status": "exists", "source": str(source), "destination": str(destination)}
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination)
    return {"status": "archived", "source": str(source), "destination": str(destination)}


def account_provider_root(provider: str) -> Path:
    return account_registry_root() / validate_string_for_path(provider, field_name="provider")


def accounts_path(provider: str) -> Path:
    return account_provider_root(provider) / "accounts.json"


def artifacts_path(provider: str) -> Path:
    return account_provider_root(provider) / "artifacts.jsonl"


def verifications_path(provider: str) -> Path:
    return account_provider_root(provider) / "verifications.jsonl"


def artifacts_dir(provider: str) -> Path:
    return account_provider_root(provider) / "artifacts"


def account_events_root() -> Path:
    return agentos_home_dir() / "accounts" / "events"


def account_events_path(timestamp: str | None = None) -> Path:
    event_time = timestamp or utc_now_iso()
    normalized = event_time[:-1] + "+00:00" if event_time.endswith("Z") else event_time
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise CliError(f"invalid account event timestamp: {event_time}") from exc
    return account_events_root() / f"{parsed.strftime('%Y%m%d')}.jsonl"


def load_accounts(provider: str) -> dict[str, object]:
    normalized_provider = validate_string_for_path(provider, field_name="provider")
    path = accounts_path(normalized_provider)
    if not path.exists():
        return _empty_accounts(normalized_provider)
    payload = _load_json_object(path, description="account registry")
    if payload.get("provider") != normalized_provider:
        raise CliError(f"account registry provider does not match path: {path}")
    accounts = payload.get("accounts")
    if not isinstance(accounts, dict):
        raise CliError(f"account registry field accounts must be a JSON object: {path}")
    return payload


def load_account(provider: str, account: str) -> dict[str, object]:
    normalized_provider = validate_string_for_path(provider, field_name="provider")
    normalized_account = validate_string_for_path(account, field_name="account")
    registry = load_accounts(normalized_provider)
    accounts = registry["accounts"]
    if not isinstance(accounts, dict):
        raise CliError(f"account registry field accounts must be a JSON object: {accounts_path(normalized_provider)}")
    account_record = accounts.get(normalized_account)
    if not isinstance(account_record, dict):
        raise CliError(f"agent account is not registered: {normalized_provider}.{normalized_account}")
    _validate_account_record(account_record, provider=normalized_provider, account=normalized_account)
    return account_record


def account_exists(provider: str, account: str) -> bool:
    normalized_provider = validate_string_for_path(provider, field_name="provider")
    normalized_account = validate_string_for_path(account, field_name="account")
    registry = load_accounts(normalized_provider)
    accounts = registry["accounts"]
    if not isinstance(accounts, dict):
        return False
    return isinstance(accounts.get(normalized_account), dict)


def upsert_account(provider: str, account: str, updates: dict[str, object]) -> dict[str, object]:
    normalized_provider = validate_string_for_path(provider, field_name="provider")
    normalized_account = validate_string_for_path(account, field_name="account")
    registry = load_accounts(normalized_provider)
    accounts = registry["accounts"]
    if not isinstance(accounts, dict):
        raise CliError(f"account registry field accounts must be a JSON object: {accounts_path(normalized_provider)}")
    existing = accounts.get(normalized_account)
    if existing is not None and not isinstance(existing, dict):
        raise CliError(f"account registry entry must be a JSON object: {accounts_path(normalized_provider)}#{normalized_account}")
    now = utc_now_iso()
    record: dict[str, object] = {
        "provider": normalized_provider,
        "account": normalized_account,
        "created_at": string_or_none(existing.get("created_at")) if isinstance(existing, dict) else now,
        "updated_at": now,
    }
    if isinstance(existing, dict):
        record.update(existing)
        record["updated_at"] = now
    record.update(updates)
    record["provider"] = normalized_provider
    record["account"] = normalized_account
    accounts[normalized_account] = record
    write_accounts(normalized_provider, registry)
    return record


def write_accounts(provider: str, payload: dict[str, object]) -> None:
    normalized_provider = validate_string_for_path(provider, field_name="provider")
    payload["schema_version"] = ACCOUNT_REGISTRY_SCHEMA_VERSION
    payload["provider"] = normalized_provider
    if not isinstance(payload.get("accounts"), dict):
        payload["accounts"] = {}
    _write_json_file(accounts_path(normalized_provider), payload)


def read_artifacts(provider: str) -> list[dict[str, object]]:
    normalized_provider = validate_string_for_path(provider, field_name="provider")
    path = artifacts_path(normalized_provider)
    if not path.exists():
        return []
    entries: list[dict[str, object]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CliError(f"invalid artifact registry JSONL at {path}:{line_number}") from exc
        if not isinstance(payload, dict):
            raise CliError(f"artifact registry entry must be a JSON object: {path}:{line_number}")
        if payload.get("provider") != normalized_provider:
            raise CliError(f"artifact registry provider does not match path: {path}:{line_number}")
        entries.append(payload)
    return entries


def append_artifact(provider: str, entry: dict[str, object]) -> tuple[dict[str, object], bool]:
    normalized_provider = validate_string_for_path(provider, field_name="provider")
    artifact_id = _required_string(entry, "artifact_id")
    account = _required_string(entry, "account")
    for existing in read_artifacts(normalized_provider):
        if existing.get("artifact_id") == artifact_id and existing.get("account") == account:
            return existing, False
    path = artifacts_path(normalized_provider)
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized_entry = {
        "registered_at": utc_now_iso(),
        **entry,
        "provider": normalized_provider,
        "artifact_id": artifact_id,
        "account": account,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(normalized_entry, sort_keys=True, separators=(",", ":")) + "\n")
    return normalized_entry, True


def read_verifications(provider: str) -> list[dict[str, object]]:
    normalized_provider = validate_string_for_path(provider, field_name="provider")
    path = verifications_path(normalized_provider)
    if not path.exists():
        return []
    entries: list[dict[str, object]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CliError(f"invalid verification registry JSONL at {path}:{line_number}") from exc
        if not isinstance(payload, dict):
            raise CliError(f"verification registry entry must be a JSON object: {path}:{line_number}")
        if payload.get("provider") != normalized_provider:
            raise CliError(f"verification registry provider does not match path: {path}:{line_number}")
        _validate_verification_entry(payload)
        entries.append(payload)
    return entries


def append_verification(provider: str, entry: dict[str, object]) -> dict[str, object]:
    normalized_provider = validate_string_for_path(provider, field_name="provider")
    account = _required_string(entry, "account")
    artifact_id = _required_string(entry, "artifact_id")
    auth_kind = _required_string(entry, "auth_kind")
    source = _required_string(entry, "source")
    verified_at = string_or_none(entry.get("verified_at")) or utc_now_iso()
    normalized_entry = {
        "recorded_at": utc_now_iso(),
        **entry,
        "provider": normalized_provider,
        "account": account,
        "artifact_id": artifact_id,
        "auth_kind": auth_kind,
        "source": source,
        "verified_at": verified_at,
    }
    _validate_verification_entry(normalized_entry)
    path = verifications_path(normalized_provider)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(normalized_entry, sort_keys=True, separators=(",", ":")) + "\n")
    return normalized_entry


def inspect_account_registry(provider: str | None = None) -> dict[str, object]:
    providers = [validate_string_for_path(provider, field_name="provider")] if provider is not None else _registered_providers()
    accounts: list[dict[str, object]] = []
    artifact_count = 0
    provider_summaries: list[dict[str, object]] = []
    for provider_name in providers:
        account_payload = load_accounts(provider_name)
        provider_accounts = _account_records(account_payload)
        artifacts = read_artifacts(provider_name)
        verifications = read_verifications(provider_name)
        accounts.extend(provider_accounts)
        artifact_count += len(artifacts)
        provider_summaries.append(
            {
                "provider": provider_name,
                "root": str(account_provider_root(provider_name)),
                "account_count": len(provider_accounts),
                "artifact_count": len(artifacts),
                "verification_count": len(verifications),
                "accounts_path": str(accounts_path(provider_name)),
                "artifacts_path": str(artifacts_path(provider_name)),
                "verifications_path": str(verifications_path(provider_name)),
            }
        )
    return {
        "status": "ok",
        "command": "agent accounts status",
        "provider": provider,
        "root": str(agentos_home_dir() / "accounts"),
        "provider_count": len(providers),
        "account_count": len(accounts),
        "artifact_count": artifact_count,
        "providers": provider_summaries,
        "accounts": sorted(accounts, key=lambda item: (str(item.get("provider", "")), str(item.get("account", "")))),
    }


def record_account_event(
    *,
    event_type: str,
    command: str,
    argv: list[str] | tuple[str, ...],
    status: str,
    payload: dict[str, object],
) -> None:
    provider = _required_string(payload, "provider")
    event_time = utc_now_iso()
    event = {
        "time": event_time,
        "event": event_type,
        "provider": provider,
        "source": command,
        "argv": list(argv),
        "status": status,
        **_redacted_event_payload(payload),
    }
    path = account_events_path(event_time)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")


def _redacted_event_payload(payload: dict[str, object]) -> dict[str, object]:
    blocked = {"auth", "copied_auth", "target_before_materialization"}
    return {key: value for key, value in payload.items() if key not in blocked}


def _account_records(payload: dict[str, object]) -> list[dict[str, object]]:
    accounts = payload.get("accounts")
    if not isinstance(accounts, dict):
        return []
    records: list[dict[str, object]] = []
    for account, record in accounts.items():
        if not isinstance(account, str) or not isinstance(record, dict):
            continue
        records.append(record)
    return records


def _registered_providers() -> list[str]:
    root = agentos_home_dir() / "accounts"
    if not root.exists():
        return []
    return sorted(
        path.name
        for path in root.iterdir()
        if path.is_dir() and path.name != "events"
    )


def _validate_account_record(record: dict[str, object], *, provider: str, account: str) -> None:
    if record.get("provider") != provider or record.get("account") != account:
        raise CliError(f"account registry entry does not match account: {accounts_path(provider)}#{account}")
    auth_kind = record.get("auth_kind")
    if not isinstance(auth_kind, str) or not auth_kind:
        raise CliError(
            f"account registry entry missing auth_kind: {accounts_path(provider)}#{account}"
        )


def _empty_accounts(provider: str) -> dict[str, object]:
    return {
        "schema_version": ACCOUNT_REGISTRY_SCHEMA_VERSION,
        "provider": provider,
        "accounts": {},
    }


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


def _required_string(payload: dict[str, object], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise CliError(f"registry field {field} must be a non-empty string")
    return value.strip()


_SECRET_VERIFICATION_KEYS = {
    "auth",
    "secure_storage",
    "credentials",
    "credential",
    "access_token",
    "accessToken",
    "refresh_token",
    "refreshToken",
    "id_token",
    "idToken",
    "token",
}


def _validate_verification_entry(entry: dict[str, object]) -> None:
    for field in ("provider", "account", "artifact_id", "auth_kind", "source", "verified_at"):
        _required_string(entry, field)
    _reject_secret_verification_payload(entry)


def _reject_secret_verification_payload(value: object, *, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                continue
            if key in _SECRET_VERIFICATION_KEYS:
                raise CliError(f"verification entry contains secret-bearing field: {path}.{key}")
            _reject_secret_verification_payload(child, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_secret_verification_payload(child, path=f"{path}[{index}]")


__all__ = [
    "account_archive_root",
    "account_exists",
    "account_provider_root",
    "account_registry_root",
    "archive_account_registry",
    "account_events_path",
    "account_events_root",
    "accounts_path",
    "append_artifact",
    "append_verification",
    "artifacts_dir",
    "artifacts_path",
    "inspect_account_registry",
    "load_account",
    "load_accounts",
    "record_account_event",
    "read_artifacts",
    "read_verifications",
    "upsert_account",
    "verifications_path",
]
