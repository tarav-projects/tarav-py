from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentos._core.errors import CliError
from agentos._core.path_validation import validate_string_for_path
from agentos.chat.providers import (
    canonical_chat_provider_specs,
    canonical_chat_provider_spec_for_name,
    ProviderInstance,
    ProviderInstanceAnchor,
    ProviderHomeSlot,
    ProviderInstanceConfigEntry,
)


@dataclass(frozen=True)
class ChatlasProviderHandler:
    family: str
    home_slots: tuple[ProviderHomeSlot, ...]
    default_excludes: tuple[str, ...] = ()
    default_includes: tuple[str, ...] = ()

    def supported_home_keys(self) -> tuple[str, ...]:
        return tuple(slot.key for slot in self.home_slots)

    def default_instance(self) -> ProviderInstance:
        return self.instance_from_homes(
            {slot.key: slot.default_home for slot in self.home_slots},
            field_prefix="chatlas.provider_instances",
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
                _normalize_chatlas_home(
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
class ChatlasProviderContext:
    provider_handler: ChatlasProviderHandler
    provider_instance: ProviderInstance
    resolved_instance_name: str
    effective_excludes: tuple[str, ...]

    def destination_root(self, raw_root: Path) -> Path:
        homes = self.provider_instance.homes
        if len(homes) != 1:
            return raw_root
        _, home_path = homes[0]
        return _chatlas_home_destination(
            raw_root=raw_root,
            home_path=home_path,
        )

    def summary(self, raw_root: Path) -> dict[str, Any]:
        destination_roots = {
            key: str(
                _chatlas_home_destination(
                    raw_root=raw_root,
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
            "destination_root": str(self.destination_root(raw_root)) if len(self.provider_instance.homes) == 1 else None,
            "destination_roots": destination_roots,
        }


def _build_chatlas_provider_handler(provider_spec) -> ChatlasProviderHandler:
    return ChatlasProviderHandler(
        family=provider_spec.family,
        home_slots=provider_spec.home_slots,
        default_excludes=provider_spec.chatlas_default_excludes,
        default_includes=provider_spec.chatlas_default_includes,
    )


_CHATLAS_PROVIDER_HANDLERS = tuple(
    _build_chatlas_provider_handler(provider_spec)
    for provider_spec in canonical_chat_provider_specs()
    if provider_spec.supports_chatlas_raw
)
_CHATLAS_PROVIDER_HANDLERS_BY_NAME = {
    provider_handler.family: provider_handler
    for provider_handler in _CHATLAS_PROVIDER_HANDLERS
}
_CHATLAS_PROVIDER_NAMES = tuple(sorted(_CHATLAS_PROVIDER_HANDLERS_BY_NAME))


def supported_chatlas_provider_families() -> tuple[ChatlasProviderHandler, ...]:
    return _CHATLAS_PROVIDER_HANDLERS


def _provider_instances_from_config_entries(
    entries: tuple[ProviderInstanceConfigEntry, ...],
) -> tuple[ProviderInstance, ...]:
    return tuple(_chatlas_instance_from_raw_config(entry) for entry in entries)


def _chatlas_instance_from_raw_config(entry: ProviderInstanceConfigEntry) -> ProviderInstance:
    raw_instance = entry.raw_instance
    family_name = raw_instance.get("provider")
    if not isinstance(family_name, str) or not family_name:
        raise CliError(f"{entry.field_name('provider')} is required")

    provider_handler = _chatlas_provider_handler_for_name(family_name)
    if provider_handler is None:
        supported_providers = ", ".join(_CHATLAS_PROVIDER_NAMES)
        raise CliError(
            f"{entry.field_name('provider')} must be one of: {supported_providers}"
        )

    home = raw_instance.get("home")
    raw_homes = raw_instance.get("homes")
    raw_instance_name = raw_instance.get("instance")
    if home is not None and raw_homes is not None:
        raise CliError(
            f"{entry.item_path()} must not define both home and homes"
        )

    includes = _load_optional_string_tuple(
        raw_instance.get("includes"),
        field_name=entry.field_name("includes"),
    )
    excludes = _load_optional_string_tuple(
        raw_instance.get("excludes"),
        field_name=entry.field_name("excludes"),
    )
    homes = _load_optional_string_mapping(
        raw_homes,
        field_name=entry.field_name("homes"),
    )

    instance_name: str | None = None
    if raw_instance_name is not None:
        if not isinstance(raw_instance_name, str) or not raw_instance_name.strip():
            raise CliError(f"{entry.field_name('instance')} must be a non-empty string")
        instance_name = raw_instance_name.strip()

    if home is not None:
        normalized_home = _normalize_chatlas_home(
            home,
            field_name=entry.field_name("home"),
        )
        if homes:
            raise CliError(
                f"{entry.item_path()} must define either home or homes, not both"
            )
        return provider_handler.instance_from_home(
            normalized_home,
            field_prefix=entry.field_prefix,
            index=entry.index,
            is_default=False,
            instance_name=instance_name,
            includes=includes,
            excludes=excludes,
        )

    if homes:
        if len(provider_handler.home_slots) == 1:
            raise CliError(
                f"{entry.field_name('homes')} is only supported for providers with multiple home roots; "
                f"use {entry.field_name('home')}"
            )
        return provider_handler.instance_from_homes(
            homes,
            field_prefix=entry.field_prefix,
            index=entry.index,
            is_default=False,
            instance_name=instance_name,
            includes=includes,
            excludes=excludes,
        )

    raise CliError(
        f"{entry.item_path()} must define home or homes"
    )


def _chatlas_provider_handler_for_name(family_name: str) -> ChatlasProviderHandler | None:
    provider_spec = canonical_chat_provider_spec_for_name(family_name)
    if provider_spec is None or not provider_spec.supports_chatlas_raw:
        return None
    return _CHATLAS_PROVIDER_HANDLERS_BY_NAME.get(family_name)


def _provider_instance_field_name(*, field_prefix: str, index: int | None, field: str) -> str:
    if index is None:
        return field
    return f"{field_prefix}[{index}].{field}"


def _normalize_chatlas_home(home: object, *, field_name: str) -> str:
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


def _build_chatlas_provider_context(provider_instance: ProviderInstance) -> ChatlasProviderContext:
    provider_handler = _chatlas_provider_handler_for_name(provider_instance.family)
    if provider_handler is None:
        raise CliError(f"unsupported chatlas provider family {provider_instance.family}")

    return ChatlasProviderContext(
        provider_handler=provider_handler,
        provider_instance=provider_instance,
        resolved_instance_name=_resolve_chatlas_instance_name(provider_instance),
        effective_excludes=_unique_strings(
            provider_instance.excludes
            + _derived_chatlas_instance_excludes(provider_instance.family, provider_instance.homes)
        ),
    )


def _mirror_chatlas_provider_instance(
    *,
    context: ChatlasProviderContext,
    raw_root: Path,
) -> dict[str, object]:
    home_results: list[dict[str, object]] = []
    synced = False

    for home_key, home_path in context.provider_instance.homes:
        exists = home_path.is_dir()
        destination_path = _chatlas_home_destination(
            raw_root=raw_root,
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
            _mirror_chatlas_home(
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

    payload = context.summary(raw_root)
    payload.update(
        {
            "synced": synced,
            "missing_home_keys": missing_home_keys,
            "homes_status": home_results,
        }
    )
    return payload


def _chatlas_home_destination(
    *,
    raw_root: Path,
    home_path: Path,
) -> Path:
    return raw_root / _chatlas_home_relpath(home_path)


def _mirror_chatlas_home(
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


def _chatlas_home_relpath(home_path: Path) -> Path:
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


def _dedupe_chatlas_instances(provider_instances: tuple[ProviderInstance, ...]) -> tuple[ProviderInstance, ...]:
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


def _validate_unique_chatlas_destinations(provider_instances: tuple[ProviderInstance, ...]) -> None:
    seen_destinations: dict[tuple[str, str], ProviderInstance] = {}
    for provider_instance in provider_instances:
        context = _build_chatlas_provider_context(provider_instance)
        key = (provider_instance.family, context.resolved_instance_name)
        if key in seen_destinations:
            existing = seen_destinations[key]
            raise CliError(
                "chatlas provider instances resolve to the same destination "
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


def _derive_chatlas_instance_name(
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
                return validate_string_for_path(suffix, field_name="chatlas instance name")

    return validate_string_for_path(basename, field_name="chatlas instance name")


def _resolve_chatlas_instance_name(provider_instance: ProviderInstance) -> str:
    if provider_instance.instance_id is not None:
        return provider_instance.instance_id
    if provider_instance.is_default:
        return "default"
    derived_name = _derive_chatlas_instance_name(provider_instance.family, provider_instance.homes)
    if derived_name is not None:
        return derived_name
    return provider_instance.fingerprint[:12]


def _derived_chatlas_instance_excludes(
    family: str,
    homes: tuple[tuple[str, Path], ...],
) -> tuple[str, ...]:
    if family != "codex":
        return ()
    derived_name = _derive_chatlas_instance_name(family, homes)
    if derived_name == "tk":
        return ("_auth-tk.json",)
    return ()


__all__ = [
    "supported_chatlas_provider_families",
]
