from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from agentos._core.errors import CliError
from agentos._core.git_ops import run_git
from agentos._core.path_validation import validate_string_for_path
from agentos._core.project import (
    agentos_home_dir,
    find_agentos_project_root,
    global_config_path,
    load_global_config,
    load_project_config,
    project_config_path,
)

CHAT_ARCHIVE_DIRNAME = "chat-archive"
DEFAULT_ARCHIVE_COMMIT_PREFIX = "checkpoint"


@dataclass(frozen=True)
class ArchiveHomeSlot:
    key: str
    default_home: str


@dataclass(frozen=True)
class ArchiveFamily:
    family: str
    home_slots: tuple[ArchiveHomeSlot, ...]
    default_excludes: tuple[str, ...] = ()
    default_includes: tuple[str, ...] = ()

    def supported_home_keys(self) -> tuple[str, ...]:
        return tuple(slot.key for slot in self.home_slots)

    def default_instance(self) -> ArchiveInstance:
        return self.instance_from_homes(
            {slot.key: slot.default_home for slot in self.home_slots},
            index=None,
            is_default=True,
            instance_name="default",
            includes=(),
            excludes=(),
        )

    def instance_from_home(
        self,
        home: str,
        *,
        index: int | None,
        is_default: bool,
        instance_name: str | None,
        includes: tuple[str, ...],
        excludes: tuple[str, ...],
    ) -> ArchiveInstance:
        if len(self.home_slots) != 1:
            field_name = _archive_provider_instance_field_name(index=index, field="home")
            homes_field_name = _archive_provider_instance_field_name(index=index, field="homes")
            supported_keys = ", ".join(self.supported_home_keys())
            raise CliError(
                f"{field_name} is only supported for providers with a single home root; "
                f"use {homes_field_name} with keys: {supported_keys}"
            )
        slot = self.home_slots[0]
        return self.instance_from_homes(
            {slot.key: home},
            index=index,
            is_default=is_default,
            instance_name=instance_name,
            includes=includes,
            excludes=excludes,
        )

    def instance_from_homes(
        self,
        homes: dict[str, str],
        *,
        index: int | None,
        is_default: bool,
        instance_name: str | None,
        includes: tuple[str, ...],
        excludes: tuple[str, ...],
    ) -> ArchiveInstance:
        supported_slots = {slot.key: slot for slot in self.home_slots}
        unsupported_keys = sorted(key for key in homes if key not in supported_slots)
        homes_field_name = _archive_provider_instance_field_name(index=index, field="homes")
        if unsupported_keys:
            supported_keys = ", ".join(self.supported_home_keys())
            unsupported_text = ", ".join(unsupported_keys)
            raise CliError(
                f"{homes_field_name} contains unsupported keys for provider {self.family}: "
                f"{unsupported_text} (supported: {supported_keys})"
            )

        normalized_homes: list[tuple[str, Path]] = []
        for slot in self.home_slots:
            raw_home = homes.get(slot.key)
            if raw_home is None:
                continue
            normalized_home = Path(
                _normalize_archive_home(
                    raw_home,
                    field_name=f"{homes_field_name}.{slot.key}",
                )
            ).expanduser().resolve()
            normalized_homes.append((slot.key, normalized_home))

        if not normalized_homes:
            supported_keys = ", ".join(self.supported_home_keys())
            raise CliError(
                f"{homes_field_name} must include at least one supported home key: {supported_keys}"
            )

        resolved_instance_name: str | None = None
        if instance_name is not None:
            field_name = _archive_provider_instance_field_name(index=index, field="instance")
            resolved_instance_name = validate_string_for_path(instance_name, field_name=field_name)

        return ArchiveInstance(
            family=self.family,
            homes=tuple(normalized_homes),
            includes=_unique_strings(self.default_includes + includes),
            excludes=_unique_strings(self.default_excludes + excludes),
            instance_name=resolved_instance_name,
            is_default=is_default,
        )


