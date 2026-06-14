from __future__ import annotations

from dataclasses import dataclass

from agentos.agent.primitives import (
    AgentConfig,
    RunnableMixin,
    adapter_kwargs_from_config,
    agent_session_paths,
)
from agentos.agent.run_runtime import (
    AgentCommand,
    AgentCommandConfig,
)
from agentos._core.errors import CliError
from agentos.pi.session import (
    PiSession,
    PiSessionRef,
    discover_pi_session_refs,
    load_pi_session,
)


PI_PROVIDER = "pi"


@dataclass(frozen=True)
class PiAgent(RunnableMixin, AgentConfig):
    provider: str = PI_PROVIDER

    @classmethod
    def from_config(cls, config: AgentConfig) -> PiAgent:
        return cls(
            **adapter_kwargs_from_config(
                config,
                provider=PI_PROVIDER,
                agent_name="Pi.Agent",
            )
        )

    def discover_session_refs(self) -> tuple[PiSessionRef, ...]:
        direct_targets, _ = agent_session_paths(self)
        return discover_pi_session_refs(targets=direct_targets)

    def load_session(self, session_ref: PiSessionRef) -> PiSession:
        return load_pi_session(session_ref)

    def _build_command(self, command_config: AgentCommandConfig) -> AgentCommand:
        if command_config.account is not None:
            raise CliError(f"--account is not supported for provider {self.provider}")
        return self._build_command_with_env(
            command_config,
            env_overrides=dict(self.env),
        )


def validate_profile(profile_json: dict[str, object]) -> None:
    pass


__all__ = ["PiAgent", "validate_profile"]
