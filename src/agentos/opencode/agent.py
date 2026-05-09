from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentos._core.errors import CliError
from agentos.agent.primitives import (
    AgentConfig,
    AgentRunRequest,
    provider_session_paths,
    ResolvedAgentRun,
    resolve_terminal_agent_run,
)
from agentos.opencode.session import (
    OpencodeSession,
    OpencodeSessionRef,
    discover_opencode_session_refs,
    load_opencode_session,
)


OPENCODE_PROVIDER = "opencode"


@dataclass(frozen=True)
class OpencodeAgent:
    instance_id: str | None = None
    label: str | None = None
    homes: tuple[tuple[str, Path], ...] = ()
    cli_command: tuple[str, ...] = ()
    run_args: tuple[str, ...] = ()
    env: tuple[tuple[str, str], ...] = ()
    default_model: str | None = None
    model_flag: str | None = None
    prompt_flag: str | None = None
    is_default: bool = False
    fingerprint: str | None = None

    @classmethod
    def from_config(cls, config: AgentConfig) -> OpencodeAgent:
        if config.provider != OPENCODE_PROVIDER:
            raise CliError(f"cannot build OpenCode.Agent from provider {config.provider}")
        return cls(
            instance_id=config.instance_id,
            label=config.label,
            homes=config.homes,
            cli_command=config.cli_command,
            run_args=config.run_args,
            env=config.env,
            default_model=config.default_model,
            model_flag=config.model_flag,
            prompt_flag=config.prompt_flag,
            is_default=config.is_default,
            fingerprint=config.fingerprint,
        )

    @property
    def provider(self) -> str:
        return OPENCODE_PROVIDER

    def resolve_run(self, request: AgentRunRequest) -> ResolvedAgentRun:
        return resolve_terminal_agent_run(self, request)

    def discover_session_refs(self) -> tuple[OpencodeSessionRef, ...]:
        direct_targets, sqlite_db_paths = provider_session_paths(OPENCODE_PROVIDER, self.homes)
        return discover_opencode_session_refs(
            targets=direct_targets,
            sqlite_db_paths=sqlite_db_paths,
        )

    def load_session(self, session_ref: OpencodeSessionRef) -> OpencodeSession:
        return load_opencode_session(session_ref)

    def summary(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"family": self.provider, "is_default": self.is_default}
        if self.fingerprint is not None:
            payload["fingerprint"] = self.fingerprint
        if self.instance_id is not None:
            payload["instance_id"] = self.instance_id
        if self.label is not None:
            payload["label"] = self.label
        if self.homes:
            payload["homes"] = {key: str(path) for key, path in self.homes}
        if self.cli_command:
            payload["cli_command"] = list(self.cli_command)
        if self.run_args:
            payload["run_args"] = list(self.run_args)
        if self.env:
            payload["env"] = {key: value for key, value in self.env}
        if self.default_model is not None:
            payload["default_model"] = self.default_model
        if self.model_flag is not None:
            payload["model_flag"] = self.model_flag
        if self.prompt_flag is not None:
            payload["prompt_flag"] = self.prompt_flag
        return payload


__all__ = ["OpencodeAgent"]
