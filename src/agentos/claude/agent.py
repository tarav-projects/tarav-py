from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from agentos._core.errors import CliError
from agentos.agent.account_status import AccountStatus
from agentos.agent.primitives import (
    AgentConfig,
    RunnableMixin,
    adapter_kwargs_from_config,
    agent_session_paths,
)
from agentos.agent.run_runtime import (
    AgentCommand,
    AgentCommandConfig,
    AgentRunConfig,
    AgentRunDryResult,
    AgentRunResult,
    CLAUDE_CODE_OAUTH_TOKEN_ENV_VAR,
    CLAUDE_CONFIG_DIR_ENV_VAR,
    execute_agent_command,
    format_agent_command,
)
from agentos.agent.run_prepare import AgentRunPrepareRequest, AgentRunPrepareResult
from agentos.claude.session import (
    ClaudeSession,
    ClaudeSessionRef,
    discover_claude_session_refs,
    find_claude_session_ref_by_id,
    load_claude_session,
)
from agentos.claude.account_status import _claude_account_status_impl


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
        direct_targets, _ = agent_session_paths(self)
        return discover_claude_session_refs(targets=direct_targets)

    def find_session_ref_by_id(self, session_id: str) -> ClaudeSessionRef | None:
        direct_targets, _ = agent_session_paths(self)
        return find_claude_session_ref_by_id(targets=direct_targets, session_id=session_id)

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
        requested_account = self._resolved_account(command_config)
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
        if base_result.exit_code == 0 and command_config.credential_success_source is not None:
            self._refresh_ambient_auth_after_successful_run(
                requested_account,
                source=command_config.credential_success_source,
            )
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

        from agentos.agent.run_runtime import agent_command_with_env_overrides
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
        requested_account = self._resolved_account(request.command_config)
        if requested_account is None:
            return AgentRunPrepareResult()
        from agentos.claude.account_registry import (
            has_claude_oauth_token_kind,
            load_claude_oauth_token_for_account,
        )

        if not has_claude_oauth_token_kind(requested_account):
            return AgentRunPrepareResult()
        token = load_claude_oauth_token_for_account(requested_account)
        env_display_overrides = {}
        if request.dry_run:
            env_display_overrides[CLAUDE_CODE_OAUTH_TOKEN_ENV_VAR] = token.safe_display_value()
        return AgentRunPrepareResult(
            preamble_lines=(_format_claude_preamble_line(self, requested_account),),
            env_overrides={CLAUDE_CODE_OAUTH_TOKEN_ENV_VAR: token.token},
            env_display_overrides=env_display_overrides,
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

    def _refresh_ambient_auth_after_successful_run(
        self,
        account: str | None,
        *,
        source: str,
    ) -> None:
        if account is None or self.home is None:
            return
        try:
            from agentos.claude.account_registry import (
                has_claude_oauth_token_kind,
                promote_verified_claude_ambient_auth_from_home,
            )

            if has_claude_oauth_token_kind(account):
                return
            promote_verified_claude_ambient_auth_from_home(
                home=self.home,
                account=account,
                source=source,
            )
        except CliError:
            return

    def _run_env_overrides(self) -> dict[str, str]:
        env_overrides = dict(self.env)
        if self.home is not None:
            env_overrides[CLAUDE_CONFIG_DIR_ENV_VAR] = str(self.home)
        return env_overrides


def _format_claude_preamble_line(agent: ClaudeAgent, account: str) -> str:
    profile = agent.profile_id or "<default>"
    return f"[agentos] injected claude oauth token for profile {profile} from account {account}"


def validate_profile(profile_json: dict[str, object]) -> None:
    pass


__all__ = ["ClaudeAgent", "validate_profile"]