@dataclass(frozen=True)
class ArchiveInstance:
    family: str
    homes: tuple[tuple[str, Path], ...]
    includes: tuple[str, ...] = ()
    excludes: tuple[str, ...] = ()
    instance_name: str | None = None
    is_default: bool = False

    def homes_map(self) -> dict[str, Path]:
        return {key: path for key, path in self.homes}

    @property
    def fingerprint(self) -> str:
        digest = hashlib.sha256()
        digest.update(self.family.encode("utf-8"))
        for key, path in self.homes:
            digest.update(b"\0")
            digest.update(key.encode("utf-8"))
            digest.update(b"\0")
            digest.update(str(path).encode("utf-8"))
        return digest.hexdigest()

    @property
    def resolved_instance_name(self) -> str:
        if self.instance_name is not None:
            return self.instance_name
        if self.is_default:
            return "default"
        return self.fingerprint[:12]

    def identity_key(self) -> tuple[object, ...]:
        return (
            self.family,
            tuple((key, str(path)) for key, path in self.homes),
        )

    def destination_root(self, archive_root: Path) -> Path:
        return archive_root / self.family / self.resolved_instance_name

    def summary(self, archive_root: Path) -> dict[str, Any]:
        return {
            "provider": self.family,
            "instance": self.resolved_instance_name,
            "is_default": self.is_default,
            "homes": {key: str(path) for key, path in self.homes},
            "includes": list(self.includes),
            "excludes": list(self.excludes),
            "destination_root": str(self.destination_root(archive_root)),
        }


@dataclass(frozen=True)
class ArchiveSettings:
    commit_prefix: str
    provider_instances: tuple[ArchiveInstance, ...]


def default_chat_archive_root() -> Path:
    return agentos_home_dir() / CHAT_ARCHIVE_DIRNAME


def supported_archive_provider_families() -> tuple[ArchiveFamily, ...]:
    return (
        ArchiveFamily(
            family="claude-code",
            home_slots=(ArchiveHomeSlot(key="home", default_home="~/.claude"),),
            default_excludes=(
                "debug/",
                "telemetry/",
                "cache/",
                "statsig/",
                "shell-snapshots/",
                "paste-cache/",
                "session-env/",
                "downloads/",
                "ide/",
                "plugins/",
                "skills",
            ),
        ),
        ArchiveFamily(
            family="copilot-cli",
            home_slots=(ArchiveHomeSlot(key="home", default_home="~/.copilot"),),
            default_excludes=(
                "pkg/",
                "logs/",
                "ide/",
            ),
        ),
        ArchiveFamily(
            family="codex",
            home_slots=(ArchiveHomeSlot(key="home", default_home="~/.codex"),),
            default_excludes=(
                "log/",
                "vendor_imports/",
                "worktrees/",
                "shell_snapshots/",
                "models_cache.json",
                "sqlite/",
                "tmp/",
                "auth.json",
                "skills",
            ),
        ),
        ArchiveFamily(
            family="gemini-cli",
            home_slots=(ArchiveHomeSlot(key="home", default_home="~/.gemini"),),
            default_excludes=(
                "tmp/bin/",
                "oauth_creds.json",
                "google_accounts.json",
            ),
        ),
        ArchiveFamily(
            family="agents",
            home_slots=(ArchiveHomeSlot(key="home", default_home="~/.agents"),),
        ),
        ArchiveFamily(
            family="openclaw",
            home_slots=(ArchiveHomeSlot(key="home", default_home="~/.openclaw"),),
            default_excludes=("agents/*/agent/auth*.json",),
            default_includes=(
                "agents/*/sessions/**",
                "agents/*/agent/*.md",
                "agents/*/agent/*.json",
                "agents/*/agent/*.toml",
                "agents/*/agent/*.yaml",
                "agents/*/agent/*.yml",
                "agents/*/agent/*.ini",
                "workspace/AGENTS.md",
                "workspace/BOOTSTRAP.md",
                "workspace/HEARTBEAT.md",
                "workspace/IDENTITY.md",
                "workspace/SOUL.md",
                "workspace/TOOLS.md",
                "workspace/USER.md",
                "cron/jobs.json",
            ),
        ),
    )


