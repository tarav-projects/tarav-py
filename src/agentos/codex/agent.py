from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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
from agentos.codex.session import (
    CodexSession,
    CodexSessionRef,
    discover_codex_session_refs,
    find_codex_session_ref_by_id,
    load_codex_session,
)
from agentos.codex.account_status import _codex_account_status_impl


CODEX_PROVIDER = "codex"
CODEX_HOME_ENV_VAR = "CODEX_HOME"


@dataclass(frozen=True)
class CodexAgent(AgentBase):

    @classmethod
    def from_config(cls, config: AgentConfig) -> CodexAgent:
        return cls(
            **agent_base_kwargs_for_provider(
                config,
                provider=CODEX_PROVIDER,
                agent_name="Codex.Agent",
            )
        )

    @property
    def provider(self) -> str:
        return CODEX_PROVIDER

    def discover_session_refs(self) -> tuple[CodexSessionRef, ...]:
        return discover_codex_session_refs(targets=self.session_discovery_targets())

    def find_session_ref_by_id(self, session_id: str) -> CodexSessionRef | None:
        return find_codex_session_ref_by_id(
            targets=self.session_discovery_targets(),
            session_id=session_id,
        )

    def load_session(self, session_ref: CodexSessionRef) -> CodexSession:
        return load_codex_session(session_ref)

    def session_discovery_targets(self) -> tuple[Path, ...]:
        direct_targets, sqlite_db_paths = agent_session_paths(self)
        return direct_targets + sqlite_db_paths

    def _build_command(self, command_config: AgentCommandConfig) -> AgentCommand:
        effective_config = self._codex_command_config(command_config)
        return self._build_command_with_env(
            effective_config,
            env_overrides=self._run_env_overrides(),
        )

    def run(
        self,
        command_config: AgentCommandConfig,
        run_config: AgentRunConfig,
    ) -> AgentRunResult:
        from agentos._core.project import normalize_project_target
        start_path = run_config.cwd
        preamble_lines = _run_codex_preflight(
            self,
            command_config=command_config,
            start_path=start_path,
            dry_run=False,
            source="agent.run",
        )
        for line in preamble_lines:
            print(line)
        command = self._build_command(command_config)
        base_result = execute_agent_command(command, run_config=self.resolve_run_config(run_config))
        return AgentRunResult(
            exit_code=base_result.exit_code,
            stdout=base_result.stdout,
            stderr=base_result.stderr,
            preamble_lines=tuple(preamble_lines),
        )

    def run_dry(self, command_config: AgentCommandConfig) -> AgentRunDryResult:
        from agentos._core.project import normalize_project_target
        start_path = Path.cwd().resolve()
        preamble_lines = _run_codex_preflight(
            self,
            command_config=command_config,
            start_path=start_path,
            dry_run=True,
            source="agent.run",
        )
        command = self._build_command(command_config)
        return AgentRunDryResult(
            lines=(*preamble_lines, *command.setup_lines, format_agent_command(command)),
        )

    def account_status(
        self,
        *,
        record_usage: bool = True,
        fallback_to_usage_registry: bool = True,
    ) -> AccountStatus:
        return _codex_account_status_impl(
            self,
            record_usage=record_usage,
            fallback_to_usage_registry=fallback_to_usage_registry,
        )

    def _codex_command_config(self, command_config: AgentCommandConfig) -> AgentCommandConfig:
        if command_config.interaction_mode != "non_interactive":
            return command_config
        if command_config.prompt is None or command_config.argv:
            return command_config
        return AgentCommandConfig(
            prompt=None,
            argv=("exec", command_config.prompt),
            model=command_config.model,
            account=command_config.account,
            interaction_mode=command_config.interaction_mode,
        )

    def _run_env_overrides(self) -> dict[str, str]:
        env_overrides = dict(self.env)
        if self.home is not None:
            env_overrides[CODEX_HOME_ENV_VAR] = str(self.home)
        return env_overrides


