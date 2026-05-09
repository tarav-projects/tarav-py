from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from agentos._core.errors import CliError
from agentos.providers import require_canonical_provider_spec


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
class AgentConfig:
    provider: str
    instance_id: str | None = None
    label: str | None = None
    homes: tuple[tuple[str, Path], ...] = ()
    cli_command: tuple[str, ...] = ()
    run_args: tuple[str, ...] = ()
    env: tuple[tuple[str, str], ...] = ()
    timeout_sec: int | None = None
    default_model: str | None = None
    model_flag: str | None = None
    prompt_flag: str | None = None
    is_default: bool = False
    fingerprint: str | None = None


class TerminalAgentLike(Protocol):
    provider: str
    instance_id: str | None
    cli_command: tuple[str, ...]
    run_args: tuple[str, ...]
    default_model: str | None
    model_flag: str | None
    prompt_flag: str | None
    env: tuple[tuple[str, str], ...]


def provider_session_paths(
    provider: str,
    homes: tuple[tuple[str, Path], ...],
) -> tuple[tuple[Path, ...], tuple[Path, ...]]:
    direct_targets: list[Path] = []
    sqlite_db_paths: list[Path] = []
    provider_spec = require_canonical_provider_spec(provider)
    slots_by_key = {slot.key: slot for slot in provider_spec.home_slots}
    for key, home in homes:
        slot = slots_by_key.get(key)
        if slot is None:
            continue
        slot_direct_targets, _, slot_sqlite_db_paths = slot.build_paths(home=home)
        direct_targets.extend(slot_direct_targets)
        sqlite_db_paths.extend(slot_sqlite_db_paths)
    return tuple(direct_targets), tuple(sqlite_db_paths)


def resolve_terminal_agent_run(
    agent: TerminalAgentLike,
    request: AgentRunRequest,
) -> ResolvedAgentRun:
    if not agent.cli_command:
        raise CliError(
            f"agent {agent.instance_id or '<default>'} for provider {agent.provider} has no cli_command"
        )

    command = list(agent.cli_command)
    command.extend(agent.run_args)
    effective_model = request.model or agent.default_model
    if effective_model is not None:
        if agent.model_flag is None:
            raise CliError(
                f"agent {agent.instance_id or '<default>'} for provider {agent.provider} does not define model_flag"
            )
        command.extend([agent.model_flag, effective_model])

    if agent.prompt_flag is not None:
        command.extend([agent.prompt_flag, request.prompt])
    else:
        command.append(request.prompt)

    return ResolvedAgentRun(
        provider=agent.provider,
        instance_id=agent.instance_id,
        command=tuple(command),
        env=agent.env,
    )


__all__ = [
    "AgentConfig",
    "AgentRunRequest",
    "provider_session_paths",
    "resolve_terminal_agent_run",
    "ResolvedAgentRun",
    "TerminalAgentLike",
]
