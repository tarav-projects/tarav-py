from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any


def write_text_file(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def seed_account(
    provider: str, account: str, *, identity: dict[str, Any], method: str, auth_class: str
) -> None:
    """Declare an account in the new-model settings `accounts.json` (test setup)."""
    from agentos._core.project import agentos_home_dir

    prov = agentos_home_dir() / "accounts" / provider
    prov.mkdir(parents=True, exist_ok=True)
    path = prov / "accounts.json"
    data = json.loads(path.read_text()) if path.exists() else {"provider": provider, "accounts": {}}
    data["accounts"][account] = {"identity": identity, "auth_methods": {method: {"class": auth_class}}}
    path.write_text(json.dumps(data), encoding="utf-8")


def seed_codex_account(account: str, *, account_id: str = "acc_123") -> None:
    seed_account("codex", account, identity={"provider_account_id": account_id},
                 method="file", auth_class="auth-json")


def seed_claude_account(account: str, *, account_uuid: str = "acc_uuid", email: str = "x@e.com") -> None:
    seed_account("claude-code", account, identity={"account_uuid": account_uuid, "email": email},
                 method="browser", auth_class="ambient-browser-login")


def seed_copilot_account(account: str, *, login: str = "josePereiro") -> None:
    seed_account("copilot-cli", account, identity={"provider_account_id": login},
                 method="gh-token", auth_class="gh-auth-token")


def read_json_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl_file(path: Path) -> list[Any]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


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
    write_text_file(
        home / ".claude.json",
        json.dumps(
            {
                "oauthAccount": {
                    "accountUuid": account_uuid,
                    "emailAddress": email,
                    "displayName": "Browser BR",
                    "organizationUuid": "org_br",
                }
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    write_text_file(
        home / ".credentials.json",
        json.dumps(
            {
                "claudeAiOauth": {
                    "accessToken": access_token,
                    "refreshToken": refresh_token,
                }
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )


def captured_json(capsys: object) -> dict[str, Any]:
    return json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]
