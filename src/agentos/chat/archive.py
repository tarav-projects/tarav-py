from __future__ import annotations

import os
import shutil
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
from agentos.chat.providers import ProviderInstance, ProviderInstanceAnchor

CHAT_ARCHIVE_DIRNAME = "chat-archive"
DEFAULT_ARCHIVE_COMMIT_PREFIX = "checkpoint"


@dataclass(frozen=True)
class ArchiveHomeSlot:
    key: str
    default_home: str


@dataclass(frozen=True)
class ArchiveProviderHandler:
    family: str
    home_slots: tuple[ArchiveHomeSlot, ...]
    default_excludes: tuple[str, ...] = ()
    default_includes: tuple[str, ...] = ()

    def supported_home_keys(self) -> tuple[str, ...]:
        return tuple(slot.key for slot in self.home_slots)

    def default_instance(self) -> ProviderInstance:
        return self.instance_from_homes(
            {slot.key: slot.default_home for slot in self.home_slots},
            field_prefix="chat.archive.provider_instances",
            index=None,
            is_default=True,
            instance_name=None,
            includes=(),
            excludes=(),
        )

    def instance_from_home(
        self,
        home: str,
        *,
        field_prefix: str,
        index: int | None,
        is_default: bool,
        instance_name: str | None,
        includes: tuple[str, ...],
        excludes: tuple[str, ...],
    ) -> ProviderInstance:
        if len(self.home_slots) != 1:
            field_name = _provider_instance_field_name(field_prefix=field_prefix, index=index, field="home")
            homes_field_name = _provider_instance_field_name(field_prefix=field_prefix, index=index, field="homes")
            supported_keys = ", ".join(self.supported_home_keys())
            raise CliError(
                f"{field_name} is only supported for providers with a single home root; "
                f"use {homes_field_name} with keys: {supported_keys}"
            )
        slot = self.home_slots[0]
        return self.instance_from_homes(
            {slot.key: home},
            field_prefix=field_prefix,
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
        field_prefix: str,
        index: int | None,
        is_default: bool,
        instance_name: str | None,
        includes: tuple[str, ...],
        excludes: tuple[str, ...],
    ) -> ProviderInstance:
        supported_slots = {slot.key: slot for slot in self.home_slots}
        unsupported_keys = sorted(key for key in homes if key not in supported_slots)
        homes_field_name = _provider_instance_field_name(field_prefix=field_prefix, index=index, field="homes")
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
            field_name = _provider_instance_field_name(field_prefix=field_prefix, index=index, field="instance")
            resolved_instance_name = validate_string_for_path(instance_name, field_name=field_name)

        anchors = tuple(
            ProviderInstanceAnchor(role="home", path=home_path, slot=home_key)
            for home_key, home_path in normalized_homes
        )

        return ProviderInstance(
            family=self.family,
            instance_id=resolved_instance_name,
            homes=tuple(normalized_homes),
            includes=_unique_strings(self.default_includes + includes),
            excludes=_unique_strings(self.default_excludes + excludes),
            anchors=anchors,
            is_default=is_default,
        )


@dataclass(frozen=True)
class ArchiveProviderContext:
    provider_handler: ArchiveProviderHandler
    provider_instance: ProviderInstance
    resolved_instance_name: str
    effective_excludes: tuple[str, ...]

    def destination_root(self, archive_root: Path) -> Path:
        homes = self.provider_instance.homes
        if len(homes) != 1:
            return archive_root
        _, home_path = homes[0]
        return _archive_home_destination(
            archive_root=archive_root,
            home_path=home_path,
        )

    def summary(self, archive_root: Path) -> dict[str, Any]:
        destination_roots = {
            key: str(
                _archive_home_destination(
                    archive_root=archive_root,
                    home_path=home_path,
                )
            )
            for key, home_path in self.provider_instance.homes
        }
        return {
            "provider": self.provider_instance.family,
            "instance": self.resolved_instance_name,
            "is_default": self.provider_instance.is_default,
            "homes": {key: str(path) for key, path in self.provider_instance.homes},
            "includes": list(self.provider_instance.includes),
            "excludes": list(self.effective_excludes),
            "destination_root": str(self.destination_root(archive_root)) if len(self.provider_instance.homes) == 1 else None,
            "destination_roots": destination_roots,
        }


