from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

from agentos._core.errors import CliError
from agentos._core.project import (
    agentos_home_dir,
    find_agentos_project_root,
    global_config_path,
    load_global_config,
    load_project_config,
    project_config_path,
)


@dataclass(frozen=True)
class ProviderFamily:
    family: str


_CANONICAL_PROVIDER_FAMILIES = tuple(
    ProviderFamily(family=family_name)
    for family_name in (
        "agents",
        "claude-code",
        "codex",
        "copilot",
        "copilot-cli",
        "gemini-cli",
        "opencode",
        "openclaw",
    )
)
_CANONICAL_PROVIDER_FAMILIES_BY_NAME = {
    provider_family.family: provider_family
    for provider_family in _CANONICAL_PROVIDER_FAMILIES
}


def canonical_provider_families() -> tuple[ProviderFamily, ...]:
    return _CANONICAL_PROVIDER_FAMILIES


def canonical_provider_family_for_name(family_name: str) -> ProviderFamily | None:
    return _CANONICAL_PROVIDER_FAMILIES_BY_NAME.get(family_name)


def require_canonical_provider_family(family_name: str) -> ProviderFamily:
    provider_family = canonical_provider_family_for_name(family_name)
    if provider_family is None:
        raise ValueError(f"unknown provider family: {family_name}")
    return provider_family


@dataclass(frozen=True)
class ProviderInstanceConfigSource:
    object_path: tuple[str, ...]
    field_prefix: str


@dataclass(frozen=True)
class ProviderInstanceConfigEntry:
    field_prefix: str
    index: int
    raw_instance: dict[str, object]

    def item_path(self) -> str:
        return f"{self.field_prefix}[{self.index}]"

    def field_name(self, field: str) -> str:
        return f"{self.item_path()}.{field}"


def load_chat_config_documents(*, start_path: Path | str = ".") -> tuple[dict[str, object], ...]:
    configs: list[dict[str, object]] = []

    global_path = global_config_path(agentos_home_dir())
    if global_path.exists():
        configs.append(load_global_config(global_path))

    project_root = find_agentos_project_root(start_path)
    if project_root is not None:
        project_path = project_config_path(project_root)
        if project_path.exists():
            configs.append(load_project_config(project_path))

    return tuple(configs)


def provider_instance_config_entries_from_config(
    config: dict[str, object],
    *,
    source: ProviderInstanceConfigSource,
) -> tuple[ProviderInstanceConfigEntry, ...]:
    raw_instances = _config_value_at_object_path(config, object_path=source.object_path)
    if raw_instances is None:
        return ()
    if not isinstance(raw_instances, list):
        raise CliError(f"config field {'.'.join(source.object_path)} must be a JSON array")

    entries: list[ProviderInstanceConfigEntry] = []
    for index, raw_instance in enumerate(raw_instances):
        if not isinstance(raw_instance, dict):
            raise CliError(f"{source.field_prefix}[{index}] must be a JSON object")
        entries.append(
            ProviderInstanceConfigEntry(
                field_prefix=source.field_prefix,
                index=index,
                raw_instance=raw_instance,
            )
        )
    return tuple(entries)


def load_provider_instance_config_entries(
    *,
    start_path: Path | str = ".",
    sources: tuple[ProviderInstanceConfigSource, ...],
) -> tuple[ProviderInstanceConfigEntry, ...]:
    entries: list[ProviderInstanceConfigEntry] = []
    for config in load_chat_config_documents(start_path=start_path):
        for source in sources:
            entries.extend(
                provider_instance_config_entries_from_config(
                    config,
                    source=source,
                )
            )
    return tuple(entries)


def _config_value_at_object_path(config: dict[str, object], *, object_path: tuple[str, ...]) -> object | None:
    if not object_path:
        return config

    current: object = config
    current_path: list[str] = []
    for key in object_path[:-1]:
        current_path.append(key)
        if not isinstance(current, dict):
            raise CliError(f"config field {'.'.join(current_path)} must be a JSON object")
        next_value = current.get(key)
        if next_value is None:
            return None
        if not isinstance(next_value, dict):
            raise CliError(f"config field {'.'.join(current_path)} must be a JSON object")
        current = next_value

    if not isinstance(current, dict):
        raise CliError(f"config field {'.'.join(object_path[:-1])} must be a JSON object")
    return current.get(object_path[-1])


@dataclass(frozen=True)
class ProviderInstanceAnchor:
    role: str
    path: Path
    slot: str | None = None

    def identity_key(self) -> tuple[str, str | None, str]:
        return (self.role, self.slot, str(self.path))

    def summary(self) -> dict[str, str]:
        payload = {
            "role": self.role,
            "path": str(self.path),
        }
        if self.slot is not None:
            payload["slot"] = self.slot
        return payload


