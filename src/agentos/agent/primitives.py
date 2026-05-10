from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

from agentos._core.errors import CliError
from agentos.providers import ProviderHomeAnchor
from agentos.providers import require_canonical_provider_spec


@dataclass(frozen=True)
class AgentRunCommand:
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
    direct_targets: tuple[Path, ...] = ()
    grep_targets: tuple[Path, ...] = ()
    sqlite_db_paths: tuple[Path, ...] = ()
    identity_anchors: tuple[ProviderHomeAnchor, ...] = ()
    chatlas_includes: tuple[str, ...] = ()
    chatlas_excludes: tuple[str, ...] = ()
    account_live_usage_refresh: bool | None = None
    account_usage_progression_limit: str | None = None

    def computed_fingerprint(self) -> str:
        if self.fingerprint is not None:
            return self.fingerprint
        return agent_identity_fingerprint(
            provider=self.provider,
            anchors=self.identity_anchors,
            direct_targets=self.direct_targets,
            sqlite_db_paths=self.sqlite_db_paths,
        )

    def identity_key(self) -> tuple[object, ...]:
        if self.identity_anchors:
            return (
                self.provider,
                tuple(anchor.identity_key() for anchor in self.identity_anchors),
            )
        return (
            self.provider,
            self.instance_id,
            tuple((key, str(path)) for key, path in self.homes),
            tuple(str(path) for path in self.direct_targets),
            tuple(str(path) for path in self.grep_targets),
            tuple(str(path) for path in self.sqlite_db_paths),
            self.cli_command,
            self.run_args,
            self.env,
            self.timeout_sec,
            self.default_model,
            self.model_flag,
            self.prompt_flag,
            self.chatlas_includes,
            self.chatlas_excludes,
            self.account_live_usage_refresh,
            self.account_usage_progression_limit,
        )

    def uri_key(self) -> str:
        return quote(self.computed_fingerprint(), safe="")


class Agent(Protocol):
    provider: str
    instance_id: str | None
    label: str | None
    homes: tuple[tuple[str, Path], ...]
    cli_command: tuple[str, ...]
    run_args: tuple[str, ...]
    env: tuple[tuple[str, str], ...]
    timeout_sec: int | None
    default_model: str | None
    model_flag: str | None
    prompt_flag: str | None
    is_default: bool
    fingerprint: str | None
    direct_targets: tuple[Path, ...]
    grep_targets: tuple[Path, ...]
    sqlite_db_paths: tuple[Path, ...]
    identity_anchors: tuple[ProviderHomeAnchor, ...]
    chatlas_includes: tuple[str, ...]
    chatlas_excludes: tuple[str, ...]
    account_live_usage_refresh: bool | None
    account_usage_progression_limit: str | None

    def summary(self) -> dict[str, object]: ...

    def resolve_run(self, *, prompt: str, model: str | None = None) -> AgentRunCommand: ...


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


def agent_session_paths(agent: Agent) -> tuple[tuple[Path, ...], tuple[Path, ...]]:
    direct_targets, sqlite_db_paths = provider_session_paths(agent.provider, agent.homes)
    return (
        tuple(dict.fromkeys((*direct_targets, *agent.direct_targets))),
        tuple(dict.fromkeys((*sqlite_db_paths, *agent.sqlite_db_paths))),
    )


def agent_identity_fingerprint(
    *,
    provider: str,
    anchors: tuple[ProviderHomeAnchor, ...],
    direct_targets: tuple[Path, ...] = (),
    sqlite_db_paths: tuple[Path, ...] = (),
) -> str:
    digest = hashlib.sha256()
    digest.update(provider.encode("utf-8"))
    effective_anchors = anchors
    if not effective_anchors:
        effective_anchors = tuple(
            ProviderHomeAnchor(role=f"direct_target_{index + 1}", path=path)
            for index, path in enumerate(direct_targets)
        ) + tuple(
            ProviderHomeAnchor(role=f"sqlite_db_{index + 1}", path=path)
            for index, path in enumerate(sqlite_db_paths)
        )
    for anchor in effective_anchors:
        digest.update(b"\0")
        digest.update(anchor.role.encode("utf-8"))
        digest.update(b"\0")
        digest.update((anchor.slot or "").encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(anchor.path).encode("utf-8"))
    return digest.hexdigest()


def agent_fingerprint(agent: Agent) -> str:
    if agent.fingerprint is not None:
        return agent.fingerprint
    return agent_identity_fingerprint(
        provider=agent.provider,
        anchors=agent.identity_anchors,
        direct_targets=agent.direct_targets,
        sqlite_db_paths=agent.sqlite_db_paths,
    )


def agent_identity_key(agent: Agent) -> tuple[object, ...]:
    if agent.identity_anchors:
        return (
            agent.provider,
            tuple(anchor.identity_key() for anchor in agent.identity_anchors),
        )
    return (
        agent.provider,
        agent.instance_id,
        tuple((key, str(path)) for key, path in agent.homes),
        tuple(str(path) for path in agent.direct_targets),
        tuple(str(path) for path in agent.grep_targets),
        tuple(str(path) for path in agent.sqlite_db_paths),
        agent.cli_command,
        agent.run_args,
        agent.env,
        agent.timeout_sec,
        agent.default_model,
        agent.model_flag,
        agent.prompt_flag,
        agent.chatlas_includes,
        agent.chatlas_excludes,
        agent.account_live_usage_refresh,
        agent.account_usage_progression_limit,
    )


def agent_uri_key(agent: Agent) -> str:
    return quote(agent_fingerprint(agent), safe="")


def resolve_terminal_agent_run(
    agent: Agent,
    *,
    prompt: str,
    model: str | None = None,
) -> AgentRunCommand:
    if not agent.cli_command:
        raise CliError(
            f"agent {agent.instance_id or '<default>'} for provider {agent.provider} has no cli_command"
        )

    command = list(agent.cli_command)
    command.extend(agent.run_args)
    effective_model = model or agent.default_model
    if effective_model is not None:
        if agent.model_flag is None:
            raise CliError(
                f"agent {agent.instance_id or '<default>'} for provider {agent.provider} does not define model_flag"
            )
        command.extend([agent.model_flag, effective_model])

    if agent.prompt_flag is not None:
        command.extend([agent.prompt_flag, prompt])
    else:
        command.append(prompt)

    return AgentRunCommand(
        provider=agent.provider,
        instance_id=agent.instance_id,
        command=tuple(command),
        env=agent.env,
    )


__all__ = [
    "Agent",
    "AgentConfig",
    "AgentRunCommand",
    "agent_fingerprint",
    "agent_identity_fingerprint",
    "agent_identity_key",
    "agent_session_paths",
    "agent_uri_key",
    "provider_session_paths",
    "resolve_terminal_agent_run",
]
