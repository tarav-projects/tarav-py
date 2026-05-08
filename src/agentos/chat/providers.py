from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

from agentos._core.errors import CliError
from agentos._core.sequences import _unique_paths
from agentos._core.path_validation import validate_string_for_path
from agentos._core.project import (
    agentos_home_dir,
    find_agentos_project_root,
    global_config_path,
    load_global_config,
    load_project_config,
    project_config_path,
)
from agentos.providers import (
    ProviderFamily,
    ProviderHomeAnchor as LegacyProviderConfigAnchor,
    ProviderHomeSlot,
    canonical_provider_families,
    canonical_provider_family_for_name,
    require_canonical_provider_family,
)
from agentos.codex.chatlas import (
    CODEX_CHATLAS_DEFAULT_EXCLUDES,
    CODEX_CHATLAS_DEFAULT_INCLUDES,
)
from agentos.claude.chatlas import (
    CLAUDE_CHATLAS_DEFAULT_EXCLUDES,
    CLAUDE_CHATLAS_DEFAULT_INCLUDES,
)
from agentos.copilot.chatlas import (
    COPILOT_CHATLAS_DEFAULT_EXCLUDES,
    COPILOT_CHATLAS_DEFAULT_INCLUDES,
)
from agentos.gemini.chatlas import GEMINI_CHATLAS_DEFAULT_EXCLUDES
from agentos.home.providers import home_provider_for_name
from agentos.openclaw.chatlas import (
    OPENCLAW_CHATLAS_DEFAULT_EXCLUDES,
    OPENCLAW_CHATLAS_DEFAULT_INCLUDES,
)
from agentos.opencode.chatlas import (
    OPENCODE_CHATLAS_DEFAULT_EXCLUDES,
    OPENCODE_CHATLAS_DEFAULT_INCLUDES,
)
from agentos.pi.chatlas import (
    PI_CHATLAS_DEFAULT_EXCLUDES,
    PI_CHATLAS_DEFAULT_INCLUDES,
)


@dataclass(frozen=True)
class ChatProviderSpec:
    provider_family: ProviderFamily
    home_slots: tuple[ProviderHomeSlot, ...]
    supports_session_discovery: bool = True
    supports_chatlas_raw: bool = True
    chatlas_default_excludes: tuple[str, ...] = ()
    chatlas_default_includes: tuple[str, ...] = ()

    @property
    def family(self) -> str:
        return self.provider_family.family


_CANONICAL_CHAT_PROVIDER_SPECS: tuple[ChatProviderSpec, ...] = ()


def _legacy_provider_default_cli_command(family_name: str) -> tuple[str, ...]:
    if family_name == "codex":
        return ("codex",)
    if family_name == "copilot-cli":
        return ("copilot",)
    if family_name == "pi":
        return ("pi",)
    return ()


def _legacy_provider_default_run_args(family_name: str) -> tuple[str, ...]:
    if family_name == "codex":
        return ("exec", "--dangerously-bypass-approvals-and-sandbox")
    if family_name == "copilot-cli":
        return ("--allow-all-tools", "--no-ask-user")
    if family_name == "opencode":
        return ("run",)
    return ()


def _legacy_provider_default_model(family_name: str) -> str | None:
    if family_name == "codex":
        return "gpt-5.4"
    return None


def _legacy_provider_default_model_flag(family_name: str) -> str | None:
    if family_name == "codex":
        return "--model"
    if family_name == "copilot-cli":
        return "--model"
    if family_name == "opencode":
        return "--model"
    if family_name == "pi":
        return "--model"
    return None


def _legacy_provider_default_prompt_flag(family_name: str) -> str | None:
    if family_name == "copilot-cli":
        return "-p"
    if family_name == "pi":
        return "-p"
    return None


def canonical_chat_provider_specs() -> tuple[ChatProviderSpec, ...]:
    return _CANONICAL_CHAT_PROVIDER_SPECS


def canonical_chat_provider_spec_for_name(family_name: str) -> ChatProviderSpec | None:
    for provider_spec in _CANONICAL_CHAT_PROVIDER_SPECS:
        if provider_spec.family == family_name:
            return provider_spec
    return None