def _provider_instance_fingerprint(
    *,
    family: str,
    anchors: tuple[ProviderInstanceAnchor, ...],
) -> str:
    digest = hashlib.sha256()
    digest.update(family.encode("utf-8"))
    for anchor in anchors:
        digest.update(b"\0")
        digest.update(anchor.role.encode("utf-8"))
        digest.update(b"\0")
        digest.update((anchor.slot or "").encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(anchor.path).encode("utf-8"))
    return digest.hexdigest()


@dataclass(frozen=True)
class ProviderInstance:
    family: str
    instance_id: str | None = None
    label: str | None = None
    homes: tuple[tuple[str, Path], ...] = ()
    direct_targets: tuple[Path, ...] = ()
    grep_targets: tuple[Path, ...] = ()
    sqlite_db_paths: tuple[Path, ...] = ()
    cli_command: tuple[str, ...] = ()
    env: tuple[tuple[str, str], ...] = ()
    timeout_sec: int | None = None
    live_usage_refresh: bool | None = None
    usage_progression_limit: str | None = None
    includes: tuple[str, ...] = ()
    excludes: tuple[str, ...] = ()
    anchors: tuple[ProviderInstanceAnchor, ...] = ()
    is_default: bool = False

    def homes_map(self) -> dict[str, Path]:
        return {key: path for key, path in self.homes}

    @property
    def fingerprint(self) -> str:
        if self.anchors:
            return _provider_instance_fingerprint(
                family=self.family,
                anchors=self.anchors,
            )

        fallback_anchors = tuple(
            ProviderInstanceAnchor(role=f"direct_target_{index + 1}", path=path)
            for index, path in enumerate(self.direct_targets)
        ) + tuple(
            ProviderInstanceAnchor(role=f"sqlite_db_{index + 1}", path=path)
            for index, path in enumerate(self.sqlite_db_paths)
        )
        return _provider_instance_fingerprint(
            family=self.family,
            anchors=fallback_anchors,
        )

    def matches_fingerprint_prefix(self, fingerprint_prefix: str) -> bool:
        normalized_prefix = fingerprint_prefix.strip().lower()
        if not normalized_prefix:
            return False
        return self.fingerprint.startswith(normalized_prefix)

    def identity_key(self) -> tuple[object, ...]:
        if self.anchors:
            return (
                self.family,
                tuple(anchor.identity_key() for anchor in self.anchors),
            )
        return (
            self.family,
            self.instance_id,
            tuple((key, str(path)) for key, path in self.homes),
            tuple(str(path) for path in self.direct_targets),
            tuple(str(path) for path in self.grep_targets),
            tuple(str(path) for path in self.sqlite_db_paths),
            self.cli_command,
            self.env,
            self.timeout_sec,
            self.live_usage_refresh,
            self.usage_progression_limit,
            self.includes,
            self.excludes,
        )

    def summary(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "family": self.family,
            "fingerprint": self.fingerprint,
            "is_default": self.is_default,
        }
        if self.instance_id is not None:
            payload["instance_id"] = self.instance_id
        if self.label is not None:
            payload["label"] = self.label
        if self.anchors:
            payload["anchors"] = [anchor.summary() for anchor in self.anchors]
        if self.homes:
            payload["homes"] = {key: str(path) for key, path in self.homes}
        if self.direct_targets:
            payload["direct_targets"] = [str(path) for path in self.direct_targets]
        if self.grep_targets:
            payload["grep_targets"] = [str(path) for path in self.grep_targets]
        if self.sqlite_db_paths:
            payload["sqlite_db_paths"] = [str(path) for path in self.sqlite_db_paths]
        if self.cli_command:
            payload["cli_command"] = list(self.cli_command)
        if self.env:
            payload["env"] = {key: value for key, value in self.env}
        if self.timeout_sec is not None:
            payload["timeout_sec"] = self.timeout_sec
        if self.live_usage_refresh is not None:
            payload["live_usage_refresh"] = self.live_usage_refresh
        if self.usage_progression_limit is not None:
            payload["usage_progression_limit"] = self.usage_progression_limit
        if self.includes:
            payload["includes"] = list(self.includes)
        if self.excludes:
            payload["excludes"] = list(self.excludes)
        return payload

    def uri_component(self) -> str:
        return quote(self.fingerprint, safe="")


__all__ = [
    "canonical_provider_families",
    "canonical_provider_family_for_name",
    "load_chat_config_documents",
    "load_provider_instance_config_entries",
    "ProviderFamily",
    "ProviderInstanceConfigEntry",
    "ProviderInstanceConfigSource",
    "ProviderInstance",
    "ProviderInstanceAnchor",
    "provider_instance_config_entries_from_config",
    "require_canonical_provider_family",
]
