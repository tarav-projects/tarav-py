# $kw: --from Agent.Profile --from Provider.Instance
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from tarav._core.errors import CliError
from tarav._core.path_validation import validate_string_for_path
from tarav._core.project import (
    tarav_home_dir,
    find_agentos_project_root,
    global_config_path,
    load_global_config,
    load_project_config,
    project_config_path,
)
from tarav._core.sequences import _unique_paths
from tarav.agent.primitives import AgentConfig, default_agent_ping_config
from tarav.agent.providers import (
    ProviderHomeAnchor,
    canonical_provider_families,
    canonical_provider_family_for_name,
    require_canonical_provider_family,
)

from ._config_entry import (
    _load_json_object,
    _load_string_argv,
    _validate_unique_agent_config_ids,
    _write_json_file,
    agent_config_from_config_entry,
    agent_config_with_provider_config,
    default_agent_ping_config_with_model as default_agent_ping_config_with_model,
    validate_provider_profile,
)
from ._config_models import (
    AGENT_ACCOUNT_POLICIES,
    AGENT_ACCOUNT_POLICY_HOME_CURRENT,
    AGENT_ACCOUNT_POLICY_PROFILE_DEFAULT,
    AGENT_PROFILE_CONFIG_SOURCE,
    AGENT_PROVIDER_CONFIG_FIELD_PREFIX,
    AGENT_PROVIDER_CONFIG_OBJECT_PATH,
    AgentConfigEntry,
    AgentConfigSource,
    AgentProviderConfig,
    ChatProviderSpec,
    ProviderFamily,
    ProviderHomeSpec,
    _agent_default_model,
    _agent_default_ping_model as _agent_default_ping_model,
    _agent_default_run_args,
    canonical_chat_provider_spec_for_name,
    canonical_chat_provider_specs,
)


def load_chat_config_documents(
    *, start_path: Path | str = "."
) -> tuple[dict[str, object], ...]:
    configs: list[dict[str, object]] = []

    global_path = global_config_path(tarav_home_dir())
    if global_path.exists():
        configs.append(load_global_config(global_path))

    project_root = find_agentos_project_root(start_path)
    if project_root is not None:
        project_path = project_config_path(project_root)
        if project_path.exists():
            configs.append(load_project_config(project_path))

    return tuple(configs)


def agent_config_entries_from_config(
    config: dict[str, object],
    *,
    source: AgentConfigSource,
) -> tuple[AgentConfigEntry, ...]:
    raw_profiles = _config_value_at_object_path(config, object_path=source.object_path)
    if raw_profiles is None:
        return ()
    if not isinstance(raw_profiles, list):
        raise CliError(
            f"config field {'.'.join(source.object_path)} must be a JSON array"
        )

    entries: list[AgentConfigEntry] = []
    for index, raw_profile in enumerate(raw_profiles):
        if not isinstance(raw_profile, dict):
            raise CliError(f"{source.field_prefix}[{index}] must be a JSON object")
        entries.append(
            AgentConfigEntry(
                field_prefix=source.field_prefix,
                index=index,
                raw_profile=raw_profile,
            )
        )
    return tuple(entries)


def load_agent_config_entries(
    *,
    start_path: Path | str = ".",
    sources: tuple[AgentConfigSource, ...],
) -> tuple[AgentConfigEntry, ...]:
    entries: list[AgentConfigEntry] = []
    for config in load_chat_config_documents(start_path=start_path):
        for source in sources:
            entries.extend(
                agent_config_entries_from_config(
                    config,
                    source=source,
                )
            )
    return tuple(entries)


def _config_value_at_object_path(
    config: dict[str, object], *, object_path: tuple[str, ...]
) -> object | None:
    if not object_path:
        return config

    current: object = config
    current_path: list[str] = []
    for key in object_path[:-1]:
        current_path.append(key)
        if not isinstance(current, dict):
            raise CliError(
                f"config field {'.'.join(current_path)} must be a JSON object"
            )
        next_value = current.get(key)
        if next_value is None:
            return None
        if not isinstance(next_value, dict):
            raise CliError(
                f"config field {'.'.join(current_path)} must be a JSON object"
            )
        current = next_value

    if not isinstance(current, dict):
        raise CliError(
            f"config field {'.'.join(object_path[:-1])} must be a JSON object"
        )
    return current.get(object_path[-1])


