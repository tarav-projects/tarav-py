from __future__ import annotations

from pathlib import Path

from agentos._core.errors import CliError
from agentos.agent.primitives import (
    Agent,
    AgentConfig,
)
from agentos.agents.agent import AgentsAgent
from agentos.chat.providers import load_agent_configs
from agentos.claude.agent import ClaudeAgent
from agentos.codex.agent import CodexAgent
from agentos.copilot.agent import CopilotAgent
from agentos.gemini.agent import GeminiAgent
from agentos.openclaw.agent import OpenclawAgent
from agentos.opencode.agent import OpencodeAgent
from agentos.pi.agent import PiAgent


DEFAULT_RUN_PROVIDER_FAMILIES = ("codex", "copilot-cli", "pi")


ConfiguredAgent = Agent


def load_configured_agents(*, start_path: Path | str = ".") -> tuple[ConfiguredAgent, ...]:
    return tuple(
        agent_from_config(agent_config)
        for agent_config in load_agent_configs(start_path=start_path)
    )


def supported_default_run_provider_families() -> tuple[str, ...]:
    return DEFAULT_RUN_PROVIDER_FAMILIES


def agent_from_config(config: AgentConfig) -> ConfiguredAgent:
    if config.provider == "agents":
        return AgentsAgent.from_config(config)
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


def resolve_agent(
    *,
    provider: str,
    instance_id: str | None,
    start_path: Path,
) -> ConfiguredAgent:
    matching = [
        agent
        for agent in load_configured_agents(start_path=start_path)
        if agent.provider == provider
    ]
    if not matching:
        raise CliError(f"no configured agents found for provider {provider}")

    if instance_id is not None:
        for agent in matching:
            if agent.instance_id == instance_id:
                return agent
        raise CliError(
            f"no agent {instance_id!r} found for provider {provider}"
        )

    if len(matching) == 1:
        return matching[0]

    available = ", ".join(agent.instance_id or "<default>" for agent in matching)
    raise CliError(
        f"provider {provider} is ambiguous; pass --instance (available: {available})"
    )


__all__ = [
    "agent_from_config",
    "ConfiguredAgent",
    "load_configured_agents",
    "resolve_agent",
    "supported_default_run_provider_families",
]
