from __future__ import annotations

import os
from pathlib import Path


def resolve_project_root() -> Path:
    env_root = os.getenv("AGENTOS_PROJECT_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    return Path(__file__).resolve().parents[3]


def skills_dir() -> Path:
    return resolve_project_root() / "skills"


def list_skill_names() -> list[str]:
    root = skills_dir()
    if not root.exists():
        return []

    names: list[str] = []
    for child in root.iterdir():
        if child.is_dir() and not child.name.startswith("."):
            names.append(child.name)
    return sorted(names)