def load_agent_configs(*, start_path: Path | str = ".") -> tuple["AgentConfig", ...]:
    provider_configs = load_agent_provider_configs(start_path=start_path)
    profile_entries = load_agent_profile_entries()
    agent_configs = tuple(
        agent_config_from_config_entry(entry, provider_configs=provider_configs)
        for entry in profile_entries
    )
    _validate_unique_agent_config_ids(agent_configs)
    return agent_configs


def profiles_root() -> Path:
    return tarav_home_dir() / "profiles"


def profile_path(name: str) -> Path:
    normalized_name = validate_string_for_path(name, field_name="profile")
    return profiles_root() / f"{normalized_name}.json"


def load_agent_profile_entries() -> tuple[AgentConfigEntry, ...]:
    root = profiles_root()
    if not root.exists():
        return ()
    entries: list[AgentConfigEntry] = []
    for index, path in enumerate(sorted(root.glob("*.json"))):
        profile_name = path.stem
        validate_string_for_path(profile_name, field_name="profile")
        payload = _load_json_object(path, description="agent profile")
        raw_id = payload.get("id")
        if raw_id is None:
            payload["id"] = profile_name
        elif raw_id != profile_name:
            raise CliError(f"agent profile id must match filename: {path}")
        entries.append(
            AgentConfigEntry(
                field_prefix="agent.profiles",
                index=index,
                raw_profile=payload,
            )
        )
    return tuple(entries)


def load_agent_profile(name: str) -> AgentConfig:
    provider_configs = load_agent_provider_configs()
    path = profile_path(name)
    if not path.exists():
        raise CliError(f"agent profile not found: {name}")
    payload = _load_json_object(path, description="agent profile")
    profile_name = path.stem
    raw_id = payload.get("id")
    if raw_id is None:
        payload["id"] = profile_name
    elif raw_id != profile_name:
        raise CliError(f"agent profile id must match filename: {path}")
    return agent_config_from_config_entry(
        AgentConfigEntry(
            field_prefix="agent.profiles",
            index=0,
            raw_profile=payload,
        ),
        provider_configs=provider_configs,
    )


def write_agent_profile(config: AgentConfig) -> Path:
    if config.profile_id is None:
        raise CliError("agent profile id is required")
    path = profile_path(config.profile_id)
    payload: dict[str, object] = {
        "schema_version": 1,
        "id": config.profile_id,
        "provider": config.provider,
    }
    if config.homes:
        payload["homes"] = [str(home) for home in config.homes]
    if config.accounts:
        payload["accounts"] = [account.account for account in config.accounts]
    if config.account_policy != AGENT_ACCOUNT_POLICY_PROFILE_DEFAULT:
        payload["account_policy"] = config.account_policy
    if config.default_model is not None:
        payload["default_model"] = config.default_model
    if config.run_args:
        payload["run_args"] = list(config.run_args)
    if config.env:
        payload["env"] = {key: value for key, value in config.env}
    if config.ping_config != default_agent_ping_config():
        payload["ping"] = config.ping_config.summary()
    _write_json_file(path, payload)
    return path


def update_agent_profile_account(
    name: str, account: str
) -> tuple[AgentConfig, str | None, Path]:
    config = load_agent_profile(name)
    normalized_account = validate_string_for_path(account, field_name="account")
    path = profile_path(name)
    payload = _load_json_object(path, description="agent profile")
    previous = config.account.account if config.account is not None else None
    existing_accounts = [
        item.account for item in config.accounts if item.account != normalized_account
    ]
    payload["accounts"] = [normalized_account, *existing_accounts]
    _write_json_file(path, payload)
    return load_agent_profile(name), previous, path


