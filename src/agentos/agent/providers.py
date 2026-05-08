from __future__ import annotations

from pathlib import Path
from typing import Protocol

from agentos._core.errors import CliError
from agentos.agent.primitives import AgentConfig, AgentRunRequest, ResolvedAgentRun
from agentos.agents.agent import AgentsAgent
from agentos.chat.providers import LegacyProviderConfig, load_legacy_provider_configs
from agentos.claude.agent import ClaudeAgent
from agentos.codex.agent import CodexAgent
from agentos.copilot.agent import CopilotAgent
from agentos.gemini.agent import GeminiAgent
from agentos.openclaw.agent import OpenclawAgent
from agentos.opencode.agent import OpencodeAgent
from agentos.pi.agent import PiAgent


DEFAULT_RUN_PROVIDER_FAMILIES = ("codex", "copilot-cli", "pi")


class ConfiguredAgent(Protocol):
    provider: str
    instance_id: str | None
    label: str | None
    homes: tuple[tuple[str, Path], ...]
    default_model: str | None

    def summary(self) -> dict[str, object]: ...

    def resolve_run(self, request: AgentRunRequest) -> ResolvedAgentRun: ...


def load_configured_agents(*, start_path: Path | str = ".") -> tuple[ConfiguredAgent, ...]:
    return tuple(
        _agent_from_legacy_config(legacy_provider_config)
        for legacy_provider_config in load_legacy_provider_configs(start_path=start_path)
    )


def supported_default_run_provider_families() -> tuple[str, ...]:
    return DEFAULT_RUN_PROVIDER_FAMILIES


def _agent_from_legacy_config(legacy_provider_config: LegacyProviderConfig) -> ConfiguredAgent:
    config = _agent_config_from_legacy_config(legacy_provider_config)
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
    raise CliError(f"unsupported configured agent provider {legacy_provider_config.family}")


def _agent_config_from_legacy_config(instance: LegacyProviderConfig) -> AgentConfig:
    return AgentConfig(
        provider=instance.family,
        instance_id=instance.instance_id,
        label=instance.label,
        homes=instance.homes,
        cli_command=instance.cli_command,
        run_args=instance.run_args,
        env=instance.env,
        timeout_sec=instance.timeout_sec,
        default_model=instance.default_model,
        model_flag=instance.model_flag,
        prompt_flag=instance.prompt_flag,
        is_default=instance.is_default,
        fingerprint=instance.fingerprint,
    )


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
    "AgentRunRequest",
    "ConfiguredAgent",
    "load_configured_agents",
    "ResolvedAgentRun",
    "resolve_agent",
    "supported_default_run_provider_families",
]
