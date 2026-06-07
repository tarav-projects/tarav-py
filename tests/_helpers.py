from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any


def write_text_file(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


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


def register_codex_args(auth_file: Path, *, account: str = "br") -> list[str]:
    return [
        "agent",
        "accounts",
        "register",
        "--provider",
        "codex",
        "--account",
        account,
        "--auth-file",
        str(auth_file),
    ]


def captured_json(capsys: object) -> dict[str, Any]:
    return json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]
