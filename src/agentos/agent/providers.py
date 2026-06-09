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
from agentos.agent.profile_scope import select_allowed_home
from agentos.agent.config import (
    AgentProviderConfig,
    agent_config_with_provider_config,
    agent_config_with_home_override,
    default_agent_configs,
    load_agent_configs,
    load_agent_provider_configs,
    load_agent_profile,
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
    provider: str | None,
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
        profile_id=config.instance_id or "<default>",
        allowed_homes=config.homes,
        home=home,
    )
    return agent_config_with_home_override(config, home=selected_home)


__all__ = [
    "agent_from_config",
    "build_registered_account_agent",
    "load_configured_agents",
    "resolve_agent",
    "resolve_agent_config",
    "supported_default_run_provider_families",
]