def load_agent_provider_configs(
    *, start_path: Path | str = "."
) -> dict[str, AgentProviderConfig]:
    provider_configs: dict[str, AgentProviderConfig] = {}
    for config in load_chat_config_documents(start_path=start_path):
        provider_configs.update(agent_provider_configs_from_config(config))
    return provider_configs


def agent_provider_configs_from_config(
    config: dict[str, object],
) -> dict[str, AgentProviderConfig]:
    raw_providers = _config_value_at_object_path(
        config, object_path=AGENT_PROVIDER_CONFIG_OBJECT_PATH
    )
    if raw_providers is None:
        return {}
    if not isinstance(raw_providers, dict):
        raise CliError(
            f"config field {AGENT_PROVIDER_CONFIG_FIELD_PREFIX} must be a JSON object"
        )

    provider_configs: dict[str, AgentProviderConfig] = {}
    for raw_provider, raw_provider_config in raw_providers.items():
        if not isinstance(raw_provider, str) or not raw_provider.strip():
            raise CliError("agent.providers contains an invalid provider key")
        provider = raw_provider.strip()
        if canonical_provider_family_for_name(provider) is None:
            supported_providers = ", ".join(
                sorted(
                    provider_family.family
                    for provider_family in canonical_provider_families()
                )
            )
            raise CliError(
                f"agent.providers.{provider} must be one of: {supported_providers}"
            )
        if not isinstance(raw_provider_config, dict):
            raise CliError(
                f"{AGENT_PROVIDER_CONFIG_FIELD_PREFIX}.{provider} must be a JSON object"
            )

        raw_cli_command = raw_provider_config.get("cli_command")
        cli_command = (
            _load_string_argv(
                raw_cli_command,
                field_name=agent_provider_config_field_name(provider, "cli_command"),
            )
            if raw_cli_command is not None
            else ()
        )
        provider_configs[provider] = AgentProviderConfig(
            cli_command=cli_command,
        )
    return provider_configs


def agent_provider_config_field_name(provider: str, field: str) -> str:
    return f"{AGENT_PROVIDER_CONFIG_FIELD_PREFIX}.{provider}.{field}"


def select_agent_configs(
    configured_agent_configs: tuple["AgentConfig", ...],
    *,
    selected_profile_ids: tuple[str, ...] | None,
    supported_families: set[str],
    selector_field_name: str,
    unsupported_profile_label: str,
    default_to_supported_families: bool,
) -> tuple["AgentConfig", ...]:
    if selected_profile_ids is None:
        if not default_to_supported_families:
            return ()
        return tuple(
            agent_config
            for agent_config in configured_agent_configs
            if agent_config.provider in supported_families
        )

    agent_configs_by_id = {
        agent_config.profile_id: agent_config
        for agent_config in configured_agent_configs
        if agent_config.profile_id is not None
    }
    missing_ids = [
        profile_id
        for profile_id in selected_profile_ids
        if profile_id not in agent_configs_by_id
    ]
    if missing_ids:
        suffix = "s" if len(missing_ids) != 1 else ""
        raise CliError(
            f"{selector_field_name} references unknown configured profile id{suffix}: "
            f"{', '.join(missing_ids)}"
        )

    unsupported_ids = [
        profile_id
        for profile_id in selected_profile_ids
        if agent_configs_by_id[profile_id].provider not in supported_families
    ]
    if unsupported_ids:
        suffix = "s" if len(unsupported_ids) != 1 else ""
        raise CliError(
            f"{selector_field_name} references unsupported {unsupported_profile_label} "
            f"profile id{suffix}: {', '.join(unsupported_ids)}"
        )
    return tuple(agent_configs_by_id[profile_id] for profile_id in selected_profile_ids)


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
            raise CliError(
                f"{normalized_item_field_name}[{index}] must be a non-empty string"
            )
        item = raw_item.strip()
        if item in seen_ids:
            raise CliError(
                f"{normalized_item_field_name} must be unique; duplicate id {item}"
            )
        seen_ids.add(item)
        items.append(item)
    return tuple(items)


