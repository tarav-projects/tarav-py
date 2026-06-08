from __future__ import annotations

import hashlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from agentos._core.errors import CliError
from agentos._core.path_validation import validate_string_for_path
from agentos.agent.account_registry import (
    account_exists,
    append_artifact,
    artifacts_dir,
    load_account,
    record_account_event,
    upsert_account,
)

CLAUDE_PROVIDER = "claude-code"
CLAUDE_AUTH_KIND = "ambient-browser-login"
CLAUDE_OAUTH_TOKEN_AUTH_KIND = "oauth-token-env"


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
    if token_info is None:
        auth_kinds = _merged_auth_kinds(existing, CLAUDE_AUTH_KIND)
        updates: dict[str, object] = {
            "auth_kinds": auth_kinds,
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
        auth_kinds = _merged_auth_kinds(
            existing,
            CLAUDE_AUTH_KIND,
            CLAUDE_OAUTH_TOKEN_AUTH_KIND,
        )
        updates = {
            "auth_kinds": auth_kinds,
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
            "auth_kinds": auth_kinds,
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


def link_claude_account_to_home(
    *,
    account: str,
    home: Path | None = None,
    force: bool = False,
    argv: list[str] | tuple[str, ...] = (),
) -> dict[str, object]:
    normalized_account = validate_string_for_path(account, field_name="account")
    account_record = load_account(CLAUDE_PROVIDER, normalized_account)
    auth_kinds = account_record.get("auth_kinds")
    if not isinstance(auth_kinds, list) or CLAUDE_AUTH_KIND not in auth_kinds:
        raise CliError(f"agent accounts link is not supported for provider {CLAUDE_PROVIDER} account {normalized_account}")
    normalized_home = home.expanduser().resolve() if home is not None else None
    event_payload: dict[str, object] = {
        "provider": CLAUDE_PROVIDER,
        "account": normalized_account,
        "kind": "claimed",
        "force": force,
    }
    if normalized_home is not None:
        event_payload["home"] = str(normalized_home)
    record_account_event(
        event_type="agent.accounts.link",
        command="agent accounts link",
        argv=argv,
        status="ok",
        payload=event_payload,
    )
    payload: dict[str, object] = {
        "status": "ok",
        "command": "agent accounts link",
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
    auth_kinds = account_record.get("auth_kinds")
    return isinstance(auth_kinds, list) and CLAUDE_OAUTH_TOKEN_AUTH_KIND in auth_kinds


def load_claude_oauth_token_for_account(
    account: str,
) -> ClaudeOAuthTokenMaterialization:
    normalized_account = validate_string_for_path(account, field_name="account")
    account_record = load_account(CLAUDE_PROVIDER, normalized_account)
    auth_kinds = account_record.get("auth_kinds")
    if (
        not isinstance(auth_kinds, list)
        or CLAUDE_OAUTH_TOKEN_AUTH_KIND not in auth_kinds
    ):
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


def _load_account_or_none(account: str) -> dict[str, object] | None:
    if not account_exists(CLAUDE_PROVIDER, account):
        return None
    return load_account(CLAUDE_PROVIDER, account)


def _merged_auth_kinds(
    existing: dict[str, object] | None,
    *auth_kinds: str,
) -> list[str]:
    merged: list[str] = []
    existing_kinds = existing.get("auth_kinds") if existing is not None else None
    if isinstance(existing_kinds, list):
        for item in existing_kinds:
            if isinstance(item, str) and item not in merged:
                merged.append(item)
    for item in auth_kinds:
        if item not in merged:
            merged.append(item)
    return merged


def _provider_root() -> Path:
    from agentos.agent.account_registry import account_provider_root

    return account_provider_root(CLAUDE_PROVIDER)


def _artifact_path(artifact_id: str) -> Path:
    return artifacts_dir(CLAUDE_PROVIDER) / f"{artifact_id}.oauth-token"


def _artifact_relative_file(artifact_id: str) -> str:
    return f"artifacts/{artifact_id}.oauth-token"


def _require_account_string(account: dict[str, object], field: str) -> str:
    value = account.get(field)
    if not isinstance(value, str) or not value.strip():
        raise CliError(f"claude-code account field {field} must be a non-empty string")
    return value.strip()


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


__all__ = [
    "CLAUDE_OAUTH_TOKEN_AUTH_KIND",
    "ClaudeOAuthTokenMaterialization",
    "link_claude_account_to_home",
    "load_claude_oauth_token_for_account",
    "read_claude_oauth_token_info",
    "register_claude_account",
]
