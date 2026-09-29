# $kw: ^agentos-provider-claude-code-agent --from Agent.Navigable.Codebase --note [DF] provider-specific behavior lives beneath the agent provider namespace --supp ^c20260811-62u
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tarav.l1.agent.account_status import AccountStatus
from tarav.l1.agent.primitives import (
    AgentConfig,
    RunnableMixin,
    adapter_kwargs_from_config,
    agent_session_paths,
)
from tarav.l1.agent.run_runtime import (
    AgentCommand,
    AgentCommandConfig,
    AgentRunConfig,
    AgentRunDryResult,
    AgentRunResult,
    CLAUDE_CONFIG_DIR_ENV_VAR,
    execute_agent_command,
    format_agent_command,
)
from tarav.l1.agent.run_prepare import AgentRunPrepareRequest, AgentRunPrepareResult
from tarav.l1.agent.providers.claude_code.session import (
    ClaudeSession,
    ClaudeSessionRef,
    discover_claude_session_refs,
    find_claude_session_ref_by_id,
    load_claude_session,
)
from tarav.l1.agent.providers.claude_code.account_status import _claude_account_status_impl


CLAUDE_PROVIDER = "claude-code"


@dataclass(frozen=True)
class ClaudeAgent(RunnableMixin, AgentConfig):
    provider: str = CLAUDE_PROVIDER

    @classmethod
    def from_config(cls, config: AgentConfig) -> ClaudeAgent:
        return cls(
            **adapter_kwargs_from_config(
                config,
                provider=CLAUDE_PROVIDER,
                agent_name="Claude.Agent",
            )
        )

    def discover_session_refs(self) -> tuple[ClaudeSessionRef, ...]:
        direct_targets = self._session_discovery_targets()
        return discover_claude_session_refs(targets=direct_targets)

    def find_session_ref_by_id(self, session_id: str) -> ClaudeSessionRef | None:
        direct_targets = self._session_discovery_targets()
        return find_claude_session_ref_by_id(targets=direct_targets, session_id=session_id)

    def _session_discovery_targets(self) -> tuple[Path, ...]:
        direct_targets, _ = agent_session_paths(self)
        if self.home is None:
            return direct_targets
        return tuple(dict.fromkeys((*direct_targets, self.home / "archive")))

    def load_session(self, session_ref: ClaudeSessionRef) -> ClaudeSession:
        return load_claude_session(session_ref)

    def _build_command(self, command_config: AgentCommandConfig) -> AgentCommand:
        return self._build_command_with_env(
            command_config,
            env_overrides=self._run_env_overrides(),
        )

    def run(
        self,
        command_config: AgentCommandConfig,
        run_config: AgentRunConfig,
    ) -> AgentRunResult:
        self._check_account_scope(command_config)
        prepare_result = self.prepare_run(
            AgentRunPrepareRequest(
                agent=self,
                command_config=command_config,
                start_path=run_config.cwd,
                dry_run=False,
                source="agent.run",
            )
        )
        for line in prepare_result.preamble_lines:
            print(line)

        command = self._build_command_with_env(
            command_config,
            env_overrides={
                **self._run_env_overrides(),
                **prepare_result.env_overrides,
            },
        )
        base_result = execute_agent_command(command, run_config=self.resolve_run_config(run_config))
        return AgentRunResult(
            exit_code=base_result.exit_code,
            stdout=base_result.stdout,
            stderr=base_result.stderr,
            preamble_lines=prepare_result.preamble_lines,
        )

    def run_dry(self, command_config: AgentCommandConfig) -> AgentRunDryResult:
        self._check_account_scope(command_config)
        prepare_result = self.prepare_run(
            AgentRunPrepareRequest(
                agent=self,
                command_config=command_config,
                start_path=Path.cwd().resolve(),
                dry_run=True,
                source="agent.run",
            )
        )

        from tarav.l1.agent.run_runtime import agent_command_with_env_overrides
        base_command = self._build_command_with_env(
            command_config,
            env_overrides=self._run_env_overrides(),
        )
        command = agent_command_with_env_overrides(
            base_command,
            env_overrides=prepare_result.env_overrides,
            env_display_overrides=prepare_result.env_display_overrides,
        )
        return AgentRunDryResult(
            lines=(*prepare_result.preamble_lines, *command.setup_lines, format_agent_command(command)),
        )

    def prepare_run(
        self,
        request: AgentRunPrepareRequest,
    ) -> AgentRunPrepareResult:




        return AgentRunPrepareResult()

    def account_status(
        self,
        *,
        record_usage: bool = True,
        fallback_to_usage_registry: bool = True,
    ) -> AccountStatus:
        return _claude_account_status_impl(
            self,
            record_usage=record_usage,
            fallback_to_usage_registry=fallback_to_usage_registry,
        )

    def _resolved_account(self, command_config: AgentCommandConfig) -> str | None:
        account_str = (command_config.account or "").strip() or None
        if account_str is not None:
            return account_str
        if self.account is None:
            return None
        if self.account.provider != self.provider:
            return None
        return (self.account.account or "").strip() or None

    def _run_env_overrides(self) -> dict[str, str]:
        env_overrides = dict(self.env)
        if self.home is not None:
            env_overrides[CLAUDE_CONFIG_DIR_ENV_VAR] = str(self.home)
        return env_overrides


def validate_profile(profile_json: dict[str, object]) -> None:
    pass


__all__ = ["ClaudeAgent", "validate_profile"]