@dataclass(frozen=True)
class ArchiveSettings:
    commit_prefix: str
    provider_instances: tuple[ProviderInstance, ...]


def default_chat_archive_root() -> Path:
    return agentos_home_dir() / CHAT_ARCHIVE_DIRNAME


def supported_archive_provider_families() -> tuple[ArchiveProviderHandler, ...]:
    return (
        ArchiveProviderHandler(
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
        ArchiveProviderHandler(
            family="copilot-cli",
            home_slots=(ArchiveHomeSlot(key="home", default_home="~/.copilot"),),
            default_excludes=(
                "pkg/",
                "logs/",
                "ide/",
            ),
        ),
        ArchiveProviderHandler(
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
        ArchiveProviderHandler(
            family="gemini-cli",
            home_slots=(ArchiveHomeSlot(key="home", default_home="~/.gemini"),),
            default_excludes=(
                "tmp/bin/",
                "oauth_creds.json",
                "google_accounts.json",
            ),
        ),
        ArchiveProviderHandler(
            family="agents",
            home_slots=(ArchiveHomeSlot(key="home", default_home="~/.agents"),),
        ),
        ArchiveProviderHandler(
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
        provider_instances.extend(_session_archive_instances_from_config(config))
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
    selected_contexts = tuple(_build_archive_provider_context(instance) for instance in selected_instances)

    instance_payloads: list[dict[str, object]] = []
    synced_instance_count = 0
    skipped_instance_count = 0

    for context in selected_contexts:
        instance_payload = _archive_single_instance(
            context=context,
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

    provider_names = _unique_strings(tuple(context.provider_instance.family for context in selected_contexts))
    return {
        "status": "ok",
        "command": "chat archive",
        "archive_root": str(archive_root_path),
        "commit_prefix": settings.commit_prefix,
        "provider_count": len(provider_names),
        "instance_count": len(selected_contexts),
        "synced_instance_count": synced_instance_count,
        "skipped_instance_count": skipped_instance_count,
        "committed": committed,
        "commit_message": commit_message,
        "instances": instance_payloads,
    }


def _archive_single_instance(
    *,
    context: ArchiveProviderContext,
    archive_root: Path,
) -> dict[str, object]:
    legacy_destination_root = _legacy_archive_instance_destination_root(
        context=context,
        archive_root=archive_root,
    )
    if legacy_destination_root != archive_root and legacy_destination_root.exists():
        _remove_archive_tree(legacy_destination_root)
        _prune_archive_parent_dirs(legacy_destination_root.parent, stop=archive_root)

    home_results: list[dict[str, object]] = []
    synced = False

    for home_key, home_path in context.provider_instance.homes:
        exists = home_path.is_dir()
        destination_path = _archive_home_destination(
            archive_root=archive_root,
            home_path=home_path,
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
                includes=context.provider_instance.includes,
                excludes=context.effective_excludes,
            )
            home_payload["synced"] = True
            synced = True
        home_results.append(home_payload)

    missing_home_keys = [
        home_result["key"]
        for home_result in home_results
        if not bool(home_result["exists"])
    ]

    payload = context.summary(archive_root)
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
    archive_root: Path,
    home_path: Path,
) -> Path:
    return archive_root / _archive_home_relpath(home_path)


def _legacy_archive_instance_destination_root(
    *,
    context: ArchiveProviderContext,
    archive_root: Path,
) -> Path:
    return archive_root / context.provider_instance.family / context.resolved_instance_name


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


def _archive_home_relpath(home_path: Path) -> Path:
    normalized_home = home_path.expanduser().resolve()
    user_home = Path.home().expanduser().resolve()

    try:
        relpath = normalized_home.relative_to(user_home)
        if relpath.parts:
            return relpath
    except ValueError:
        pass

    if normalized_home.is_absolute():
        relative_text = os.path.relpath(str(normalized_home), normalized_home.anchor)
        relpath = Path(relative_text)
        if relpath.parts and relpath != Path("."):
            return relpath

    return Path(normalized_home.name)


def _remove_archive_tree(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
        return
    if path.is_dir():
        shutil.rmtree(path)


def _prune_archive_parent_dirs(path: Path, *, stop: Path) -> None:
    current = path
    stop_resolved = stop.resolve()
    while current != stop_resolved:
        if not current.exists() or not current.is_dir():
            return
        children = list(current.iterdir())
        removable = [child for child in children if child.name == ".DS_Store"]
        for child in removable:
            child.unlink()
        if any(child.name != ".DS_Store" for child in children):
            return
        try:
            current.rmdir()
        except OSError:
            return
        parent = current.parent
        if parent == current:
            return
        current = parent


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


def _archive_instances_from_config(archive_config: dict[str, object]) -> tuple[ProviderInstance, ...]:
    raw_instances = archive_config.get("provider_instances")
    if raw_instances is None:
        return ()
    if not isinstance(raw_instances, list):
        raise CliError("config field chat.archive.provider_instances must be a JSON array")

    instances: list[ProviderInstance] = []
    for index, raw_instance in enumerate(raw_instances):
        if not isinstance(raw_instance, dict):
            raise CliError(f"chat.archive.provider_instances[{index}] must be a JSON object")
        instances.append(
            _archive_instance_from_raw_config(
                raw_instance,
                index=index,
                field_prefix="chat.archive.provider_instances",
            )
        )
    return tuple(instances)


def _session_archive_instances_from_config(config: dict[str, object]) -> tuple[ProviderInstance, ...]:
    chat_config = config.get("chat")
    if chat_config is None:
        return ()
    if not isinstance(chat_config, dict):
        raise CliError("config field chat must be a JSON object")

    session_config = chat_config.get("session")
    if session_config is None:
        return ()
    if not isinstance(session_config, dict):
        raise CliError("config field chat.session must be a JSON object")

    raw_instances = session_config.get("provider_instances")
    if raw_instances is None:
        return ()
    if not isinstance(raw_instances, list):
        raise CliError("config field chat.session.provider_instances must be a JSON array")

    instances: list[ProviderInstance] = []
    for index, raw_instance in enumerate(raw_instances):
        if not isinstance(raw_instance, dict):
            raise CliError(f"chat.session.provider_instances[{index}] must be a JSON object")
        instances.append(
            _archive_instance_from_raw_config(
                raw_instance,
                index=index,
                field_prefix="chat.session.provider_instances",
            )
        )
    return tuple(instances)


def _archive_instance_from_raw_config(
    raw_instance: dict[str, object],
    *,
    index: int,
    field_prefix: str,
) -> ProviderInstance:
    family_name = raw_instance.get("provider")
    if not isinstance(family_name, str) or not family_name:
        raise CliError(f"{field_prefix}[{index}].provider is required")

    provider_handler = _archive_provider_handler_for_name(family_name)
    if provider_handler is None:
        supported_providers = ", ".join(
            sorted(provider_family.family for provider_family in supported_archive_provider_families())
        )
        raise CliError(
            f"{field_prefix}[{index}].provider must be one of: {supported_providers}"
        )

    home = raw_instance.get("home")
    raw_homes = raw_instance.get("homes")
    raw_instance_name = raw_instance.get("instance")

    if home is not None and raw_homes is not None:
        raise CliError(
            f"{field_prefix}[{index}] must not define both home and homes"
        )

    includes = _load_optional_string_tuple(
        raw_instance.get("includes"),
        field_name=f"{field_prefix}[{index}].includes",
    )
    excludes = _load_optional_string_tuple(
        raw_instance.get("excludes"),
        field_name=f"{field_prefix}[{index}].excludes",
    )
    homes = _load_optional_string_mapping(
        raw_homes,
        field_name=f"{field_prefix}[{index}].homes",
    )

    instance_name: str | None = None
    if raw_instance_name is not None:
        if not isinstance(raw_instance_name, str) or not raw_instance_name.strip():
            raise CliError(f"{field_prefix}[{index}].instance must be a non-empty string")
        instance_name = raw_instance_name.strip()

    if home is not None:
        normalized_home = _normalize_archive_home(
            home,
            field_name=f"{field_prefix}[{index}].home",
        )
        if homes:
            raise CliError(
                f"{field_prefix}[{index}] must define either home or homes, not both"
            )
        return provider_handler.instance_from_home(
            normalized_home,
            field_prefix=field_prefix,
            index=index,
            is_default=False,
            instance_name=instance_name,
            includes=includes,
            excludes=excludes,
        )

    if homes:
        if len(provider_handler.home_slots) == 1:
            raise CliError(
                f"{field_prefix}[{index}].homes is only supported for providers with multiple home roots; "
                f"use {field_prefix}[{index}].home"
            )
        return provider_handler.instance_from_homes(
            homes,
            field_prefix=field_prefix,
            index=index,
            is_default=False,
            instance_name=instance_name,
            includes=includes,
            excludes=excludes,
        )

    raise CliError(
        f"{field_prefix}[{index}] must define home or homes"
    )


def _archive_provider_handler_for_name(family_name: str) -> ArchiveProviderHandler | None:
    for provider_handler in supported_archive_provider_families():
        if provider_handler.family == family_name:
            return provider_handler
    return None


def _provider_instance_field_name(*, field_prefix: str, index: int | None, field: str) -> str:
    if index is None:
        return field
    return f"{field_prefix}[{index}].{field}"


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


def _build_archive_provider_context(provider_instance: ProviderInstance) -> ArchiveProviderContext:
    provider_handler = _archive_provider_handler_for_name(provider_instance.family)
    if provider_handler is None:
        raise CliError(f"unsupported archive provider family {provider_instance.family}")

    return ArchiveProviderContext(
        provider_handler=provider_handler,
        provider_instance=provider_instance,
        resolved_instance_name=_resolve_archive_instance_name(provider_instance),
        effective_excludes=_unique_strings(
            provider_instance.excludes
            + _derived_archive_instance_excludes(provider_instance.family, provider_instance.homes)
        ),
    )


def _dedupe_archive_instances(provider_instances: tuple[ProviderInstance, ...]) -> tuple[ProviderInstance, ...]:
    unique_instances: dict[tuple[object, ...], ProviderInstance] = {}
    for provider_instance in provider_instances:
        key = provider_instance.identity_key()
        if key not in unique_instances:
            unique_instances[key] = provider_instance
            continue

        existing = unique_instances[key]
        if existing.is_default and not provider_instance.is_default:
            unique_instances[key] = provider_instance
    return tuple(unique_instances.values())


def _validate_unique_archive_destinations(provider_instances: tuple[ProviderInstance, ...]) -> None:
    seen_destinations: dict[tuple[str, str], ProviderInstance] = {}
    for provider_instance in provider_instances:
        context = _build_archive_provider_context(provider_instance)
        key = (provider_instance.family, context.resolved_instance_name)
        if key in seen_destinations:
            existing = seen_destinations[key]
            raise CliError(
                "chat archive provider instances resolve to the same destination "
                f"{provider_instance.family}/{context.resolved_instance_name}: "
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


def _derive_archive_instance_name(
    family: str,
    homes: tuple[tuple[str, Path], ...],
) -> str | None:
    if len(homes) != 1:
        return None

    _, home_path = homes[0]
    basename = home_path.name.lstrip(".")
    if not basename or basename == family:
        return None

    for separator in ("-", "_"):
        family_prefix = f"{family}{separator}"
        if basename.startswith(family_prefix):
            suffix = basename[len(family_prefix):].strip()
            if suffix:
                return validate_string_for_path(suffix, field_name="archive instance name")

    return validate_string_for_path(basename, field_name="archive instance name")


def _resolve_archive_instance_name(provider_instance: ProviderInstance) -> str:
    if provider_instance.instance_id is not None:
        return provider_instance.instance_id
    if provider_instance.is_default:
        return "default"
    derived_name = _derive_archive_instance_name(provider_instance.family, provider_instance.homes)
    if derived_name is not None:
        return derived_name
    return provider_instance.fingerprint[:12]


def _derived_archive_instance_excludes(
    family: str,
    homes: tuple[tuple[str, Path], ...],
) -> tuple[str, ...]:
    # Preserve the old trackagents behavior for ~/.codex-tk without forcing
    # users to duplicate their existing session-home config under chat.archive.
    if family != "codex":
        return ()
    derived_name = _derive_archive_instance_name(family, homes)
    if derived_name == "tk":
        return ("_auth-tk.json",)
    return ()


__all__ = [
    "archive_chat_instances",
    "configured_archive_settings",
    "default_chat_archive_root",
    "supported_archive_provider_families",
]