def configured_archive_settings(*, start_path: Path | str = ".") -> ArchiveSettings:
    commit_prefix = DEFAULT_ARCHIVE_COMMIT_PREFIX
    provider_instances = [family.default_instance() for family in supported_archive_provider_families()]

    configs: list[dict[str, object]] = []
    global_path = global_config_path(agentos_home_dir())
    if global_path.exists():
        configs.append(load_global_config(global_path))

    project_root = find_agentos_project_root(start_path)
    if project_root is not None:
        project_path = project_config_path(project_root)
        if project_path.exists():
            configs.append(load_project_config(project_path))

    for config in configs:
        archive_config = _archive_config_from_config(config)
        if archive_config is None:
            continue
        raw_commit_prefix = archive_config.get("commit_prefix")
        if raw_commit_prefix is not None:
            if not isinstance(raw_commit_prefix, str) or not raw_commit_prefix.strip():
                raise CliError("config field chat.archive.commit_prefix must be a non-empty string")
            commit_prefix = raw_commit_prefix.strip()
        provider_instances.extend(_archive_instances_from_config(archive_config))

    deduped_instances = _dedupe_archive_instances(tuple(provider_instances))
    _validate_unique_archive_destinations(deduped_instances)
    return ArchiveSettings(
        commit_prefix=commit_prefix,
        provider_instances=deduped_instances,
    )


def archive_chat_instances(
    *,
    providers: tuple[str, ...] | None = None,
    archive_root: Path | None = None,
    start_path: Path | str = ".",
) -> dict[str, object]:
    settings = configured_archive_settings(start_path=start_path)
    archive_root_path = (archive_root or default_chat_archive_root()).expanduser().resolve()

    selected_instances = settings.provider_instances
    if providers is not None:
        selected_instances = tuple(
            instance
            for instance in selected_instances
            if instance.family in providers
        )

    instance_payloads: list[dict[str, object]] = []
    synced_instance_count = 0
    skipped_instance_count = 0

    for instance in selected_instances:
        instance_payload = _archive_single_instance(
            instance=instance,
            archive_root=archive_root_path,
        )
        instance_payloads.append(instance_payload)
        if bool(instance_payload["synced"]):
            synced_instance_count += 1
        else:
            skipped_instance_count += 1

    committed = False
    commit_message: str | None = None
    if synced_instance_count > 0:
        _ensure_git_repo(archive_root_path)
        run_git(archive_root_path, "add", "-A")
        if run_git(archive_root_path, "status", "--porcelain").strip():
            commit_message = f"{settings.commit_prefix}: {_archive_commit_timestamp()}"
            run_git(
                archive_root_path,
                "-c",
                "user.name=agentos",
                "-c",
                "user.email=agentos@local.invalid",
                "commit",
                "-m",
                commit_message,
            )
            committed = True

    provider_names = _unique_strings(tuple(instance.family for instance in selected_instances))
    return {
        "status": "ok",
        "command": "chat archive",
        "archive_root": str(archive_root_path),
        "commit_prefix": settings.commit_prefix,
        "provider_count": len(provider_names),
        "instance_count": len(selected_instances),
        "synced_instance_count": synced_instance_count,
        "skipped_instance_count": skipped_instance_count,
        "committed": committed,
        "commit_message": commit_message,
        "instances": instance_payloads,
    }


def _archive_single_instance(
    *,
    instance: ArchiveInstance,
    archive_root: Path,
) -> dict[str, object]:
    destination_root = instance.destination_root(archive_root)
    home_results: list[dict[str, object]] = []
    synced = False

    for home_key, home_path in instance.homes:
        exists = home_path.is_dir()
        destination_path = _archive_home_destination(
            instance=instance,
            destination_root=destination_root,
            home_key=home_key,
        )
        home_payload = {
            "key": home_key,
            "source_path": str(home_path),
            "destination_path": str(destination_path),
            "exists": exists,
            "synced": False,
        }
        if exists:
            _mirror_archive_home(
                source_path=home_path,
                destination_path=destination_path,
                includes=instance.includes,
                excludes=instance.excludes,
            )
            home_payload["synced"] = True
            synced = True
        home_results.append(home_payload)

    missing_home_keys = [
        home_result["key"]
        for home_result in home_results
        if not bool(home_result["exists"])
    ]

    payload = instance.summary(archive_root)
    payload.update(
        {
            "synced": synced,
            "missing_home_keys": missing_home_keys,
            "homes_status": home_results,
        }
    )
    return payload


