from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agentos._core.errors import CliError
from agentos.chat.providers import ProviderInstance, load_configured_provider_instances


@dataclass(frozen=True)
class AgentRunRequest:
    prompt: str
    model: str | None = None


@dataclass(frozen=True)
class ResolvedAgentRun:
    provider: str
    instance_id: str | None
    command: tuple[str, ...]
    env: tuple[tuple[str, str], ...]

    def env_mapping(self) -> dict[str, str]:
        return dict(self.env)


@dataclass(frozen=True)
class AgentosAgent:
    provider_instance: ProviderInstance

    @property
    def provider(self) -> str:
        return self.provider_instance.family

    @property
    def instance_id(self) -> str | None:
        return self.provider_instance.instance_id

    def summary(self) -> dict[str, object]:
        return self.provider_instance.summary()

    def resolve_run(self, request: AgentRunRequest) -> ResolvedAgentRun:
        command = _build_agent_command(
            self.provider_instance,
            prompt=request.prompt,
            model=request.model,
        )
        return ResolvedAgentRun(
            provider=self.provider,
            instance_id=self.instance_id,
            command=tuple(command),
            env=self.provider_instance.env,
        )


def load_configured_agents(*, start_path: Path | str = ".") -> tuple[AgentosAgent, ...]:
    return tuple(
        AgentosAgent(provider_instance=provider_instance)
        for provider_instance in load_configured_provider_instances(start_path=start_path)
    )


def resolve_agent(
    *,
    provider: str,
    instance_id: str | None,
    start_path: Path,
) -> AgentosAgent:
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


def _build_agent_command(
    instance: ProviderInstance,
    *,
    prompt: str,
    model: str | None,
) -> list[str]:
    if not instance.cli_command:
        raise CliError(
            f"agent {instance.instance_id or '<default>'} for provider {instance.family} has no cli_command"
        )

    command = list(instance.cli_command)
    command.extend(instance.run_args)
    effective_model = model or instance.default_model
    if effective_model is not None:
        if instance.model_flag is None:
            raise CliError(
                f"agent {instance.instance_id or '<default>'} for provider {instance.family} does not define model_flag"
            )
        command.extend([instance.model_flag, effective_model])

    if instance.prompt_flag is not None:
        command.extend([instance.prompt_flag, prompt])
    else:
        command.append(prompt)
    return command


__all__ = [
    "AgentosAgent",
    "AgentRunRequest",
    "load_configured_agents",
    "ResolvedAgentRun",
    "resolve_agent",
]
