from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from pathlib import Path

from agentos._core.errors import CliError
from agentos._core.sequences import _unique_paths
from agentos._core.path_validation import validate_string_for_path
from agentos.agent.account_status import AgentAccountContext
from agentos.agent.primitives import (
    AgentConfig,
    AgentPingConfig,
    default_agent_ping_config,
)
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
    ProviderHomeAnchor,
    ProviderHomeSpec,
    canonical_provider_families,
    canonical_provider_family_for_name,
    require_canonical_provider_family,
)
from agentos.home.providers import home_provider_for_name

AGENT_ACCOUNT_POLICY_PROFILE_DEFAULT = "profile-default"
AGENT_ACCOUNT_POLICY_HOME_CURRENT = "home-current"
AGENT_ACCOUNT_POLICIES = (
    AGENT_ACCOUNT_POLICY_PROFILE_DEFAULT,
    AGENT_ACCOUNT_POLICY_HOME_CURRENT,
)


@dataclass(frozen=True)
class ChatProviderSpec:
    provider_family: ProviderFamily
    home_spec: ProviderHomeSpec
    supports_session_discovery: bool = True

    @property
    def family(self) -> str:
        return self.provider_family.family


_CANONICAL_CHAT_PROVIDER_SPECS: tuple[ChatProviderSpec, ...] = ()


def _agent_default_run_args(family_name: str) -> tuple[str, ...]:
    if family_name == "codex":
        return ("--dangerously-bypass-approvals-and-sandbox",)
    if family_name == "copilot-cli":
        return ("--allow-all-tools", "--no-ask-user")
    if family_name == "opencode":
        return ("run",)
    return ()


def _agent_default_model(family_name: str) -> str | None:
    if family_name == "codex":
        return "gpt-5.4"
    return None


def _agent_default_ping_model(family_name: str) -> str | None:
    if family_name == "claude-code":
        return "haiku"
    if family_name == "codex":
        return "gpt-5.4-mini"
    if family_name == "pi":
        return "gpt-5.4-mini"
    return None


def _agent_default_model_flag(family_name: str) -> str | None:
    if family_name == "claude-code":
        return "--model"
    if family_name == "codex":
        return "--model"
    if family_name == "copilot-cli":
        return "--model"
    if family_name == "opencode":
        return "--model"
    if family_name == "pi":
        return "--model"
    return None


def _agent_default_prompt_flag(family_name: str) -> str | None:
    if family_name == "claude-code":
        return "-p"
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
) -> ChatProviderSpec:
    home_provider = home_provider_for_name(family_name)
    if home_provider is None:
        raise ValueError(f"unknown provider family: {family_name}")
    return ChatProviderSpec(
        provider_family=home_provider.provider_family,
        home_spec=home_provider.home_spec,
        supports_session_discovery=supports_session_discovery,
    )


_CANONICAL_CHAT_PROVIDER_SPECS = (
    _chat_provider_spec("copilot-cli"),
    _chat_provider_spec("gemini-cli"),
    _chat_provider_spec("codex"),
    _chat_provider_spec("claude-code"),
    _chat_provider_spec("opencode"),
    _chat_provider_spec("pi"),
    _chat_provider_spec("openclaw"),
)


@dataclass(frozen=True)
class AgentConfigSource:
    object_path: tuple[str, ...]
    field_prefix: str


AGENT_PROFILE_CONFIG_SOURCE = AgentConfigSource(
    object_path=(),
    field_prefix="agent.profiles",
)

AGENT_PROVIDER_CONFIG_OBJECT_PATH = ("agent", "providers")
AGENT_PROVIDER_CONFIG_FIELD_PREFIX = "agent.providers"


@dataclass(frozen=True)
class AgentProviderConfig:
    cli_command: tuple[str, ...] = ()


@dataclass(frozen=True)
class AgentConfigEntry:
    field_prefix: str
    index: int
    raw_profile: dict[str, object]

    def item_path(self) -> str:
        return f"{self.field_prefix}[{self.index}]"

    def field_name(self, field: str) -> str:
        return f"{self.item_path()}.{field}"


def load_chat_config_documents(
    *, start_path: Path | str = "."
) -> tuple[dict[str, object], ...]:
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
    return agentos_home_dir() / "profiles"


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
    if config.ping != default_agent_ping_config():
        payload["ping"] = config.ping.summary()
    _write_json_file(path, payload)
    return path


