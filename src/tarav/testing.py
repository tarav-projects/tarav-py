# $kw: --from RED.GREEN.Test.Suite
"""Construct valid isolated Tarav state for tests in any Python package.

Use ``TaravTestEnvironment`` for normal state. Use ``write_raw_json`` only
when a test intentionally needs malformed state.
"""

from __future__ import annotations

import base64
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
import json
from pathlib import Path
from uuid import UUID


DEFAULT_TEST_PROJECT_ID = "00000000-0000-4000-8000-000000000001"


def _reject_reserved_fields(
    values: Mapping[str, object],
    *,
    reserved: set[str],
) -> None:
    found = sorted(reserved.intersection(values))
    if found:
        raise ValueError(
            f"reserved Tarav test-state fields cannot be overridden: {', '.join(found)}"
        )


def _require_profile_id(profile_id: str) -> None:
    if not profile_id or Path(profile_id).name != profile_id:
        raise ValueError("test profile id must be a non-empty filename")


def write_raw_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def write_project_marker(
    project_root: Path,
    *,
    project_id: str = DEFAULT_TEST_PROJECT_ID,
    project_name: str | None = None,
) -> Path:
    UUID(project_id)
    payload: dict[str, object] = {
        "class": "agentos.project",
        "schema_version": 1,
        "project_id": project_id,
    }
    if project_name is not None:
        payload["project_name"] = project_name
    return write_raw_json(project_root / ".tarav" / "project.json", payload)


def write_project_config(project_root: Path, **sections: object) -> Path:
    _reject_reserved_fields(sections, reserved={"class", "schema_version"})
    return write_raw_json(
        project_root / ".tarav" / "config.json",
        {
            "class": "agentos.project.config",
            "schema_version": 1,
            **sections,
        },
    )


@dataclass(frozen=True)
class TaravTestEnvironment:
    root: Path
    home: Path
    tarav_home: Path

    @classmethod
    def create(cls, root: Path) -> "TaravTestEnvironment":
        resolved_root = root.resolve()
        home = resolved_root / "home"
        tarav_home = resolved_root / "agentos-home"
        home.mkdir(parents=True, exist_ok=True)
        tarav_home.mkdir(parents=True, exist_ok=True)
        return cls(root=resolved_root, home=home, tarav_home=tarav_home)

    def environment_variables(self) -> dict[str, str]:
        return {
            "HOME": str(self.home),
            "TARAV_HOME": str(self.tarav_home),
        }

    def apply_environment(self, setenv: Callable[[str, str], object]) -> None:
        for name, value in self.environment_variables().items():
            setenv(name, value)

    def write_global_config(self, **sections: object) -> Path:
        _reject_reserved_fields(sections, reserved={"class", "schema_version"})
        return write_raw_json(
            self.tarav_home / "config.json",
            {
                "class": "agentos.global.config",
                "schema_version": 1,
                **sections,
            },
        )

    def write_profile(
        self,
        profile_id: str,
        *,
        provider: str,
        **fields: object,
    ) -> Path:
        _require_profile_id(profile_id)
        _reject_reserved_fields(fields, reserved={"schema_version", "id", "provider"})
        return write_raw_json(
            self.tarav_home / "profiles" / f"{profile_id}.json",
            {
                "schema_version": 1,
                "id": profile_id,
                "provider": provider,
                **fields,
            },
        )

    def write_profiles(self, profiles: Iterable[Mapping[str, object]]) -> list[Path]:
        paths: list[Path] = []
        for profile in profiles:
            profile_id = profile.get("id")
            provider = profile.get("provider")
            if not isinstance(profile_id, str) or not isinstance(provider, str):
                raise ValueError("test profiles require string id and provider fields")
            fields = {
                name: value
                for name, value in profile.items()
                if name not in {"id", "provider"}
            }
            paths.append(self.write_profile(profile_id, provider=provider, **fields))
        return paths

    def write_project_marker(
        self,
        project_root: Path,
        *,
        project_id: str = DEFAULT_TEST_PROJECT_ID,
        project_name: str | None = None,
    ) -> Path:
        return write_project_marker(
            project_root,
            project_id=project_id,
            project_name=project_name,
        )

    def write_project_config(
        self,
        project_root: Path,
        **sections: object,
    ) -> Path:
        return write_project_config(project_root, **sections)