def _archive_home_destination(
    *,
    instance: ArchiveInstance,
    destination_root: Path,
    home_key: str,
) -> Path:
    if len(instance.homes) == 1:
        return destination_root
    return destination_root / home_key


def _mirror_archive_home(
    *,
    source_path: Path,
    destination_path: Path,
    includes: tuple[str, ...],
    excludes: tuple[str, ...],
) -> None:
    destination_path.mkdir(parents=True, exist_ok=True)
    command = [
        "rsync",
        "-a",
        "--delete",
        "--delete-excluded",
        "--exclude",
        ".git",
    ]

    if includes:
        command.extend(["--prune-empty-dirs", "--include", "*/"])
        for pattern in excludes:
            command.extend(["--exclude", pattern])
        for pattern in includes:
            command.extend(["--include", pattern])
        command.extend(["--exclude", "*"])
    else:
        for pattern in excludes:
            command.extend(["--exclude", pattern])

    source_text = str(source_path)
    if not source_text.endswith("/"):
        source_text += "/"
    command.extend([source_text, str(destination_path)])

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        details = result.stderr.strip() or result.stdout.strip() or "rsync failed"
        raise CliError(details)


def _ensure_git_repo(repo_root: Path) -> None:
    repo_root.mkdir(parents=True, exist_ok=True)
    git_dir = repo_root / ".git"
    if git_dir.exists() and not git_dir.is_dir():
        raise CliError(f"archive git path is not a directory: {git_dir}")
    if not git_dir.exists():
        run_git(repo_root, "init")


def _archive_commit_timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _archive_config_from_config(config: dict[str, object]) -> dict[str, object] | None:
    chat_config = config.get("chat")
    if chat_config is None:
        return None
    if not isinstance(chat_config, dict):
        raise CliError("config field chat must be a JSON object")

    archive_config = chat_config.get("archive")
    if archive_config is None:
        return None
    if not isinstance(archive_config, dict):
        raise CliError("config field chat.archive must be a JSON object")
    return archive_config


def _archive_instances_from_config(archive_config: dict[str, object]) -> tuple[ArchiveInstance, ...]:
    raw_instances = archive_config.get("provider_instances")
    if raw_instances is None:
        return ()
    if not isinstance(raw_instances, list):
        raise CliError("config field chat.archive.provider_instances must be a JSON array")

    instances: list[ArchiveInstance] = []
    for index, raw_instance in enumerate(raw_instances):
        if not isinstance(raw_instance, dict):
            raise CliError(f"chat.archive.provider_instances[{index}] must be a JSON object")
        instances.append(_archive_instance_from_config(raw_instance, index=index))
    return tuple(instances)