def _chat_provider_spec(
    family_name: str,
    *,
    supports_session_discovery: bool = True,
    supports_chatlas_raw: bool = True,
    chatlas_default_excludes: tuple[str, ...] = (),
    chatlas_default_includes: tuple[str, ...] = (),
) -> ChatProviderSpec:
    home_provider = home_provider_for_name(family_name)
    if home_provider is None:
        raise ValueError(f"unknown provider family: {family_name}")
    return ChatProviderSpec(
        provider_family=home_provider.provider_family,
        home_slots=home_provider.home_slots,
        supports_session_discovery=supports_session_discovery,
        supports_chatlas_raw=supports_chatlas_raw,
        chatlas_default_excludes=chatlas_default_excludes,
        chatlas_default_includes=chatlas_default_includes,
    )


_CANONICAL_CHAT_PROVIDER_SPECS = (
    _chat_provider_spec(
        "copilot-cli",
        chatlas_default_includes=COPILOT_CHATLAS_DEFAULT_INCLUDES,
        chatlas_default_excludes=COPILOT_CHATLAS_DEFAULT_EXCLUDES,
    ),
    _chat_provider_spec(
        "gemini-cli",
        chatlas_default_excludes=GEMINI_CHATLAS_DEFAULT_EXCLUDES,
    ),
    _chat_provider_spec(
        "codex",
        chatlas_default_includes=CODEX_CHATLAS_DEFAULT_INCLUDES,
        chatlas_default_excludes=CODEX_CHATLAS_DEFAULT_EXCLUDES,
    ),
    _chat_provider_spec(
        "claude-code",
        chatlas_default_includes=CLAUDE_CHATLAS_DEFAULT_INCLUDES,
        chatlas_default_excludes=CLAUDE_CHATLAS_DEFAULT_EXCLUDES,
    ),
    _chat_provider_spec(
        "opencode",
        chatlas_default_includes=OPENCODE_CHATLAS_DEFAULT_INCLUDES,
        chatlas_default_excludes=OPENCODE_CHATLAS_DEFAULT_EXCLUDES,
    ),
    _chat_provider_spec(
        "pi",
        chatlas_default_includes=PI_CHATLAS_DEFAULT_INCLUDES,
        chatlas_default_excludes=PI_CHATLAS_DEFAULT_EXCLUDES,
    ),
    _chat_provider_spec(
        "openclaw",
        chatlas_default_excludes=OPENCLAW_CHATLAS_DEFAULT_EXCLUDES,
        chatlas_default_includes=OPENCLAW_CHATLAS_DEFAULT_INCLUDES,
    ),
    _chat_provider_spec(
        "agents",
        supports_session_discovery=False,
    ),
)


@dataclass(frozen=True)
class LegacyProviderConfigSource:
    object_path: tuple[str, ...]
    field_prefix: str


AGENT_INSTANCE_CONFIG_SOURCE = LegacyProviderConfigSource(
    object_path=("agent", "instances"),
    field_prefix="agent.instances",
)


@dataclass(frozen=True)
class LegacyProviderConfigEntry:
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


def legacy_provider_config_entries_from_config(
    config: dict[str, object],
    *,
    source: LegacyProviderConfigSource,
) -> tuple[LegacyProviderConfigEntry, ...]:
    raw_instances = _config_value_at_object_path(config, object_path=source.object_path)
    if raw_instances is None:
        return ()
    if not isinstance(raw_instances, list):
        raise CliError(f"config field {'.'.join(source.object_path)} must be a JSON array")

    entries: list[LegacyProviderConfigEntry] = []
    for index, raw_instance in enumerate(raw_instances):
        if not isinstance(raw_instance, dict):
            raise CliError(f"{source.field_prefix}[{index}] must be a JSON object")
        entries.append(
            LegacyProviderConfigEntry(
                field_prefix=source.field_prefix,
                index=index,
                raw_instance=raw_instance,
            )
        )
    return tuple(entries)


