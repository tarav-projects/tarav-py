# $kw: --from Agent.Profile --from Provider.Instance
"""Agent configuration entry decoding and validation."""

from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path

from tarav._core.errors import CliError
from tarav._core.path_validation import validate_string_for_path
from tarav._core.sequences import _unique_paths
from tarav.agent.account_status import AgentAccountContext
from tarav.agent.primitives import (
    AgentConfig,
    AgentPingConfig,
    default_agent_ping_config,
)
from tarav.agent.run_runtime import HARNESS_INJECTED_ENV_ALLOWLIST
from tarav.agent.providers import (
    ProviderHomeAnchor,
    canonical_provider_families,
    canonical_provider_family_for_name,
)

from ._config_models import (
    AGENT_ACCOUNT_POLICIES,
    AGENT_ACCOUNT_POLICY_PROFILE_DEFAULT,
    AgentConfigEntry,
    AgentProviderConfig,
    ChatProviderSpec,
    _agent_default_model,
    _agent_default_ping_model,
    _agent_default_run_args,
    canonical_chat_provider_spec_for_name,
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
    _reject_harness_injected_env(
        env,
        provider=provider_family.family,
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
        ping_config=ping,
        fingerprint_override=fingerprint_override,
        identity_anchors=anchors,
        is_default=False,
    )


def validate_provider_profile(provider: str, profile_json: dict[str, object]) -> None:
    from tarav.agent.providers.claude_code.agent import validate_profile as _claude
    from tarav.agent.providers.codex.agent import validate_profile as _codex
    from tarav.agent.providers.copilot_cli.agent import validate_profile as _copilot
    from tarav.agent.providers.pi.agent import validate_profile as _pi
    from tarav.agent.providers.gemini_cli.agent import validate_profile as _gemini
    from tarav.agent.providers.openclaw.agent import validate_profile as _openclaw
    from tarav.agent.providers.opencode.agent import validate_profile as _opencode

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


        account = account.split("/", 1)[0]
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
        account=validate_string_for_path(
            raw_account.strip(), field_name=f"{field_name}.account"
        ),
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


def _reject_harness_injected_env(
    env: tuple[tuple[str, str], ...],
    *,
    provider: str,
    field_name: str,
) -> None:
    reserved = HARNESS_INJECTED_ENV_ALLOWLIST.get(provider, frozenset())
    for key, _ in env:
        if key in reserved:
            raise CliError(
                f"{field_name}.{key} is harness-injected; "
                "Tarav derives it from the selected home or account state"
            )


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
    temp_path = path.parent / f".{path.name}.tarav-tmp-{os.getpid()}"
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
