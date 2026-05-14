from __future__ import annotations

import json
import os
from pathlib import Path

from agentos._core.clock import utc_now_iso
from agentos._core.errors import CliError
from agentos._core.path_validation import validate_string_for_path
from agentos._core.project import agentos_home_dir

ACCOUNT_MANIFEST_SCHEMA_VERSION = 1


def account_provider_root(provider: str) -> Path:
    return agentos_home_dir() / "accounts" / validate_string_for_path(provider, field_name="provider")


def account_dir(provider: str, account: str) -> Path:
    return account_provider_root(provider) / "accounts" / validate_string_for_path(account, field_name="account")


def account_manifest_path(provider: str, account: str) -> Path:
    return account_dir(provider, account) / "manifest.json"


def write_account_manifest(
    *,
    provider: str,
    account: str,
    auth_kind: str,
    capabilities: dict[str, bool],
    email: str | None = None,
    label: str | None = None,
    home: Path | None = None,
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    normalized_provider = validate_string_for_path(provider, field_name="provider")
    normalized_account = validate_string_for_path(account, field_name="account")
    path = account_manifest_path(normalized_provider, normalized_account)
    existing = _load_existing_manifest(path, provider=normalized_provider, account=normalized_account)
    now = utc_now_iso()
    manifest: dict[str, object] = {
        "schema_version": ACCOUNT_MANIFEST_SCHEMA_VERSION,
        "provider": normalized_provider,
        "account": normalized_account,
        "auth_kind": auth_kind,
        "capabilities": dict(sorted(capabilities.items())),
        "created_at": _manifest_string(existing, "created_at") or now,
        "updated_at": now,
    }
    for key, value in (
        ("label", _string_or_none(label)),
        ("email", _string_or_none(email)),
        ("home", str(home.expanduser().resolve()) if home is not None else None),
    ):
        if value is not None:
            manifest[key] = value
    if extra:
        manifest.update({key: value for key, value in extra.items() if value is not None})
    _write_json_file(path, manifest)
    return manifest


def load_account_manifest(provider: str, account: str) -> dict[str, object]:
    normalized_provider = validate_string_for_path(provider, field_name="provider")
    normalized_account = validate_string_for_path(account, field_name="account")
    path = account_manifest_path(normalized_provider, normalized_account)
    if not path.exists():
        raise CliError(f"agent account is not registered: {normalized_provider}.{normalized_account}")
    manifest = _load_json_object(path, description="agent account manifest")
    _validate_manifest_identity(manifest, path=path, provider=normalized_provider, account=normalized_account)
    return manifest


def list_account_manifests(provider: str | None = None) -> list[dict[str, object]]:
    providers = [validate_string_for_path(provider, field_name="provider")] if provider is not None else _registered_providers()
    manifests: list[dict[str, object]] = []
    for provider_name in providers:
        accounts_root = account_provider_root(provider_name) / "accounts"
        if not accounts_root.exists():
            continue
        for manifest_path in sorted(accounts_root.glob("*/manifest.json")):
            payload = _load_json_object(manifest_path, description="agent account manifest")
            account = _string_or_none(payload.get("account"))
            if account is None:
                raise CliError(f"agent account manifest field account must be a non-empty string: {manifest_path}")
            _validate_manifest_identity(payload, path=manifest_path, provider=provider_name, account=account)
            manifests.append(payload)
    return sorted(manifests, key=lambda item: (str(item.get("provider", "")), str(item.get("account", ""))))


def inspect_account_registry(provider: str | None = None) -> dict[str, object]:
    manifests = list_account_manifests(provider)
    providers = sorted({str(manifest["provider"]) for manifest in manifests})
    return {
        "status": "ok",
        "command": "agent accounts status",
        "provider": provider,
        "root": str(agentos_home_dir() / "accounts"),
        "provider_count": len(providers),
        "account_count": len(manifests),
        "providers": providers,
        "accounts": manifests,
    }


def _registered_providers() -> list[str]:
    root = agentos_home_dir() / "accounts"
    if not root.exists():
        return []
    return sorted(path.name for path in root.iterdir() if path.is_dir())


def _load_existing_manifest(path: Path, *, provider: str, account: str) -> dict[str, object] | None:
    if not path.exists():
        return None
    manifest = _load_json_object(path, description="agent account manifest")
    _validate_manifest_identity(manifest, path=path, provider=provider, account=account)
    return manifest


def _validate_manifest_identity(
    manifest: dict[str, object],
    *,
    path: Path,
    provider: str,
    account: str,
) -> None:
    if manifest.get("provider") != provider or manifest.get("account") != account:
        raise CliError(f"agent account manifest does not match path: {path}")


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


def _manifest_string(manifest: dict[str, object] | None, field: str) -> str | None:
    if manifest is None:
        return None
    return _string_or_none(manifest.get(field))


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


__all__ = [
    "account_dir",
    "account_manifest_path",
    "account_provider_root",
    "inspect_account_registry",
    "list_account_manifests",
    "load_account_manifest",
    "write_account_manifest",
]
