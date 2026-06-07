from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from agentos.agent.primitives import Agent
from agentos.agent.run_runtime import AgentCommandConfig


@dataclass(frozen=True)
class AgentRunPreflightResult:
    lines: tuple[str, ...] = ()
    env_overrides: dict[str, str] = field(default_factory=dict)
    env_display_overrides: dict[str, str] = field(default_factory=dict)


def run_agent_preflight(
    *,
    agent: Agent,
    command_config: AgentCommandConfig,
    start_path: Path,
    dry_run: bool = False,
    source: str = "agent.run",
) -> AgentRunPreflightResult:
    if agent.provider == "codex":
        return _run_codex_preflight(
            agent=agent,
            command_config=command_config,
            start_path=start_path,
            dry_run=dry_run,
            source=source,
        )
    if agent.provider == "claude-code":
        return _run_claude_preflight(
            agent=agent,
            command_config=command_config,
        )
    return AgentRunPreflightResult()


def _run_claude_preflight(
    *,
    agent: Agent,
    command_config: AgentCommandConfig,
) -> AgentRunPreflightResult:
    requested_account = _normalized_account(command_config.account) or _agent_account(agent)
    if requested_account is None:
        return AgentRunPreflightResult()

    from agentos.claude.account_registry import load_claude_oauth_token_for_account

    token = load_claude_oauth_token_for_account(requested_account)
    return AgentRunPreflightResult(
        lines=(
            _format_claude_preflight_line(
                agent=agent,
                account=requested_account,
            ),
        ),
        env_overrides={"CLAUDE_CODE_OAUTH_TOKEN": token.token},
        env_display_overrides={
            "CLAUDE_CODE_OAUTH_TOKEN": token.safe_display_value(),
        },
    )


def _run_codex_preflight(
    *,
    agent: Agent,
    command_config: AgentCommandConfig,
    start_path: Path,
    dry_run: bool,
    source: str,
) -> AgentRunPreflightResult:
    if agent.home is None:
        return AgentRunPreflightResult()

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
                return AgentRunPreflightResult(
                    lines=(
                        _format_preflight_line(
                            action="would materialize",
                            agent=agent,
                            account=requested_account,
                        ),
                    )
                )
            payload = link_codex_account_to_home(
                home=agent.home,
                account=requested_account,
                record_event=False,
            )
            _record_materialized_event(
                agent=agent,
                account=str(payload.get("account", requested_account)),
                artifact_id=_payload_string(payload, "artifact_id"),
                source=source,
            )
            return AgentRunPreflightResult(
                lines=(
                    _format_preflight_line(
                        action="materialized",
                        agent=agent,
                        account=str(payload.get("account", requested_account)),
                    ),
                )
            )
        if home_account != requested_account:
            if dry_run:
                return AgentRunPreflightResult(
                    lines=(
                        _format_preflight_line(
                            action="would materialize",
                            agent=agent,
                            account=requested_account,
                        ),
                    )
                )
            payload = link_codex_account_to_home(
                home=agent.home,
                account=requested_account,
            )
            _record_materialized_event(
                agent=agent,
                account=str(payload.get("account", requested_account)),
                artifact_id=_payload_string(payload, "artifact_id"),
                source=source,
            )
            return AgentRunPreflightResult(
                lines=(
                    _format_preflight_line(
                        action="materialized",
                        agent=agent,
                        account=str(payload.get("account", requested_account)),
                    ),
                )
            )
        return _sync_codex_linked_home(
            agent=agent,
            account=requested_account,
            start_path=start_path,
            dry_run=dry_run,
            source=source,
        )

    if home_account is None:
        return AgentRunPreflightResult()
    return _sync_codex_linked_home(
        agent=agent,
        account=home_account,
        start_path=start_path,
        dry_run=dry_run,
        source=source,
    )


def _sync_codex_linked_home(
    *,
    agent: Agent,
    account: str,
    start_path: Path,
    dry_run: bool,
    source: str,
) -> AgentRunPreflightResult:
    if agent.home is None:
        return AgentRunPreflightResult()

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
        return AgentRunPreflightResult()
    if not dry_run:
        _record_materialized_event(
            agent=agent,
            account=account,
            artifact_id=_synced_artifact_id(payload),
            source=source,
        )
    action = "would refresh" if dry_run else "refreshed"
    return AgentRunPreflightResult(
        lines=(
            _format_preflight_line(
                action=action,
                agent=agent,
                account=account,
            ),
        )
    )


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
    agent: Agent,
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


def _agent_account(agent: Agent) -> str | None:
    if agent.account is None:
        return None
    if agent.account.provider != agent.provider:
        return None
    return _normalized_account(agent.account.account)


def _format_preflight_line(*, action: str, agent: Agent, account: str) -> str:
    profile = agent.instance_id or "<default>"
    return f"[agentos] {action} codex auth for profile {profile} from account {account}"


def _format_claude_preflight_line(*, agent: Agent, account: str) -> str:
    profile = agent.instance_id or "<default>"
    return f"[agentos] injected claude oauth token for profile {profile} from account {account}"


__all__ = [
    "AgentRunPreflightResult",
    "run_agent_preflight",
]