def load_legacy_provider_config_entries(
    *,
    start_path: Path | str = ".",
    sources: tuple[LegacyProviderConfigSource, ...],
) -> tuple[LegacyProviderConfigEntry, ...]:
    entries: list[LegacyProviderConfigEntry] = []
    for config in load_chat_config_documents(start_path=start_path):
        for source in sources:
            entries.extend(
                legacy_provider_config_entries_from_config(
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


def load_legacy_provider_configs(*, start_path: Path | str = ".") -> tuple["LegacyProviderConfig", ...]:
    entries = load_legacy_provider_config_entries(
        start_path=start_path,
        sources=(AGENT_INSTANCE_CONFIG_SOURCE,),
    )
    legacy_provider_configs = tuple(legacy_provider_config_from_config_entry(entry) for entry in entries)
    _validate_unique_legacy_provider_config_ids(legacy_provider_configs)
    return legacy_provider_configs


def select_legacy_provider_configs(
    configured_legacy_configs: tuple["LegacyProviderConfig", ...],
    *,
    selected_instance_ids: tuple[str, ...] | None,
    supported_families: set[str],
    selector_field_name: str,
    unsupported_instance_label: str,
    default_to_supported_families: bool,
) -> tuple["LegacyProviderConfig", ...]:
    if selected_instance_ids is None:
        if not default_to_supported_families:
            return ()
        return tuple(
            legacy_provider_config
            for legacy_provider_config in configured_legacy_configs
            if legacy_provider_config.family in supported_families
        )

    legacy_configs_by_id = {
        legacy_provider_config.instance_id: legacy_provider_config
        for legacy_provider_config in configured_legacy_configs
        if legacy_provider_config.instance_id is not None
    }
    missing_ids = [
        instance_id for instance_id in selected_instance_ids if instance_id not in legacy_configs_by_id
    ]
    if missing_ids:
        suffix = "s" if len(missing_ids) != 1 else ""
        raise CliError(
            f"{selector_field_name} references unknown configured instance id{suffix}: "
            f"{', '.join(missing_ids)}"
        )

    unsupported_ids = [
        instance_id
        for instance_id in selected_instance_ids
        if legacy_configs_by_id[instance_id].family not in supported_families
    ]
    if unsupported_ids:
        suffix = "s" if len(unsupported_ids) != 1 else ""
        raise CliError(
            f"{selector_field_name} references unsupported {unsupported_instance_label} "
            f"instance id{suffix}: {', '.join(unsupported_ids)}"
        )
    return tuple(legacy_configs_by_id[instance_id] for instance_id in selected_instance_ids)


def load_unique_string_list(
    value: object,
    *,
    container_field_name: str,
    item_field_name: str | None = None,
    require_non_empty: bool = False,
) -> tuple[str, ...]:
    normalized_item_field_name = item_field_name or container_field_name
    if not isinstance(value, list):
        array_kind = "non-empty JSON array" if require_non_empty else "JSON array"
        raise CliError(f"{container_field_name} must be a {array_kind}")
    if require_non_empty and not value:
        raise CliError(f"{container_field_name} must be a non-empty JSON array")

    items: list[str] = []
    seen_ids: set[str] = set()
    for index, raw_item in enumerate(value):
        if not isinstance(raw_item, str) or not raw_item.strip():
            raise CliError(f"{normalized_item_field_name}[{index}] must be a non-empty string")
        item = raw_item.strip()
        if item in seen_ids:
            raise CliError(
                f"{normalized_item_field_name} must be unique; duplicate id {item}"
            )
        seen_ids.add(item)
        items.append(item)
    return tuple(items)


def default_legacy_provider_configs(
    *,
    supports_session_discovery_only: bool = False,
) -> tuple["LegacyProviderConfig", ...]:
    instances: list[LegacyProviderConfig] = []
    for provider_spec in canonical_chat_provider_specs():
        if supports_session_discovery_only and not provider_spec.supports_session_discovery:
            continue

        homes: list[tuple[str, Path]] = []
        direct_targets: list[Path] = []
        grep_targets: list[Path] = []
        sqlite_db_paths: list[Path] = []
        anchors: list[LegacyProviderConfigAnchor] = []

        for slot in provider_spec.home_slots:
            home = Path(slot.default_home).expanduser().resolve()
            homes.append((slot.key, home))
            slot_direct_paths, slot_grep_paths, slot_sqlite_db_paths = slot.build_paths(home=home)
            direct_targets.extend(slot_direct_paths)
            grep_targets.extend(slot_grep_paths or slot_direct_paths)
            sqlite_db_paths.extend(slot_sqlite_db_paths)
            anchors.extend(slot.build_anchors(home=home))

        instances.append(
            LegacyProviderConfig(
                family=provider_spec.family,
                homes=tuple(homes),
                direct_targets=_unique_paths(tuple(direct_targets)),
                grep_targets=_unique_paths(tuple(grep_targets)),
                sqlite_db_paths=_unique_paths(tuple(sqlite_db_paths)),
                cli_command=_legacy_provider_default_cli_command(provider_spec.family),
                run_args=_legacy_provider_default_run_args(provider_spec.family),
                default_model=_legacy_provider_default_model(provider_spec.family),
                model_flag=_legacy_provider_default_model_flag(provider_spec.family),
                prompt_flag=_legacy_provider_default_prompt_flag(provider_spec.family),
                anchors=tuple(anchors),
                is_default=True,
            )
        )
    return tuple(instances)


def legacy_provider_config_from_config_entry(entry: LegacyProviderConfigEntry) -> "LegacyProviderConfig":
    raw_instance = entry.raw_instance
    family_name = raw_instance.get("provider")
    if not isinstance(family_name, str) or not family_name:
        raise CliError(f"{entry.field_name('provider')} is required")

    provider_family = canonical_provider_family_for_name(family_name)
    if provider_family is None:
        supported_providers = ", ".join(
            sorted(provider_family.family for provider_family in canonical_provider_families())
        )
        raise CliError(
            f"{entry.field_name('provider')} must be one of: {supported_providers}"
        )

    raw_instance_id = raw_instance.get("id")
    if not isinstance(raw_instance_id, str) or not raw_instance_id.strip():
        raise CliError(f"{entry.field_name('id')} is required")
    instance_id = validate_string_for_path(
        raw_instance_id.strip(),
        field_name=entry.field_name("id"),
    )

    raw_label = raw_instance.get("label")
    if raw_label is None:
        label = instance_id
    elif not isinstance(raw_label, str) or not raw_label.strip():
        raise CliError(f"{entry.field_name('label')} must be a non-empty string")
    else:
        label = raw_label.strip()

    home = raw_instance.get("home")
    raw_homes = raw_instance.get("homes")
    raw_direct_paths = raw_instance.get("direct_paths")
    raw_grep_paths = raw_instance.get("grep_paths")
    raw_sqlite_db_paths = raw_instance.get("sqlite_db_paths")
    raw_sqlite_db_path = raw_instance.get("sqlite_db_path")
    raw_cli_command = raw_instance.get("cli_command")
    raw_run_args = raw_instance.get("run_args")
    raw_env = raw_instance.get("env")
    raw_timeout_sec = raw_instance.get("timeout_sec")
    raw_default_model = raw_instance.get("default_model")
    raw_model_flag = raw_instance.get("model_flag")
    raw_prompt_flag = raw_instance.get("prompt_flag")
    raw_live_usage_refresh = raw_instance.get("live_usage_refresh")
    raw_usage_progression_limit = raw_instance.get("usage_progression_limit")
    raw_includes = raw_instance.get("includes")
    raw_excludes = raw_instance.get("excludes")

    if home is not None and raw_homes is not None:
        raise CliError(f"{entry.item_path()} must not define both home and homes")
    if raw_sqlite_db_path is not None and raw_sqlite_db_paths is not None:
        raise CliError(
            f"{entry.item_path()} must not define both sqlite_db_path and sqlite_db_paths"
        )

    provider_spec = canonical_chat_provider_spec_for_name(family_name)
    direct_paths = _load_optional_string_tuple(
        raw_direct_paths,
        field_name=entry.field_name("direct_paths"),
    )
    grep_paths = _load_optional_string_tuple(
        raw_grep_paths,
        field_name=entry.field_name("grep_paths"),
    )
    sqlite_db_paths = _load_optional_string_tuple(
        raw_sqlite_db_paths if raw_sqlite_db_paths is not None else raw_sqlite_db_path,
        field_name=entry.field_name("sqlite_db_paths"),
    )
    homes = _load_optional_string_mapping(
        raw_homes,
        field_name=entry.field_name("homes"),
    )
    cli_command = (
        _load_string_argv(
            raw_cli_command,
            field_name=entry.field_name("cli_command"),
        )
        if raw_cli_command is not None
        else _legacy_provider_default_cli_command(family_name)
    )
    run_args = (
        _load_string_argv(
            raw_run_args,
            field_name=entry.field_name("run_args"),
        )
        if raw_run_args is not None
        else _legacy_provider_default_run_args(family_name)
    )
    env = _load_string_mapping(
        raw_env,
        field_name=entry.field_name("env"),
    )
    if raw_timeout_sec is None:
        timeout_sec = None
    elif isinstance(raw_timeout_sec, bool) or not isinstance(raw_timeout_sec, int) or raw_timeout_sec < 1:
        raise CliError(f"{entry.field_name('timeout_sec')} must be an integer greater than 0")
    else:
        timeout_sec = raw_timeout_sec
    if raw_default_model is None:
        default_model = _legacy_provider_default_model(family_name)
    elif not isinstance(raw_default_model, str) or not raw_default_model.strip():
        raise CliError(f"{entry.field_name('default_model')} must be a non-empty string")
    else:
        default_model = raw_default_model.strip()
    if raw_model_flag is None:
        model_flag = _legacy_provider_default_model_flag(family_name)
    elif not isinstance(raw_model_flag, str) or not raw_model_flag.strip():
        raise CliError(f"{entry.field_name('model_flag')} must be a non-empty string")
    else:
        model_flag = raw_model_flag.strip()
    if raw_prompt_flag is None:
        prompt_flag = _legacy_provider_default_prompt_flag(family_name)
    elif not isinstance(raw_prompt_flag, str) or not raw_prompt_flag.strip():
        raise CliError(f"{entry.field_name('prompt_flag')} must be a non-empty string")
    else:
        prompt_flag = raw_prompt_flag.strip()
    if raw_live_usage_refresh is None:
        live_usage_refresh = None
    elif not isinstance(raw_live_usage_refresh, bool):
        raise CliError(f"{entry.field_name('live_usage_refresh')} must be a boolean")
    else:
        live_usage_refresh = raw_live_usage_refresh
    if raw_usage_progression_limit is None:
        usage_progression_limit = None
    elif not isinstance(raw_usage_progression_limit, str) or not raw_usage_progression_limit.strip():
        raise CliError(f"{entry.field_name('usage_progression_limit')} must be a non-empty string")
    else:
        usage_progression_limit = raw_usage_progression_limit.strip()
    includes = _load_optional_string_tuple(
        raw_includes,
        field_name=entry.field_name("includes"),
    )
    excludes = _load_optional_string_tuple(
        raw_excludes,
        field_name=entry.field_name("excludes"),
    )

    normalized_homes: list[tuple[str, Path]] = []
    resolved_direct_targets: tuple[Path, ...] = ()
    resolved_grep_targets: tuple[Path, ...] = ()
    resolved_sqlite_db_paths: tuple[Path, ...] = ()
    anchors: tuple[LegacyProviderConfigAnchor, ...] = ()

    if home is not None or homes:
        if provider_spec is None:
            raise CliError(
                f"{entry.item_path()} does not support home-based configuration for provider {family_name}"
            )
        if direct_paths or grep_paths or sqlite_db_paths:
            raise CliError(
                f"{entry.item_path()} must define either home/homes or explicit paths, not both"
            )

        if home is not None:
            if len(provider_spec.home_slots) != 1:
                supported_keys = ", ".join(slot.key for slot in provider_spec.home_slots)
                raise CliError(
                    f"{entry.field_name('home')} is only supported for providers with a single home root; "
                    f"use {entry.field_name('homes')} with keys: {supported_keys}"
                )
            resolved_homes = {
                provider_spec.home_slots[0].key: _normalize_provider_home(
                    home,
                    field_name=entry.field_name("home"),
                )
            }
        else:
            if len(provider_spec.home_slots) == 1:
                raise CliError(
                    f"{entry.field_name('homes')} is only supported for providers with multiple home roots; "
                    f"use {entry.field_name('home')}"
                )
            resolved_homes = homes

        supported_slots = {slot.key: slot for slot in provider_spec.home_slots}
        unsupported_keys = sorted(key for key in resolved_homes if key not in supported_slots)
        if unsupported_keys:
            supported_keys = ", ".join(slot.key for slot in provider_spec.home_slots)
            raise CliError(
                f"{entry.field_name('homes')} contains unsupported keys for provider {family_name}: "
                f"{', '.join(unsupported_keys)} (supported: {supported_keys})"
            )

        direct_targets_list: list[Path] = []
        grep_targets_list: list[Path] = []
        sqlite_db_paths_list: list[Path] = []
        anchors_list: list[LegacyProviderConfigAnchor] = []
        for slot in provider_spec.home_slots:
            raw_home = resolved_homes.get(slot.key)
            if raw_home is None:
                continue
            field_name = entry.field_name("home") if home is not None else f"{entry.field_name('homes')}.{slot.key}"
            normalized_home = Path(
                _normalize_provider_home(
                    raw_home,
                    field_name=field_name,
                )
            ).expanduser().resolve()
            normalized_homes.append((slot.key, normalized_home))
            slot_direct_paths, slot_grep_paths, slot_sqlite_db_paths = slot.build_paths(home=normalized_home)
            direct_targets_list.extend(slot_direct_paths)
            grep_targets_list.extend(slot_grep_paths or slot_direct_paths)
            sqlite_db_paths_list.extend(slot_sqlite_db_paths)
            anchors_list.extend(slot.build_anchors(home=normalized_home))

        resolved_direct_targets = _unique_paths(tuple(direct_targets_list))
        resolved_grep_targets = _unique_paths(tuple(grep_targets_list))
        resolved_sqlite_db_paths = _unique_paths(tuple(sqlite_db_paths_list))
        anchors = tuple(anchors_list)
    elif direct_paths or sqlite_db_paths:
        resolved_direct_targets = _resolve_raw_paths(direct_paths)
        resolved_grep_targets = _resolve_raw_paths(grep_paths) if grep_paths else resolved_direct_targets
        resolved_sqlite_db_paths = _resolve_raw_paths(sqlite_db_paths)
        anchors = _build_explicit_legacy_provider_config_anchors(
            direct_targets=resolved_direct_targets,
            sqlite_db_paths=resolved_sqlite_db_paths,
        )

    return LegacyProviderConfig(
        family=provider_family.family,
        instance_id=instance_id,
        label=label,
        homes=tuple(normalized_homes),
        direct_targets=resolved_direct_targets,
        grep_targets=resolved_grep_targets,
        sqlite_db_paths=resolved_sqlite_db_paths,
        cli_command=cli_command,
        run_args=run_args,
        env=env,
        timeout_sec=timeout_sec,
        default_model=default_model,
        model_flag=model_flag,
        prompt_flag=prompt_flag,
        live_usage_refresh=live_usage_refresh,
        usage_progression_limit=usage_progression_limit,
        includes=includes,
        excludes=excludes,
        anchors=anchors,
        is_default=False,
    )


def _validate_unique_legacy_provider_config_ids(legacy_provider_configs: tuple["LegacyProviderConfig", ...]) -> None:
    seen_legacy_configs: dict[str, LegacyProviderConfig] = {}
    for legacy_provider_config in legacy_provider_configs:
        if legacy_provider_config.instance_id is None:
            raise CliError("agent.instances ids must not be empty")
        existing = seen_legacy_configs.get(legacy_provider_config.instance_id)
        if existing is None:
            seen_legacy_configs[legacy_provider_config.instance_id] = legacy_provider_config
            continue
        raise CliError(
            "agent.instances ids must be unique; "
            f"duplicate id {legacy_provider_config.instance_id} for providers "
            f"{existing.family} and {legacy_provider_config.family}"
        )


def _legacy_provider_config_fingerprint(
    *,
    family: str,
    anchors: tuple[LegacyProviderConfigAnchor, ...],
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


def _normalize_provider_home(home: object, *, field_name: str) -> str:
    if not isinstance(home, str) or not home.strip():
        raise CliError(f"{field_name} must be a non-empty string")
    return home.strip()


def _load_string_argv(value: object, *, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise CliError(f"{field_name} must be a JSON array")

    argv: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise CliError(f"{field_name}[{index}] must be a non-empty string")
        argv.append(_expand_user_home(item.strip()))
    return tuple(argv)


def _load_string_mapping(value: object, *, field_name: str) -> tuple[tuple[str, str], ...]:
    if value is None:
        return ()
    if not isinstance(value, dict):
        raise CliError(f"{field_name} must be a JSON object")

    items: list[tuple[str, str]] = []
    for key, item in value.items():
        if not isinstance(key, str) or not key:
            raise CliError(f"{field_name} keys must be non-empty strings")
        if not isinstance(item, str):
            raise CliError(f"{field_name}.{key} must be a string")
        items.append((key, _expand_user_home(item)))
    return tuple(items)


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


def _expand_user_home(value: str) -> str:
    if value.startswith("~"):
        return str(Path(value).expanduser())
    return value


def _resolve_raw_paths(raw_paths: tuple[str, ...]) -> tuple[Path, ...]:
    return _unique_paths(tuple(Path(raw_path).expanduser().resolve() for raw_path in raw_paths))


def _build_explicit_legacy_provider_config_anchors(
    *,
    direct_targets: tuple[Path, ...],
    sqlite_db_paths: tuple[Path, ...],
) -> tuple["LegacyProviderConfigAnchor", ...]:
    anchors = [
        LegacyProviderConfigAnchor(role=f"direct_target_{index + 1}", path=path)
        for index, path in enumerate(direct_targets)
    ]
    anchors.extend(
        LegacyProviderConfigAnchor(role=f"sqlite_db_{index + 1}", path=path)
        for index, path in enumerate(sqlite_db_paths)
    )
    return tuple(anchors)



@dataclass(frozen=True)
class LegacyProviderConfig:
    family: str
    instance_id: str | None = None
    label: str | None = None
    homes: tuple[tuple[str, Path], ...] = ()
    direct_targets: tuple[Path, ...] = ()
    grep_targets: tuple[Path, ...] = ()
    sqlite_db_paths: tuple[Path, ...] = ()
    cli_command: tuple[str, ...] = ()
    run_args: tuple[str, ...] = ()
    env: tuple[tuple[str, str], ...] = ()
    timeout_sec: int | None = None
    default_model: str | None = None
    model_flag: str | None = None
    prompt_flag: str | None = None
    live_usage_refresh: bool | None = None
    usage_progression_limit: str | None = None
    includes: tuple[str, ...] = ()
    excludes: tuple[str, ...] = ()
    anchors: tuple[LegacyProviderConfigAnchor, ...] = ()
    is_default: bool = False

    def homes_map(self) -> dict[str, Path]:
        return {key: path for key, path in self.homes}

    @property
    def fingerprint(self) -> str:
        if self.anchors:
            return _legacy_provider_config_fingerprint(
                family=self.family,
                anchors=self.anchors,
            )

        fallback_anchors = tuple(
            LegacyProviderConfigAnchor(role=f"direct_target_{index + 1}", path=path)
            for index, path in enumerate(self.direct_targets)
        ) + tuple(
            LegacyProviderConfigAnchor(role=f"sqlite_db_{index + 1}", path=path)
            for index, path in enumerate(self.sqlite_db_paths)
        )
        return _legacy_provider_config_fingerprint(
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
            self.run_args,
            self.env,
            self.timeout_sec,
            self.default_model,
            self.model_flag,
            self.prompt_flag,
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
        if self.run_args:
            payload["run_args"] = list(self.run_args)
        if self.env:
            payload["env"] = {key: value for key, value in self.env}
        if self.timeout_sec is not None:
            payload["timeout_sec"] = self.timeout_sec
        if self.default_model is not None:
            payload["default_model"] = self.default_model
        if self.model_flag is not None:
            payload["model_flag"] = self.model_flag
        if self.prompt_flag is not None:
            payload["prompt_flag"] = self.prompt_flag
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
    "canonical_chat_provider_spec_for_name",
    "canonical_chat_provider_specs",
    "canonical_provider_families",
    "canonical_provider_family_for_name",
    "ChatProviderSpec",
    "AGENT_INSTANCE_CONFIG_SOURCE",
    "default_legacy_provider_configs",
    "load_chat_config_documents",
    "load_legacy_provider_configs",
    "load_unique_string_list",
    "load_legacy_provider_config_entries",
    "ProviderFamily",
    "ProviderHomeSlot",
    "LegacyProviderConfigEntry",
    "LegacyProviderConfigSource",
    "LegacyProviderConfig",
    "LegacyProviderConfigAnchor",
    "legacy_provider_config_from_config_entry",
    "legacy_provider_config_entries_from_config",
    "require_canonical_provider_family",
    "select_legacy_provider_configs",
]
