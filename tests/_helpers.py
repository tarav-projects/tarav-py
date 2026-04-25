from __future__ import annotations

import json
from pathlib import Path


def write_text_file(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


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


def set_fake_agentos_home(monkeypatch: object, root: Path) -> Path:
    agentos_home = root / ".agentos"
    agentos_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("AGENTOS_HOME", str(agentos_home))  # type: ignore[attr-defined]
    return agentos_home
