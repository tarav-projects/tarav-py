from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentos._core.errors import CliError
from agentos.agent.primitives import AgentConfig, AgentRunRequest, ResolvedAgentRun


CODEX_PROVIDER = "codex"


@dataclass(frozen=True)
class CodexAgent:
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

    @classmethod
    def from_config(cls, config: AgentConfig) -> CodexAgent:
        if config.provider != CODEX_PROVIDER:
            raise CliError(f"cannot build Codex.Agent from provider {config.provider}")
        return cls(
            instance_id=config.instance_id,
            label=config.label,
            homes=config.homes,
            cli_command=config.cli_command,
            run_args=config.run_args,
            env=config.env,
            timeout_sec=config.timeout_sec,
            default_model=config.default_model,
            model_flag=config.model_flag,
            prompt_flag=config.prompt_flag,
            is_default=config.is_default,
            fingerprint=config.fingerprint,
        )

    @property
    def provider(self) -> str:
        return CODEX_PROVIDER

    def homes_map(self) -> dict[str, Path]:
        return {key: path for key, path in self.homes}

    def runner(self) -> CodexAgentRunner:
        return CodexAgentRunner(agent=self)

    def resolve_run(self, request: AgentRunRequest) -> ResolvedAgentRun:
        return self.runner().resolve(request)

    def summary(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "family": self.provider,
            "is_default": self.is_default,
        }
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
        if self.timeout_sec is not None:
            payload["timeout_sec"] = self.timeout_sec
        if self.default_model is not None:
            payload["default_model"] = self.default_model
        if self.model_flag is not None:
            payload["model_flag"] = self.model_flag
        if self.prompt_flag is not None:
            payload["prompt_flag"] = self.prompt_flag
        return payload


@dataclass(frozen=True)
class CodexAgentRunner:
    agent: CodexAgent

    def resolve(self, request: AgentRunRequest) -> ResolvedAgentRun:
        if not self.agent.cli_command:
            raise CliError(
                f"agent {self.agent.instance_id or '<default>'} for provider codex has no cli_command"
            )

        command = list(self.agent.cli_command)
        command.extend(self.agent.run_args)
        effective_model = request.model or self.agent.default_model
        if effective_model is not None:
            if self.agent.model_flag is None:
                raise CliError(
                    f"agent {self.agent.instance_id or '<default>'} for provider codex does not define model_flag"
                )
            command.extend([self.agent.model_flag, effective_model])

        if self.agent.prompt_flag is not None:
            command.extend([self.agent.prompt_flag, request.prompt])
        else:
            command.append(request.prompt)

        return ResolvedAgentRun(
            provider=self.agent.provider,
            instance_id=self.agent.instance_id,
            command=tuple(command),
            env=self.agent.env,
        )


__all__ = [
    "CodexAgent",
    "CodexAgentRunner",
]
