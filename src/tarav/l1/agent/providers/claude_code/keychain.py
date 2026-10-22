"""Claude secure-storage (Keychain / `.credentials.json`) read+write primitives.

Provider-specific *home secret access*, shared by the new model (`ClaudeAuthMethod`)
and the kept usage/status system (`claude/account_status.py`). Carries no
credential-registry logic, so it is independent of the old account machinery.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tarav.l0._core.errors import CliError
from tarav.l0._core.process import run_process

CLAUDE_CREDENTIALS_SERVICE_SUFFIX = "-credentials"
DEFAULT_CLAUDE_KEYCHAIN_TIMEOUT_SEC = 5


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


def claude_keychain_service_names(home: Path) -> tuple[str, ...]:
    """The Keychain services scoped to THIS home — home-specific only.

    The cross-home generic ``Claude Code-credentials`` service is deliberately
    excluded: we never write it, so reading it can only return a credential
    belonging to some other home. A home without its own entry must read as
    absent rather than borrowing.
    """

    normalized_home = home.expanduser().resolve()
    home_hash = hashlib.sha256(str(normalized_home).encode("utf-8")).hexdigest()[:8]
    return (f"Claude Code{CLAUDE_CREDENTIALS_SERVICE_SUFFIX}-{home_hash}",)


def _read_claude_keychain_storage(home: Path) -> tuple[str, dict[str, Any]] | None:
    for service_name in claude_keychain_service_names(home):
        result = run_process(
            (
                "security", "find-generic-password",
                "-a", os.environ.get("USER", ""),
                "-s", service_name, "-w",
            ),
            mode="capture",
            timeout_sec=DEFAULT_CLAUDE_KEYCHAIN_TIMEOUT_SEC,
        )
        if result.exit_code != 0:
            continue
        try:
            payload = json.loads(result.stdout or "")
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return service_name, payload
    return None


def read_claude_secure_storage(home: Path) -> dict[str, Any]:
    return read_claude_secure_storage_info(home).payload


def read_claude_secure_storage_info(home: Path) -> ClaudeSecureStorageInfo:
    normalized_home = home.expanduser().resolve()
    if sys.platform == "darwin":
        keychain_data = _read_claude_keychain_storage(normalized_home)
        if keychain_data is not None:
            service_name, payload = keychain_data
            return ClaudeSecureStorageInfo(
                home=normalized_home, payload=payload,
                storage_kind="macos-keychain", keychain_service=service_name,
            )
    credentials_path = normalized_home / ".credentials.json"
    if credentials_path.is_file():
        try:
            payload = json.loads(credentials_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CliError(f"invalid claude-code credentials file: {credentials_path}") from exc
        if isinstance(payload, dict):
            return ClaudeSecureStorageInfo(
                home=normalized_home, payload=payload,
                storage_kind="credentials-json", credentials_path=credentials_path,
            )
        raise CliError(f"claude-code credentials file must be an object: {credentials_path}")
    raise CliError(f"claude-code OAuth secure storage was not found for home: {normalized_home}")


def write_claude_secure_storage(*, home: Path, payload: dict[str, Any]) -> ClaudeSecureStorageInfo:
    if not isinstance(payload, dict):
        raise CliError("claude-code secure storage payload must be an object")
    normalized_home = home.expanduser().resolve()
    normalized_home.mkdir(parents=True, exist_ok=True)
    if sys.platform == "darwin":
        service_name = claude_keychain_service_names(normalized_home)[0]
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        result = run_process(
            (
                "security", "add-generic-password", "-U",
                "-a", os.environ.get("USER", ""),
                "-s", service_name, "-w", raw,
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
            home=normalized_home, payload=payload,
            storage_kind="macos-keychain", keychain_service=service_name,
        )
    credentials_path = normalized_home / ".credentials.json"
    write_json_file_atomic(credentials_path, payload, mode=0o600)
    return ClaudeSecureStorageInfo(
        home=normalized_home, payload=payload,
        storage_kind="credentials-json", credentials_path=credentials_path,
    )


def write_json_file_atomic(path: Path, payload: dict[str, Any], *, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.parent / f".{path.name}.tarav-tmp-{os.getpid()}"
    if temp_path.exists() or temp_path.is_symlink():
        temp_path.unlink()
    try:
        temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if mode is not None:
            temp_path.chmod(mode)
        os.replace(temp_path, path)
    finally:
        if temp_path.exists() or temp_path.is_symlink():
            temp_path.unlink()


__all__ = [
    "CLAUDE_CREDENTIALS_SERVICE_SUFFIX",
    "DEFAULT_CLAUDE_KEYCHAIN_TIMEOUT_SEC",
    "ClaudeSecureStorageInfo",
    "claude_keychain_service_names",
    "read_claude_secure_storage",
    "read_claude_secure_storage_info",
    "write_claude_secure_storage",
    "write_json_file_atomic",
]
