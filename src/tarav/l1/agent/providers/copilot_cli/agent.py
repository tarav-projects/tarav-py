# $kw: ^agentos-provider-copilot-cli-agent --from Agent.Navigable.Codebase --note [DF] provider-specific behavior lives beneath the agent provider namespace --supp ^c20260811-62u
from __future__ import annotations

from dataclasses import dataclass

from tarav.l1.agent.primitives import (
    AgentConfig,
    RunnableMixin,
    adapter_kwargs_from_config,
    agent_session_paths,
)
from tarav.l1.agent.run_runtime import (
    AgentCommand,
    AgentCommandConfig,
    COPILOT_HOME_ENV_VAR,
)
from tarav.l0._core.errors import CliError
from tarav.l1.agent.account_status import AccountStatus
from tarav.l1.agent.providers.copilot_cli.session import (
    CopilotSession,
    CopilotSessionRef,
    discover_copilot_session_refs,
    find_copilot_session_ref_by_id,
    load_copilot_session,
)
from tarav.l1.agent.providers.copilot_cli.account_status import _copilot_account_status_impl


COPILOT_PROVIDER = "copilot-cli"


@dataclass(frozen=True)
class CopilotAgent(RunnableMixin, AgentConfig):
    provider: str = COPILOT_PROVIDER

    @classmethod
    def from_config(cls, config: AgentConfig) -> CopilotAgent:
        return cls(
            **adapter_kwargs_from_config(
                config,
                provider=COPILOT_PROVIDER,
                agent_name="Copilot.Agent",
            )
        )

    def discover_session_refs(self) -> tuple[CopilotSessionRef, ...]:
        direct_targets, _ = agent_session_paths(self)
        return discover_copilot_session_refs(targets=direct_targets)

    def find_session_ref_by_id(self, session_id: str) -> CopilotSessionRef | None:
        direct_targets, _ = agent_session_paths(self)
        return find_copilot_session_ref_by_id(targets=direct_targets, session_id=session_id)

    def load_session(self, session_ref: CopilotSessionRef) -> CopilotSession:
        return load_copilot_session(session_ref)

    def _build_command(self, command_config: AgentCommandConfig) -> AgentCommand:
        if command_config.account is not None:
            raise CliError(f"--account is not supported for provider {self.provider}")
        return self._build_command_with_env(
            command_config,
            env_overrides=self._run_env_overrides(),
        )

    def account_status(
        self,
        *,
        record_usage: bool = True,
        fallback_to_usage_registry: bool = True,
    ) -> AccountStatus:
        return _copilot_account_status_impl(
            self,
            record_usage=record_usage,
            fallback_to_usage_registry=fallback_to_usage_registry,
        )

    def _run_env_overrides(self) -> dict[str, str]:
        env_overrides = dict(self.env)
        if self.home is not None:
            env_overrides[COPILOT_HOME_ENV_VAR] = str(self.home)
        return env_overrides


def validate_profile(profile_json: dict[str, object]) -> None:
    pass


__all__ = ["CopilotAgent", "validate_profile"]
