# $kw: --from Package.Skill
from __future__ import annotations

import os
from pathlib import Path


def resolve_package_root() -> Path:
    env_root = os.getenv("TARAV_PROJECT_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    return Path(__file__).resolve().parents[3]


def package_skills_dir() -> Path:
    return resolve_package_root() / "skills"


def list_package_skill_names() -> list[str]:
    root = package_skills_dir()
    if not root.exists():
        return []

    names: list[str] = []
    for child in root.iterdir():
        if child.is_dir() and not child.name.startswith("."):
            names.append(child.name)
    return sorted(names)
