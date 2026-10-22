"""provider adapter registry."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from tarav.l0._core.errors import CliError
from tarav.l1.agent import auth_registry
from tarav.l1.agent.account_status import AgentAccountContext
from tarav.l1.agent.primitives import (
    AgentConfig,
)
from tarav.l1.agent.profile_scope import select_allowed_home
from tarav.l1.agent.profile_scope import validate_account_override
from tarav.l1.agent.config import (
    AgentProviderConfig,
    agent_config_with_provider_config,
    agent_config_with_home_override,
    default_agent_configs,
    load_agent_configs,
    load_agent_provider_configs,
    load_agent_profile,
)
from tarav.l1.agent.providers.claude_code.agent import ClaudeAgent
from tarav.l1.agent.providers.codex.agent import CodexAgent
from tarav.l1.agent.providers.copilot_cli.agent import CopilotAgent


PROVIDER_ADAPTERS: dict[str, type[AgentConfig]] = {
    "codex": CodexAgent,
    "claude-code": ClaudeAgent,
    "copilot-cli": CopilotAgent,
}

# tarav.breadcrumb 0fb5b6371299
DEFAULT_RUN_PROVIDER_FAMILIES = ("claude-code", "codex", "copilot-cli")


def load_configured_agents(*, start_path: Path | str = ".") -> tuple[AgentConfig, ...]:
    return tuple(
        agent_from_config(agent_config)
        for agent_config in load_agent_configs(start_path=start_path)
    )


def supported_default_run_provider_families() -> tuple[str, ...]:
    return DEFAULT_RUN_PROVIDER_FAMILIES


def agent_from_config(config: AgentConfig) -> AgentConfig:
    adapter = PROVIDER_ADAPTERS.get(config.provider)
    if adapter is None:
        raise CliError(f"unsupported configured agent provider {config.provider}")
    return adapter.from_config(config)


def resolve_account_runtime_agent(
    *,
    provider: str,
    account: str,
    home: Path | str,
    profile: str | None,
    start_path: Path | str = ".",
) -> AgentConfig:
    if not auth_registry.account_exists(provider, account):
        raise CliError(f"agent account is not registered: {provider}.{account}")
    account_context = AgentAccountContext(provider=provider, account=account)
    selected_profile = profile
    if selected_profile is None:
        selected_profile = _infer_account_runtime_profile(
            provider=account_context.provider,
            account=account_context.account,
            home=home,
            start_path=start_path,
        )
    config = resolve_agent_config(
        provider=account_context.provider,
        profile=selected_profile,
        start_path=Path(start_path),
        home=home,
    )
    validate_account_override(
        profile_id=config.profile_id or "<default>",
        allowed_accounts=config.accounts,
        account=account_context.account,
    )
    return agent_from_config(replace(config, account=account_context))


def _infer_account_runtime_profile(
    *,
    provider: str,
    account: str,
    home: Path | str,
    start_path: Path | str,
) -> str:
    normalized_home = Path(home).expanduser().resolve()
    matches = [
        config
        for config in load_agent_configs(start_path=start_path)
        if config.provider == provider
        and any(path.expanduser().resolve() == normalized_home for path in config.homes)
        and any(context.account == account for context in config.accounts)
    ]
    if len(matches) == 1:
        profile_id = matches[0].profile_id
        if profile_id is not None:
            return profile_id
    if not matches:
        raise CliError(
            "provider command runtime requires --profile or exactly one configured "
            f"profile matching {provider}/{account} at {normalized_home}"
        )
    profile_ids = ", ".join(
        sorted(config.profile_id or "<default>" for config in matches)
    )
    raise CliError(
        f"provider command runtime for {provider}/{account} at {normalized_home} "
        f"matches multiple profiles: {profile_ids}; pass --profile"
    )


def _default_registered_account_agent_config(
    *,
    provider: str,
    home: Path | str,
    provider_configs: dict[str, AgentProviderConfig],
) -> AgentConfig:
    for agent_config in default_agent_configs():
        if agent_config.provider == provider:
            configured_agent = agent_config_with_provider_config(
                agent_config,
                provider_configs.get(provider),
            )
            return agent_config_with_home_override(configured_agent, home=home)
    raise CliError(f"unsupported registered account provider {provider}")


def resolve_agent(
    *,
    provider: str | None,
    profile: str | None,
    start_path: Path,
    home: Path | str | None = None,
) -> AgentConfig:
    return agent_from_config(
        resolve_agent_config(
            provider=provider,
            profile=profile,
            start_path=start_path,
            home=home,
        )
    )


def resolve_agent_config(
    *,
    provider: str | None,
    profile: str | None,
    start_path: Path,
    home: Path | str | None = None,
) -> AgentConfig:
    if profile is not None:
        selected = _resolve_profile_config(
            provider=provider,
            profile=profile,
            start_path=start_path,
        )
        if home is not None:
            return _profile_config_with_home_selection(selected, home=home)
        return selected

    if provider is None:
        raise CliError("--profile is required unless --provider and --home are set")
    if home is None:
        raise CliError("--home is required when running without --profile")

    provider_configs = load_agent_provider_configs(start_path=start_path)
    selected = _default_registered_account_agent_config(
        provider=provider,
        home=home,
        provider_configs=provider_configs,
    )
    return selected


def _resolve_profile_config(
    *,
    provider: str | None,
    profile: str,
    start_path: Path,
) -> AgentConfig:
    del start_path
    selected = load_agent_profile(profile)
    if provider is not None and selected.provider != provider:
        raise CliError(
            f"profile {profile!r} uses provider {selected.provider}, not {provider}"
        )
    return selected


def _profile_config_with_home_selection(
    config: AgentConfig, *, home: Path | str
) -> AgentConfig:
    selected_home = select_allowed_home(
        profile_id=config.profile_id or "<default>",
        allowed_homes=config.homes,
        home=home,
    )
    return agent_config_with_home_override(config, home=selected_home)


__all__ = [
    "agent_from_config",
    "load_configured_agents",
    "resolve_agent",
    "resolve_account_runtime_agent",
    "resolve_agent_config",
    "supported_default_run_provider_families",
]
