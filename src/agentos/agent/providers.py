from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from agentos._core.errors import CliError
from agentos.agent.account_registry import load_account
from agentos.agent.account_status import AgentAccountContext
from agentos.agent.primitives import (
    Agent,
    AgentConfig,
)
from agentos.agent.config import (
    AgentProviderConfig,
    agent_config_with_provider_config,
    agent_config_with_home_override,
    default_agent_configs,
    load_agent_configs,
    load_agent_provider_configs,
)
from agentos.claude.agent import ClaudeAgent
from agentos.codex.agent import CodexAgent
from agentos.copilot.agent import CopilotAgent
from agentos.gemini.agent import GeminiAgent
from agentos.openclaw.agent import OpenclawAgent
from agentos.opencode.agent import OpencodeAgent
from agentos.pi.agent import PiAgent


DEFAULT_RUN_PROVIDER_FAMILIES = ("claude-code", "codex", "copilot-cli", "pi")


def load_configured_agents(*, start_path: Path | str = ".") -> tuple[Agent, ...]:
    return tuple(
        agent_from_config(agent_config)
        for agent_config in load_agent_configs(start_path=start_path)
    )


def load_agent_configs_with_defaults(*, start_path: Path | str = ".") -> tuple[AgentConfig, ...]:
    configured = load_agent_configs(start_path=start_path)
    provider_configs = load_agent_provider_configs(start_path=start_path)
    configured_providers = {config.provider for config in configured}
    defaults = tuple(
        agent_config_with_provider_config(
            config,
            provider_configs.get(config.provider),
        )
        for config in default_agent_configs()
        if config.provider not in configured_providers
    )
    return (*configured, *defaults)


def supported_default_run_provider_families() -> tuple[str, ...]:
    return DEFAULT_RUN_PROVIDER_FAMILIES


def agent_from_config(config: AgentConfig) -> Agent:
    if config.provider == "codex":
        return CodexAgent.from_config(config)
    if config.provider == "claude-code":
        return ClaudeAgent.from_config(config)
    if config.provider == "copilot-cli":
        return CopilotAgent.from_config(config)
    if config.provider == "gemini-cli":
        return GeminiAgent.from_config(config)
    if config.provider == "openclaw":
        return OpenclawAgent.from_config(config)
    if config.provider == "opencode":
        return OpencodeAgent.from_config(config)
    if config.provider == "pi":
        return PiAgent.from_config(config)
    raise CliError(f"unsupported configured agent provider {config.provider}")


def build_registered_account_agent(
    *,
    provider: str,
    account: str,
    home: Path | str,
    start_path: Path | str = ".",
) -> Agent:
    account_record = load_account(provider, account)
    account_context = AgentAccountContext(
        provider=str(account_record["provider"]),
        account=str(account_record["account"]),
    )
    provider_configs = load_agent_provider_configs(start_path=start_path)
    config = _default_registered_account_agent_config(
        provider=account_context.provider,
        home=home,
        provider_configs=provider_configs,
    )
    return agent_from_config(replace(config, account=account_context))


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
    provider: str,
    profile: str | None,
    start_path: Path,
    home: Path | str | None = None,
) -> Agent:
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
    provider: str,
    profile: str | None,
    start_path: Path,
    home: Path | str | None = None,
) -> AgentConfig:
    matching = [
        agent_config
        for agent_config in load_agent_configs_with_defaults(start_path=start_path)
        if agent_config.provider == provider
    ]
    if not matching:
        raise CliError(f"no agent config found for provider {provider}")

    if profile is not None:
        for agent_config in matching:
            if agent_config.instance_id == profile:
                if home is not None:
                    return agent_config_with_home_override(agent_config, home=home)
                return agent_config
        raise CliError(
            f"no profile {profile!r} found for provider {provider}"
        )

    configured_matching = tuple(agent_config for agent_config in matching if not agent_config.is_default)
    if len(configured_matching) == 1:
        selected = configured_matching[0]
    elif len(configured_matching) > 1:
        available = ", ".join(
            agent_config.instance_id or "<default>" for agent_config in configured_matching
        )
        raise CliError(
            f"provider {provider} is ambiguous; pass --profile (available: {available})"
        )
    else:
        selected = matching[0]

    if home is not None:
        return agent_config_with_home_override(selected, home=home)
    return selected


__all__ = [
    "agent_from_config",
    "build_registered_account_agent",
    "load_configured_agents",
    "load_agent_configs_with_defaults",
    "resolve_agent",
    "resolve_agent_config",
    "supported_default_run_provider_families",
]
