from __future__ import annotations

from dataclasses import dataclass
from agentos.agent.account_status import AccountStatus
from agentos.agent.primitives import (
    AgentBase,
    AgentConfig,
    agent_base_kwargs_for_provider,
    agent_session_paths,
)
from agentos.agent.run_runtime import (
    AgentCommand,
    AgentCommandConfig,
    AgentRunConfig,
    AgentRunDryResult,
    AgentRunResult,
    execute_agent_command,
    format_agent_command,
)
from agentos.claude.session import (
    ClaudeSession,
    ClaudeSessionRef,
    discover_claude_session_refs,
    find_claude_session_ref_by_id,
    load_claude_session,
)
from agentos.claude.account_status import _claude_account_status_impl


CLAUDE_PROVIDER = "claude-code"
CLAUDE_CONFIG_DIR_ENV_VAR = "CLAUDE_CONFIG_DIR"


@dataclass(frozen=True)
class ClaudeAgent(AgentBase):

    @classmethod
    def from_config(cls, config: AgentConfig) -> ClaudeAgent:
        return cls(
            **agent_base_kwargs_for_provider(
                config,
                provider=CLAUDE_PROVIDER,
                agent_name="Claude.Agent",
            )
        )

    @property
    def provider(self) -> str:
        return CLAUDE_PROVIDER

    def discover_session_refs(self) -> tuple[ClaudeSessionRef, ...]:
        direct_targets, _ = agent_session_paths(self)
        return discover_claude_session_refs(targets=direct_targets)

    def find_session_ref_by_id(self, session_id: str) -> ClaudeSessionRef | None:
        direct_targets, _ = agent_session_paths(self)
        return find_claude_session_ref_by_id(targets=direct_targets, session_id=session_id)

    def load_session(self, session_ref: ClaudeSessionRef) -> ClaudeSession:
        return load_claude_session(session_ref)

    def _build_command(self, command_config: AgentCommandConfig) -> AgentCommand:
        effective_config = self._claude_command_config(command_config)
        return self._build_command_with_env(
            effective_config,
            env_overrides=self._run_env_overrides(),
        )

    def run(
        self,
        command_config: AgentCommandConfig,
        run_config: AgentRunConfig,
    ) -> AgentRunResult:
        requested_account = self._resolved_account(command_config)
        preamble_lines: tuple[str, ...] = ()
        env_overrides: dict[str, str] = {}
        if requested_account is not None:
            from agentos.claude.account_registry import (
                has_claude_oauth_token_kind,
                load_claude_oauth_token_for_account,
            )
            if has_claude_oauth_token_kind(requested_account):
                token = load_claude_oauth_token_for_account(requested_account)
                env_overrides = {"CLAUDE_CODE_OAUTH_TOKEN": token.token}
                preamble_line = _format_claude_preamble_line(self, requested_account)
                preamble_lines = (preamble_line,)
                print(preamble_line)

        command = self._build_command_with_env(
            self._claude_command_config(command_config),
            env_overrides={**self._run_env_overrides(), **env_overrides},
        )
        base_result = execute_agent_command(command, run_config=self.resolve_run_config(run_config))
        return AgentRunResult(
            exit_code=base_result.exit_code,
            stdout=base_result.stdout,
            stderr=base_result.stderr,
            preamble_lines=preamble_lines,
        )

    def run_dry(self, command_config: AgentCommandConfig) -> AgentRunDryResult:
        requested_account = self._resolved_account(command_config)
        env_overrides: dict[str, str] = {}
        env_display_overrides: dict[str, str] = {}
        preamble_lines: list[str] = []
        if requested_account is not None:
            from agentos.claude.account_registry import (
                has_claude_oauth_token_kind,
                load_claude_oauth_token_for_account,
            )
            if has_claude_oauth_token_kind(requested_account):
                token = load_claude_oauth_token_for_account(requested_account)
                env_overrides = {"CLAUDE_CODE_OAUTH_TOKEN": token.token}
                env_display_overrides = {
                    "CLAUDE_CODE_OAUTH_TOKEN": token.safe_display_value(),
                }
                preamble_lines.append(_format_claude_preamble_line(self, requested_account))

        from agentos.agent.run_runtime import AgentCommand, agent_command_with_env_overrides
        base_command = self._build_command_with_env(
            self._claude_command_config(command_config),
            env_overrides=self._run_env_overrides(),
        )
        command = agent_command_with_env_overrides(
            base_command,
            env_overrides=env_overrides,
            env_display_overrides=env_display_overrides,
        )
        return AgentRunDryResult(
            lines=(*preamble_lines, *command.setup_lines, format_agent_command(command)),
        )

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

    def _claude_command_config(self, command_config: AgentCommandConfig) -> AgentCommandConfig:
        if command_config.interaction_mode != "non_interactive":
            return command_config
        extra_argv = ("--dangerously-skip-permissions",)
        return AgentCommandConfig(
            prompt=command_config.prompt,
            argv=extra_argv + command_config.argv,
            model=command_config.model,
            account=command_config.account,
            interaction_mode=command_config.interaction_mode,
        )

    def _run_env_overrides(self) -> dict[str, str]:
        env_overrides = dict(self.env)
        if self.home is not None:
            env_overrides[CLAUDE_CONFIG_DIR_ENV_VAR] = str(self.home)
        return env_overrides


def _format_claude_preamble_line(agent: ClaudeAgent, account: str) -> str:
    profile = agent.instance_id or "<default>"
    return f"[agentos] injected claude oauth token for profile {profile} from account {account}"


def validate_profile(profile_json: dict[str, object]) -> None:
    pass


__all__ = ["ClaudeAgent", "validate_profile"]