def update_agent_profile_account(name: str, account: str) -> tuple[AgentConfig, str | None, Path]:
    config = load_agent_profile(name)
    normalized_account = validate_string_for_path(account, field_name="account")
    path = profile_path(name)
    payload = _load_json_object(path, description="agent profile")
    previous = config.account.account if config.account is not None else None
    existing_accounts = [
        item.account
        for item in config.accounts
        if item.account != normalized_account
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
    return tuple(
        agent_configs_by_id[profile_id] for profile_id in selected_profile_ids
    )


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
                model_flag=_agent_default_model_flag(provider_spec.family),
                prompt_flag=_agent_default_prompt_flag(provider_spec.family),
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


def agent_config_from_config_entry(
    entry: AgentConfigEntry,
    *,
    provider_configs: dict[str, AgentProviderConfig] | None = None,
) -> "AgentConfig":
    raw_profile = entry.raw_profile
    family_name = raw_profile.get("provider")
    if not isinstance(family_name, str) or not family_name:
        raise CliError(f"{entry.field_name('provider')} is required")

    provider_family = canonical_provider_family_for_name(family_name)
    if provider_family is None:
        supported_providers = ", ".join(
            sorted(
                provider_family.family
                for provider_family in canonical_provider_families()
            )
        )
        raise CliError(
            f"{entry.field_name('provider')} must be one of: {supported_providers}"
        )

    raw_profile_id = raw_profile.get("id")
    if not isinstance(raw_profile_id, str) or not raw_profile_id.strip():
        raise CliError(f"{entry.field_name('id')} is required")
    profile_id = validate_string_for_path(
        raw_profile_id.strip(),
        field_name=entry.field_name("id"),
    )

    raw_label = raw_profile.get("label")
    if raw_label is None:
        label = profile_id
    elif not isinstance(raw_label, str) or not raw_label.strip():
        raise CliError(f"{entry.field_name('label')} must be a non-empty string")
    else:
        label = raw_label.strip()

    _reject_removed_profile_fields(entry, raw_profile)
    raw_homes = raw_profile.get("homes")
    raw_direct_paths = raw_profile.get("direct_paths")
    raw_grep_paths = raw_profile.get("grep_paths")
    raw_sqlite_db_paths = raw_profile.get("sqlite_db_paths")
    raw_sqlite_db_path = raw_profile.get("sqlite_db_path")
    raw_cli_command = raw_profile.get("cli_command")
    raw_run_args = raw_profile.get("run_args")
    raw_env = raw_profile.get("env")
    raw_timeout_sec = raw_profile.get("timeout_sec")
    raw_default_model = raw_profile.get("default_model")
    raw_accounts = raw_profile.get("accounts")
    raw_account_policy = raw_profile.get("account_policy")
    raw_model_flag = raw_profile.get("model_flag")
    raw_prompt_flag = raw_profile.get("prompt_flag")
    raw_ping = raw_profile.get("ping")
    raw_fingerprint = raw_profile.get("fingerprint")

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
    cli_command = _load_agent_cli_command(
        raw_cli_command,
        field_name=entry.field_name("cli_command"),
        provider_config=(provider_configs or {}).get(provider_family.family),
    )
    run_args = (
        _load_string_argv(
            raw_run_args,
            field_name=entry.field_name("run_args"),
        )
        if raw_run_args is not None
        else _agent_default_run_args(family_name)
    )
    env = _load_string_mapping(
        raw_env,
        field_name=entry.field_name("env"),
    )
    if raw_timeout_sec is None:
        timeout_sec = None
    elif (
        isinstance(raw_timeout_sec, bool)
        or not isinstance(raw_timeout_sec, int)
        or raw_timeout_sec < 1
    ):
        raise CliError(
            f"{entry.field_name('timeout_sec')} must be an integer greater than 0"
        )
    else:
        timeout_sec = raw_timeout_sec
    if raw_default_model is None:
        default_model = _agent_default_model(family_name)
    elif not isinstance(raw_default_model, str) or not raw_default_model.strip():
        raise CliError(
            f"{entry.field_name('default_model')} must be a non-empty string"
        )
    else:
        default_model = raw_default_model.strip()
    accounts = _load_agent_account_contexts(
        raw_accounts,
        provider=provider_family.family,
        field_name=entry.field_name("accounts"),
    )
    account = accounts[0] if accounts else None
    account_policy = _load_agent_account_policy(
        raw_account_policy,
        field_name=entry.field_name("account_policy"),
    )
    if raw_model_flag is None:
        model_flag = _agent_default_model_flag(family_name)
    elif not isinstance(raw_model_flag, str) or not raw_model_flag.strip():
        raise CliError(f"{entry.field_name('model_flag')} must be a non-empty string")
    else:
        model_flag = raw_model_flag.strip()
    if raw_prompt_flag is None:
        prompt_flag = _agent_default_prompt_flag(family_name)
    elif not isinstance(raw_prompt_flag, str) or not raw_prompt_flag.strip():
        raise CliError(f"{entry.field_name('prompt_flag')} must be a non-empty string")
    else:
        prompt_flag = raw_prompt_flag.strip()
    ping = _load_agent_ping_config(
        raw_ping,
        field_name=entry.field_name("ping"),
        default_model=_agent_default_ping_model(family_name),
    )
    if raw_fingerprint is None:
        fingerprint_override = None
    elif not isinstance(raw_fingerprint, str) or not raw_fingerprint.strip():
        raise CliError(f"{entry.field_name('fingerprint')} must be a non-empty string")
    else:
        fingerprint_override = raw_fingerprint.strip()

    normalized_home: Path | None = None
    resolved_direct_targets: tuple[Path, ...] = ()
    resolved_grep_targets: tuple[Path, ...] = ()
    resolved_sqlite_db_paths: tuple[Path, ...] = ()
    anchors: tuple[ProviderHomeAnchor, ...] = ()

    homes = _load_provider_homes(
        raw_homes,
        provider_spec=provider_spec,
        field_name=entry.field_name("homes"),
    )

    if homes:
        if provider_spec is None:
            raise CliError(
                f"{entry.item_path()} does not support home-based configuration for provider {family_name}"
            )
        if direct_paths or grep_paths or sqlite_db_paths:
            raise CliError(
                f"{entry.item_path()} must define either homes or explicit paths, not both"
            )

        home_spec = provider_spec.home_spec
        normalized_home = homes[0]
        home_direct_paths, home_grep_paths, home_sqlite_db_paths = (
            home_spec.build_paths(home=normalized_home)
        )
        resolved_direct_targets = _unique_paths(tuple(home_direct_paths))
        resolved_grep_targets = _unique_paths(
            tuple(home_grep_paths or home_direct_paths)
        )
        resolved_sqlite_db_paths = _unique_paths(tuple(home_sqlite_db_paths))
        anchors = tuple(home_spec.build_anchors(home=normalized_home))
    elif direct_paths or sqlite_db_paths:
        resolved_direct_targets = _resolve_raw_paths(direct_paths)
        resolved_grep_targets = (
            _resolve_raw_paths(grep_paths) if grep_paths else resolved_direct_targets
        )
        resolved_sqlite_db_paths = _resolve_raw_paths(sqlite_db_paths)
        anchors = _build_explicit_agent_config_anchors(
            direct_targets=resolved_direct_targets,
            sqlite_db_paths=resolved_sqlite_db_paths,
        )

    validate_provider_profile(provider_family.family, raw_profile)

    return AgentConfig(
        provider=provider_family.family,
        profile_id=profile_id,
        label=label,
        home=normalized_home,
        homes=homes,
        direct_targets=resolved_direct_targets,
        grep_targets=resolved_grep_targets,
        sqlite_db_paths=resolved_sqlite_db_paths,
        cli_command=cli_command,
        run_args=run_args,
        env=env,
        account=account,
        accounts=accounts,
        account_policy=account_policy,
        timeout_sec=timeout_sec,
        default_model=default_model,
        model_flag=model_flag,
        prompt_flag=prompt_flag,
        ping=ping,
        fingerprint_override=fingerprint_override,
        identity_anchors=anchors,
        is_default=False,
    )


def validate_provider_profile(provider: str, profile_json: dict[str, object]) -> None:
    from agentos.claude.agent import validate_profile as _claude
    from agentos.codex.agent import validate_profile as _codex
    from agentos.copilot.agent import validate_profile as _copilot
    from agentos.pi.agent import validate_profile as _pi
    from agentos.gemini.agent import validate_profile as _gemini
    from agentos.openclaw.agent import validate_profile as _openclaw
    from agentos.opencode.agent import validate_profile as _opencode

    _dispatch: dict[str, object] = {
        "claude-code": _claude,
        "codex": _codex,
        "copilot-cli": _copilot,
        "pi": _pi,
        "gemini-cli": _gemini,
        "openclaw": _openclaw,
        "opencode": _opencode,
    }
    fn = _dispatch.get(provider)
    if fn is not None:
        fn(profile_json)  # type: ignore[call-arg]


def _validate_unique_agent_config_ids(agent_configs: tuple["AgentConfig", ...]) -> None:
    seen_agent_configs: dict[str, AgentConfig] = {}
    for agent_config in agent_configs:
        if agent_config.profile_id is None:
            raise CliError("agent profile ids must not be empty")
        existing = seen_agent_configs.get(agent_config.profile_id)
        if existing is None:
            seen_agent_configs[agent_config.profile_id] = agent_config
            continue
        raise CliError(
            "agent profile ids must be unique; "
            f"duplicate id {agent_config.profile_id} for providers "
            f"{existing.provider} and {agent_config.provider}"
        )


def agent_config_with_provider_config(
    config: AgentConfig, provider_config: AgentProviderConfig | None
) -> AgentConfig:
    if provider_config is None or config.cli_command or not provider_config.cli_command:
        return config
    return replace(config, cli_command=provider_config.cli_command)


def _load_agent_cli_command(
    value: object,
    *,
    field_name: str,
    provider_config: AgentProviderConfig | None,
) -> tuple[str, ...]:
    if value is not None:
        return _load_string_argv(value, field_name=field_name)
    if provider_config is not None:
        return provider_config.cli_command
    return ()


def _reject_removed_profile_fields(
    entry: AgentConfigEntry, raw_profile: dict[str, object]
) -> None:
    for field_name in ("account", "home"):
        if field_name in raw_profile:
            raise CliError(
                f"{entry.field_name(field_name)} is no longer supported; "
                f"use {'accounts' if field_name != 'home' else 'homes'}"
            )


def _load_agent_account_policy(value: object, *, field_name: str) -> str:
    if value is None:
        return AGENT_ACCOUNT_POLICY_PROFILE_DEFAULT
    allowed = ", ".join(AGENT_ACCOUNT_POLICIES)
    if not isinstance(value, str) or not value.strip():
        raise CliError(f"{field_name} must be one of: {allowed}")
    normalized = value.strip()
    if normalized not in AGENT_ACCOUNT_POLICIES:
        raise CliError(f"{field_name} must be one of: {allowed}")
    return normalized


def _load_agent_account_contexts(
    value: object,
    *,
    provider: str,
    field_name: str,
) -> tuple[AgentAccountContext, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not value:
        raise CliError(f"{field_name} must be a non-empty JSON array")
    accounts: list[AgentAccountContext] = []
    seen_accounts: set[str] = set()
    for index, raw_item in enumerate(value):
        account = _load_agent_account_context(
            raw_item,
            provider=provider,
            field_name=f"{field_name}[{index}]",
        )
        if account is None:
            raise CliError(f"{field_name}[{index}] must define an account")
        if account.account in seen_accounts:
            raise CliError(
                f"{field_name} must be unique; duplicate account {account.account}"
            )
        seen_accounts.add(account.account)
        accounts.append(account)
    return tuple(accounts)


def _load_provider_homes(
    value: object,
    *,
    provider_spec: ChatProviderSpec | None,
    field_name: str,
) -> tuple[Path, ...]:
    if value is None:
        return ()
    if provider_spec is None:
        raise CliError(f"{field_name} is not supported for this provider")
    if not isinstance(value, list) or not value:
        raise CliError(f"{field_name} must be a non-empty JSON array")
    homes: list[Path] = []
    seen_homes: set[str] = set()
    for index, raw_item in enumerate(value):
        normalized_home = (
            Path(
                _normalize_provider_home(
                    raw_item,
                    field_name=f"{field_name}[{index}]",
                )
            )
            .expanduser()
            .resolve()
        )
        key = str(normalized_home)
        if key in seen_homes:
            raise CliError(f"{field_name} must be unique; duplicate home {key}")
        seen_homes.add(key)
        homes.append(normalized_home)
    return tuple(homes)


def _load_agent_account_context(
    value: object,
    *,
    provider: str,
    field_name: str,
) -> AgentAccountContext | None:
    if value is None:
        return None
    if isinstance(value, str):
        account = value.strip()
        if not account:
            raise CliError(f"{field_name} must be a non-empty string")
        return AgentAccountContext(
            provider=provider,
            account=validate_string_for_path(account, field_name=field_name),
        )
    if not isinstance(value, dict):
        raise CliError(f"{field_name} must be a string or JSON object")
    raw_provider = value.get("provider", provider)
    raw_account = value.get("account")
    if not isinstance(raw_provider, str) or not raw_provider.strip():
        raise CliError(f"{field_name}.provider must be a non-empty string")
    if not isinstance(raw_account, str) or not raw_account.strip():
        raise CliError(f"{field_name}.account must be a non-empty string")
    normalized_provider = canonical_provider_family_for_name(raw_provider.strip())
    if normalized_provider is None:
        raise CliError(f"{field_name}.provider must be a supported provider")
    if normalized_provider.family != provider:
        raise CliError(f"{field_name}.provider must match profile provider {provider}")
    return AgentAccountContext(
        provider=provider,
        account=validate_string_for_path(raw_account.strip(), field_name=f"{field_name}.account"),
    )


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


def _load_agent_ping_config(
    value: object, *, field_name: str, default_model: str | None = None
) -> AgentPingConfig:
    if value is None:
        return default_agent_ping_config_with_model(default_model)
    if not isinstance(value, dict):
        raise CliError(f"{field_name} must be a JSON object")

    raw_enabled = value.get("enabled", True)
    if not isinstance(raw_enabled, bool):
        raise CliError(f"{field_name}.enabled must be a boolean")

    raw_prompt = value.get("prompt")
    raw_argv = value.get("argv")
    raw_expected_number = value.get("expected_number", 745)
    raw_model = value.get("model", default_model)
    has_prompt = raw_prompt is not None
    has_argv = raw_argv is not None
    if has_prompt and has_argv:
        raise CliError(f"{field_name} must define either prompt or argv, not both")

    if not raw_enabled:
        if has_prompt or has_argv or "expected_number" in value or "model" in value:
            raise CliError(
                f"{field_name} must not define prompt, argv, expected_number, or model when disabled"
            )
        return AgentPingConfig(enabled=False, prompt=None, expected_number=None)

    expected_number = _load_ping_expected_number(
        raw_expected_number,
        field_name=f"{field_name}.expected_number",
    )
    model = _load_ping_model(raw_model, field_name=f"{field_name}.model")

    if has_prompt:
        if not isinstance(raw_prompt, str) or not raw_prompt.strip():
            raise CliError(f"{field_name}.prompt must be a non-empty string")
        return AgentPingConfig(
            prompt=raw_prompt.strip(),
            expected_number=expected_number,
            model=model,
        )

    if has_argv:
        argv = _load_string_argv(
            raw_argv,
            field_name=f"{field_name}.argv",
        )
        if not argv:
            raise CliError(f"{field_name}.argv must be a non-empty JSON array")
        return AgentPingConfig(
            prompt=None,
            argv=argv,
            expected_number=expected_number,
            model=model,
        )

    return default_agent_ping_config_with_model(model)


def default_agent_ping_config_with_model(model: str | None) -> AgentPingConfig:
    config = default_agent_ping_config()
    if model is None:
        return config
    return replace(config, model=model)


def _load_ping_expected_number(value: object, *, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise CliError(f"{field_name} must be an integer or null")
    return value


def _load_ping_model(value: object, *, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise CliError(f"{field_name} must be a non-empty string or null")
    return value.strip()


def _load_string_mapping(
    value: object, *, field_name: str
) -> tuple[tuple[str, str], ...]:
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


def _load_json_object(path: Path, *, description: str) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CliError(f"invalid {description} JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise CliError(f"{description} must be a JSON object: {path}")
    return payload


def _write_json_file(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.parent / f".{path.name}.agentos-tmp-{os.getpid()}"
    temp_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temp_path, path)


def _resolve_raw_paths(raw_paths: tuple[str, ...]) -> tuple[Path, ...]:
    return _unique_paths(
        tuple(Path(raw_path).expanduser().resolve() for raw_path in raw_paths)
    )


def _build_explicit_agent_config_anchors(
    *,
    direct_targets: tuple[Path, ...],
    sqlite_db_paths: tuple[Path, ...],
) -> tuple["ProviderHomeAnchor", ...]:
    anchors = [
        ProviderHomeAnchor(role=f"direct_target_{index + 1}", path=path)
        for index, path in enumerate(direct_targets)
    ]
    anchors.extend(
        ProviderHomeAnchor(role=f"sqlite_db_{index + 1}", path=path)
        for index, path in enumerate(sqlite_db_paths)
    )
    return tuple(anchors)


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
