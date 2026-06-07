"""Construct valid isolated Agentos state for tests in any Python package.

Use ``AgentosTestEnvironment`` for normal state. Use ``write_raw_json`` only
when a test intentionally needs malformed state.
"""

from __future__ import annotations

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
            f"reserved Agentos test-state fields cannot be overridden: {', '.join(found)}"
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
    return write_raw_json(project_root / ".agentos" / "project.json", payload)


def write_project_config(project_root: Path, **sections: object) -> Path:
    _reject_reserved_fields(sections, reserved={"class", "schema_version"})
    return write_raw_json(
        project_root / ".agentos" / "config.json",
        {
            "class": "agentos.project.config",
            "schema_version": 1,
            **sections,
        },
    )


@dataclass(frozen=True)
class AgentosTestEnvironment:
    root: Path
    home: Path
    agentos_home: Path

    @classmethod
    def create(cls, root: Path) -> "AgentosTestEnvironment":
        resolved_root = root.resolve()
        home = resolved_root / "home"
        agentos_home = resolved_root / "agentos-home"
        home.mkdir(parents=True, exist_ok=True)
        agentos_home.mkdir(parents=True, exist_ok=True)
        return cls(root=resolved_root, home=home, agentos_home=agentos_home)

    def environment_variables(self) -> dict[str, str]:
        return {
            "HOME": str(self.home),
            "AGENTOS_HOME": str(self.agentos_home),
        }

    def apply_environment(self, setenv: Callable[[str, str], object]) -> None:
        for name, value in self.environment_variables().items():
            setenv(name, value)

    def write_global_config(self, **sections: object) -> Path:
        _reject_reserved_fields(sections, reserved={"class", "schema_version"})
        return write_raw_json(
            self.agentos_home / "config.json",
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
            self.agentos_home / "profiles" / f"{profile_id}.json",
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


__all__ = [
    "AgentosTestEnvironment",
    "DEFAULT_TEST_PROJECT_ID",
    "write_project_config",
    "write_project_marker",
    "write_raw_json",
]