def _run_codex_preflight(
    agent: CodexAgent,
    *,
    command_config: AgentCommandConfig,
    start_path: Path,
    dry_run: bool,
    source: str,
) -> tuple[str, ...]:
    if agent.home is None:
        return ()

    from agentos.codex.account_registry import (
        inspect_codex_account_home,
        link_codex_account_to_home,
    )

    status = inspect_codex_account_home(home=agent.home)
    home_account = _active_home_account(status)
    profile_account = _agent_account(agent)
    requested_account = _normalized_account(command_config.account) or profile_account

    if requested_account is not None:
        if profile_account is not None and _status_classification(status) != "matching-active":
            if dry_run:
                return (_format_codex_preflight_line("would materialize", agent, requested_account),)
            payload = link_codex_account_to_home(
                home=agent.home,
                account=requested_account,
                record_event=False,
            )
            _record_materialized_event(agent=agent, account=str(payload.get("account", requested_account)), artifact_id=_payload_string(payload, "artifact_id"), source=source)
            return (_format_codex_preflight_line("materialized", agent, str(payload.get("account", requested_account))),)
        if home_account != requested_account:
            if dry_run:
                return (_format_codex_preflight_line("would materialize", agent, requested_account),)
            payload = link_codex_account_to_home(
                home=agent.home,
                account=requested_account,
            )
            _record_materialized_event(agent=agent, account=str(payload.get("account", requested_account)), artifact_id=_payload_string(payload, "artifact_id"), source=source)
            return (_format_codex_preflight_line("materialized", agent, str(payload.get("account", requested_account))),)
        return _sync_codex_linked_home(agent=agent, account=requested_account, start_path=start_path, dry_run=dry_run, source=source)

    if home_account is None:
        return ()
    return _sync_codex_linked_home(agent=agent, account=home_account, start_path=start_path, dry_run=dry_run, source=source)


def _sync_codex_linked_home(
    *,
    agent: CodexAgent,
    account: str,
    start_path: Path,
    dry_run: bool,
    source: str,
) -> tuple[str, ...]:
    if agent.home is None:
        return ()

    from agentos.codex.account_reconcile import reconcile_codex_accounts

    payload = reconcile_codex_accounts(
        account=account,
        home=agent.home,
        start_path=start_path,
        register_discovered=True,
        sync_homes=True,
        check=dry_run,
        record_event=False,
    )
    if not _payload_has_home_sync_action(payload):
        return ()
    if not dry_run:
        _record_materialized_event(
            agent=agent,
            account=account,
            artifact_id=_synced_artifact_id(payload),
            source=source,
        )
    action = "would refresh" if dry_run else "refreshed"
    return (_format_codex_preflight_line(action, agent, account),)


def _payload_has_home_sync_action(payload: dict[str, object]) -> bool:
    actions = payload.get("actions")
    if not isinstance(actions, list):
        return False
    return any(
        isinstance(action, dict)
        and action.get("kind") in {"would_sync_home", "synced_home"}
        for action in actions
    )


def _synced_artifact_id(payload: dict[str, object]) -> str | None:
    actions = payload.get("actions")
    if not isinstance(actions, list):
        return None
    for action in actions:
        if not isinstance(action, dict) or action.get("kind") != "synced_home":
            continue
        artifact_id = _payload_string(action, "artifact_id")
        if artifact_id is not None:
            return artifact_id
    return None


def _record_materialized_event(
    *,
    agent: CodexAgent,
    account: str,
    artifact_id: str | None,
    source: str,
) -> None:
    if agent.home is None:
        return
    from agentos.agent.account_registry import record_account_event

    record_account_event(
        event_type="account.auth.materialized",
        command=source,
        argv=(),
        status="ok",
        payload={
            "provider": agent.provider,
            "profile": agent.instance_id,
            "home": str(agent.home),
            "account": account,
            "artifact_id": artifact_id,
        },
    )


def _payload_string(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _active_home_account(status: dict[str, object]) -> str | None:
    if _status_classification(status) != "matching-active":
        return None
    matches = status.get("account_registry_matches")
    auth = status.get("auth")
    if not isinstance(matches, list) or not isinstance(auth, dict):
        return None
    artifact_id = _payload_string(auth, "artifact_id")
    accounts = sorted(
        account
        for record in matches
        if isinstance(record, dict)
        and record.get("active_artifact_id") == artifact_id
        and (account := _payload_string(record, "account")) is not None
    )
    if len(accounts) == 1:
        return accounts[0]
    return None


def _status_classification(status: dict[str, object]) -> str | None:
    value = status.get("classification")
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _normalized_account(account: str | None) -> str | None:
    if account is None:
        return None
    normalized = account.strip()
    return normalized or None


def _agent_account(agent: CodexAgent) -> str | None:
    if agent.account is None:
        return None
    if agent.account.provider != agent.provider:
        return None
    return _normalized_account(agent.account.account)


def _format_codex_preflight_line(action: str, agent: CodexAgent, account: str) -> str:
    profile = agent.instance_id or "<default>"
    return f"[agentos] {action} codex auth for profile {profile} from account {account}"


def validate_profile(profile_json: dict[str, object]) -> None:
    pass


__all__ = ["CodexAgent", "validate_profile"]