def seed_account(
    provider: str,
    account: str,
    *,
    identity: Mapping[str, object],
    method: str,
    auth_class: str,
) -> None:
    """Declare an account in the new-model settings ``accounts.json``."""
    from tarav.l0._core.project import tarav_home_dir

    provider_root = tarav_home_dir() / "accounts" / provider
    provider_root.mkdir(parents=True, exist_ok=True)
    path = provider_root / "accounts.json"
    data = (
        json.loads(path.read_text())
        if path.exists()
        else {"provider": provider, "accounts": {}}
    )
    data["accounts"][account] = {
        "identity": dict(identity),
        "auth_methods": {method: {"class": auth_class}},
    }
    path.write_text(json.dumps(data), encoding="utf-8")


def seed_codex_account(account: str, *, account_id: str = "acc_123") -> None:
    seed_account(
        "codex",
        account,
        identity={"provider_account_id": account_id},
        method="file",
        auth_class="auth-json",
    )


def seed_claude_account(
    account: str, *, account_uuid: str = "acc_uuid", email: str = "x@e.com"
) -> None:
    seed_account(
        "claude-code",
        account,
        identity={"account_uuid": account_uuid, "email": email},
        method="browser",
        auth_class="ambient-browser-login",
    )


def seed_copilot_account(account: str, *, login: str = "josePereiro") -> None:
    seed_account(
        "copilot-cli",
        account,
        identity={"provider_account_id": login},
        method="gh-token",
        auth_class="gh-auth-token",
    )


def _jwt(payload: dict[str, object]) -> str:
    raw_header = json.dumps({"alg": "none"}, separators=(",", ":")).encode("utf-8")
    raw_payload = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return ".".join(
        [
            base64.urlsafe_b64encode(raw_header).decode("ascii").rstrip("="),
            base64.urlsafe_b64encode(raw_payload).decode("ascii").rstrip("="),
            "signature",
        ]
    )


def codex_auth_json(
    *, account_id: str = "acc_123", email: str = "person@example.com"
) -> str:
    return (
        json.dumps(
            {
                "auth_mode": "chatgpt",
                "OPENAI_API_KEY": None,
                "tokens": {
                    "id_token": _jwt({"email": email, "iat": 1_776_000_000}),
                    "access_token": _jwt({"iat": 1_776_000_000}),
                    "refresh_token": "secret-refresh-token",
                    "account_id": account_id,
                },
                "last_refresh": "2026-05-12T17:00:07Z",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def write_claude_home(
    home: Path,
    *,
    email: str,
    account_uuid: str,
    access_token: str = "secret-access",
    refresh_token: str = "secret-refresh",
) -> None:
    write_raw_json(
        home / ".claude.json",
        {
            "oauthAccount": {
                "accountUuid": account_uuid,
                "emailAddress": email,
                "displayName": "Browser BR",
                "organizationUuid": "org_br",
            }
        },
    )
    write_raw_json(
        home / ".credentials.json",
        {
            "claudeAiOauth": {
                "accessToken": access_token,
                "refreshToken": refresh_token,
            }
        },
    )


__all__ = [
    "TaravTestEnvironment",
    "DEFAULT_TEST_PROJECT_ID",
    "codex_auth_json",
    "seed_account",
    "seed_claude_account",
    "seed_codex_account",
    "seed_copilot_account",
    "write_claude_home",
    "write_project_config",
    "write_project_marker",
    "write_raw_json",
]
