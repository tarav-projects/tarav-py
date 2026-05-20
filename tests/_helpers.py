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


def write_project_marker(project_root: Path) -> None:
    write_text_file(
        project_root / ".agentos" / "project.json",
        json.dumps(
            {
                "class": "agentos.project",
                "schema_version": 1,
                "project_id": "00000000-0000-4000-8000-000000000001",
            }
        )
        + "\n",
    )


def write_global_routing_config(
    agentos_home: Path,
    *,
    sources: dict[str, dict[str, object]] | None = None,
    profiles: dict[str, dict[str, object]] | None = None,
    default_profile: str | None = None,
) -> None:
    routing_payload: dict[str, object] = {
        "sources": {} if sources is None else sources,
        "profiles": {} if profiles is None else profiles,
    }
    if default_profile is not None:
        routing_payload["default_profile"] = default_profile

    write_text_file(
        agentos_home / "config.json",
        json.dumps(
            {
                "class": "agentos.global.config",
                "schema_version": 1,
                "skills": {"routing": routing_payload},
            },
            indent=2,
        )
        + "\n",
    )


def _build_agent_payload(
    *,
    provider_configs: dict[str, dict[str, object]] | None = None,
    provider_instances: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "instances": provider_instances or [],
    }
    if provider_configs is not None:
        payload["providers"] = provider_configs
    return payload


def write_global_config(
    path: Path,
    *,
    provider_configs: dict[str, dict[str, object]] | None = None,
    provider_instances: list[dict[str, object]] | None = None,
) -> None:
    write_text_file(
        path,
        json.dumps(
            {
                "class": "agentos.global.config",
                "schema_version": 1,
                "agent": _build_agent_payload(
                    provider_configs=provider_configs,
                    provider_instances=provider_instances,
                ),
            }
        ),
    )


def write_project_config(
    path: Path,
    *,
    provider_configs: dict[str, dict[str, object]] | None = None,
    provider_instances: list[dict[str, object]] | None = None,
) -> None:
    write_text_file(
        path,
        json.dumps(
            {
                "class": "agentos.project.config",
                "schema_version": 1,
                "agent": _build_agent_payload(
                    provider_configs=provider_configs,
                    provider_instances=provider_instances,
                ),
            }
        ),
    )


def set_fake_agentos_home(monkeypatch: object, root: Path) -> Path:
    agentos_home = root / ".agentos"
    agentos_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))  # type: ignore[attr-defined]
    return agentos_home


def isolate_agentos(monkeypatch: object, tmp_path: Path) -> tuple[Path, Path]:
    home = tmp_path / "home"
    agentos_home = tmp_path / "agentos-home"
    home.mkdir(parents=True, exist_ok=True)
    agentos_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(home))  # type: ignore[attr-defined]
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))  # type: ignore[attr-defined]
    return home, agentos_home


def captured_json(capsys: object) -> dict[str, Any]:
    return json.loads(capsys.readouterr().out)  # type: ignore[attr-defined]