def _archive_instance_from_config(raw_instance: dict[str, object], *, index: int) -> ArchiveInstance:
    family_name = raw_instance.get("provider")
    if not isinstance(family_name, str) or not family_name:
        raise CliError(f"chat.archive.provider_instances[{index}].provider is required")

    family = _archive_family_for_name(family_name)
    if family is None:
        supported_providers = ", ".join(
            sorted(provider_family.family for provider_family in supported_archive_provider_families())
        )
        raise CliError(
            f"chat.archive.provider_instances[{index}].provider must be one of: {supported_providers}"
        )

    home = raw_instance.get("home")
    raw_homes = raw_instance.get("homes")
    raw_instance_name = raw_instance.get("instance")

    if home is not None and raw_homes is not None:
        raise CliError(
            f"chat.archive.provider_instances[{index}] must not define both home and homes"
        )

    includes = _load_optional_string_tuple(
        raw_instance.get("includes"),
        field_name=f"chat.archive.provider_instances[{index}].includes",
    )
    excludes = _load_optional_string_tuple(
        raw_instance.get("excludes"),
        field_name=f"chat.archive.provider_instances[{index}].excludes",
    )
    homes = _load_optional_string_mapping(
        raw_homes,
        field_name=f"chat.archive.provider_instances[{index}].homes",
    )

    instance_name: str | None = None
    if raw_instance_name is not None:
        if not isinstance(raw_instance_name, str) or not raw_instance_name.strip():
            raise CliError(f"chat.archive.provider_instances[{index}].instance must be a non-empty string")
        instance_name = raw_instance_name.strip()

    if home is not None:
        normalized_home = _normalize_archive_home(
            home,
            field_name=f"chat.archive.provider_instances[{index}].home",
        )
        if homes:
            raise CliError(
                f"chat.archive.provider_instances[{index}] must define either home or homes, not both"
            )
        return family.instance_from_home(
            normalized_home,
            index=index,
            is_default=False,
            instance_name=instance_name,
            includes=includes,
            excludes=excludes,
        )

    if homes:
        if len(family.home_slots) == 1:
            raise CliError(
                f"chat.archive.provider_instances[{index}].homes is only supported for providers with multiple home roots; "
                f"use chat.archive.provider_instances[{index}].home"
            )
        return family.instance_from_homes(
            homes,
            index=index,
            is_default=False,
            instance_name=instance_name,
            includes=includes,
            excludes=excludes,
        )

    raise CliError(
        f"chat.archive.provider_instances[{index}] must define home or homes"
    )


def _archive_family_for_name(family_name: str) -> ArchiveFamily | None:
    for family in supported_archive_provider_families():
        if family.family == family_name:
            return family
    return None


def _archive_provider_instance_field_name(*, index: int | None, field: str) -> str:
    if index is None:
        return field
    return f"chat.archive.provider_instances[{index}].{field}"


def _normalize_archive_home(home: object, *, field_name: str) -> str:
    if not isinstance(home, str) or not home.strip():
        raise CliError(f"{field_name} must be a non-empty string")
    return home.strip()


def _load_optional_string_tuple(value: object, *, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise CliError(f"{field_name} must not be empty")
        return (stripped,)
    if not isinstance(value, list):
        raise CliError(f"{field_name} must be a string or array of strings")

    items: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise CliError(f"{field_name}[{index}] must be a non-empty string")
        items.append(item.strip())
    return tuple(items)


def _load_optional_string_mapping(value: object, *, field_name: str) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise CliError(f"{field_name} must be a JSON object")

    items: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip():
            raise CliError(f"{field_name} contains an invalid key")
        if not isinstance(item, str) or not item.strip():
            raise CliError(f"{field_name}.{key} must be a non-empty string")
        items[key.strip()] = item.strip()
    return items


def _dedupe_archive_instances(provider_instances: tuple[ArchiveInstance, ...]) -> tuple[ArchiveInstance, ...]:
    unique_instances: dict[tuple[object, ...], ArchiveInstance] = {}
    for provider_instance in provider_instances:
        key = provider_instance.identity_key()
        if key not in unique_instances:
            unique_instances[key] = provider_instance
            continue

        existing = unique_instances[key]
        if existing.is_default and not provider_instance.is_default:
            unique_instances[key] = provider_instance
    return tuple(unique_instances.values())


def _validate_unique_archive_destinations(provider_instances: tuple[ArchiveInstance, ...]) -> None:
    seen_destinations: dict[tuple[str, str], ArchiveInstance] = {}
    for provider_instance in provider_instances:
        key = (provider_instance.family, provider_instance.resolved_instance_name)
        if key in seen_destinations:
            existing = seen_destinations[key]
            raise CliError(
                "chat archive provider instances resolve to the same destination "
                f"{provider_instance.family}/{provider_instance.resolved_instance_name}: "
                f"{existing.homes_map()} and {provider_instance.homes_map()}"
            )
        seen_destinations[key] = provider_instance


def _unique_strings(values: tuple[str, ...]) -> tuple[str, ...]:
    items: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        items.append(value)
    return tuple(items)


__all__ = [
    "archive_chat_instances",
    "configured_archive_settings",
    "default_chat_archive_root",
    "supported_archive_provider_families",
]
