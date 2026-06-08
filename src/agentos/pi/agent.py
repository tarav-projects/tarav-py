from __future__ import annotations

from dataclasses import dataclass

from agentos.agent.primitives import (
    AgentBase,
    AgentConfig,
    agent_base_kwargs_for_provider,
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
class PiAgent(AgentBase):

    @classmethod
    def from_config(cls, config: AgentConfig) -> PiAgent:
        return cls(
            **agent_base_kwargs_for_provider(
                config,
                provider=PI_PROVIDER,
                agent_name="Pi.Agent",
            )
        )

    @property
    def provider(self) -> str:
        return PI_PROVIDER

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


__all__ = ["PiAgent"]