def default_agent_configs(
    *,
    supports_session_discovery_only: bool = False,
) -> tuple["AgentConfig", ...]:
    agent_configs: list[AgentConfig] = []
    for provider_spec in canonical_chat_provider_specs():
        if (
            supports_session_discovery_only
            and not provider_spec.supports_session_discovery
        ):
            continue

        direct_targets: list[Path] = []
        grep_targets: list[Path] = []
        sqlite_db_paths: list[Path] = []
        anchors: list[ProviderHomeAnchor] = []

        home_spec = provider_spec.home_spec
        home = Path(home_spec.default_home).expanduser().resolve()
        home_direct_paths, home_grep_paths, home_sqlite_db_paths = (
            home_spec.build_paths(home=home)
        )
        direct_targets.extend(home_direct_paths)
        grep_targets.extend(home_grep_paths or home_direct_paths)
        sqlite_db_paths.extend(home_sqlite_db_paths)
        anchors.extend(home_spec.build_anchors(home=home))

        agent_configs.append(
            AgentConfig(
                provider=provider_spec.family,
                home=home,
                homes=(home,),
                direct_targets=_unique_paths(tuple(direct_targets)),
                grep_targets=_unique_paths(tuple(grep_targets)),
                sqlite_db_paths=_unique_paths(tuple(sqlite_db_paths)),
                cli_command=(),
                run_args=_agent_default_run_args(provider_spec.family),
                default_model=_agent_default_model(provider_spec.family),
                identity_anchors=tuple(anchors),
                is_default=True,
            )
        )
    return tuple(agent_configs)


def agent_config_with_home_override(
    config: AgentConfig, *, home: Path | str
) -> AgentConfig:
    provider_spec = canonical_chat_provider_spec_for_name(config.provider)
    if provider_spec is None:
        raise CliError(f"--home is not supported for provider {config.provider}")

    home_spec = provider_spec.home_spec
    normalized_home = Path(home).expanduser().resolve()
    direct_targets, grep_targets, sqlite_db_paths = home_spec.build_paths(
        home=normalized_home
    )
    return replace(
        config,
        home=normalized_home,
        homes=config.homes or (normalized_home,),
        direct_targets=_unique_paths(tuple(direct_targets)),
        grep_targets=_unique_paths(tuple(grep_targets or direct_targets)),
        sqlite_db_paths=_unique_paths(tuple(sqlite_db_paths)),
        identity_anchors=tuple(home_spec.build_anchors(home=normalized_home)),
    )


__all__ = [
    "canonical_chat_provider_spec_for_name",
    "canonical_chat_provider_specs",
    "canonical_provider_families",
    "canonical_provider_family_for_name",
    "ChatProviderSpec",
    "AGENT_PROFILE_CONFIG_SOURCE",
    "default_agent_configs",
    "load_chat_config_documents",
    "load_agent_configs",
    "validate_provider_profile",
    "load_agent_profile",
    "load_agent_profile_entries",
    "load_unique_string_list",
    "load_agent_config_entries",
    "ProviderFamily",
    "ProviderHomeSpec",
    "AgentConfigEntry",
    "AgentProviderConfig",
    "AgentConfigSource",
    "AgentConfig",
    "AGENT_ACCOUNT_POLICIES",
    "AGENT_ACCOUNT_POLICY_HOME_CURRENT",
    "AGENT_ACCOUNT_POLICY_PROFILE_DEFAULT",
    "agent_config_with_provider_config",
    "agent_config_with_home_override",
    "agent_provider_config_field_name",
    "agent_provider_configs_from_config",
    "ProviderHomeAnchor",
    "agent_config_from_config_entry",
    "agent_config_entries_from_config",
    "load_agent_provider_configs",
    "profile_path",
    "profiles_root",
    "require_canonical_provider_family",
    "select_agent_configs",
    "update_agent_profile_account",
    "write_agent_profile",
]
