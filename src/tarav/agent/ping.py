# $kw: --from Agentos.Agent.Adapter
"""The agent-ping primitive — run an account's configured liveness ping and
report the outcome.

`AgentPingConfig` (on `AgentConfig`) models *what* a ping is; this module owns the
*operation*: build the non-interactive ping command from the agent's ping config, run
it capture-mode, time it, and validate the exit code + expected number in the output.
It returns a structured `AgentPingResult` for run outcomes and never raises `CliError`
— the consumers (the `agent ping` CLI, the monitor's auto-prime) map the result onto
their own surface. Only a precondition violation (ping disabled / agent not runnable)
raises `AgentPingError`.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path

from tarav.agent.primitives import RunCapable
from tarav.agent.run_runtime import AgentCommandConfig, AgentRunConfig

_PING_NUMBER_PATTERN = re.compile(r"(?<![\d.])-?\d+(?![\d.])")


class AgentPingError(Exception):
    """A ping precondition was not met (ping disabled, or agent not runnable).

    Deliberately not a `CliError` — keeps CLI error types out of the primitive and
    out of the monitor. Consumers translate it onto their own error surface.
    """


@dataclass(frozen=True)
class AgentPingResult:
    ok: bool
    model: str
    elapsed_ms: int
    exit_code: int
    output: str
    failure: str | None


def _run_ping(
    agent,
    *,
    cwd: Path,
    model: str | None = None,
    account: str | None = None,
) -> AgentPingResult:
    """Internal helper behind the ``ping()`` capability method.

    Runs ``agent``'s configured ping and returns the outcome. ``model`` overrides the
    configured ping model (falling back to it when ``None``); ``account`` is passed
    through to the command. Raises `AgentPingError` if the agent's ping is disabled or
    the agent is not `RunCapable`. Consumers call ``agent.ping(...)``, never this
    function directly.
    """
    if not isinstance(agent, RunCapable):
        raise AgentPingError(f"provider {agent.provider} does not support run")
    if not agent.ping_config.enabled:
        raise AgentPingError(
            f"agent {agent.profile_id or '<default>'} for provider "
            f"{agent.provider} has ping disabled"
        )

    command_config = AgentCommandConfig(
        prompt=agent.ping_config.prompt,
        argv=agent.ping_config.argv,
        model=model if model is not None else agent.ping_config.model,
        account=account,
        interaction_mode="non_interactive",
        credential_success_source=None,
    )

    started_at = time.perf_counter()
    result = agent.run(command_config, AgentRunConfig(cwd=cwd, process_mode="capture"))
    elapsed_ms = round((time.perf_counter() - started_at) * 1000)

    output = _ping_output(result.stdout, result.stderr)
    display_model = command_config.model or agent.default_model or "<provider-default>"
    failure = _ping_failure(
        exit_code=result.exit_code,
        output=output,
        expected_number=agent.ping_config.expected_number,
    )
    return AgentPingResult(
        ok=failure is None,
        model=display_model,
        elapsed_ms=elapsed_ms,
        exit_code=result.exit_code,
        output=output,
        failure=failure,
    )


def _ping_output(stdout: str | None, stderr: str | None) -> str:
    return "\n".join(part for part in (stdout, stderr) if part)


def _ping_failure(
    *, exit_code: int, output: str, expected_number: int | None
) -> str | None:
    if exit_code != 0:
        detail = output.strip()
        suffix = f": {detail}" if detail else ""
        return f"provider command exited with {exit_code}{suffix}"
    if expected_number is None:
        return None
    numbers = [int(match.group(0)) for match in _PING_NUMBER_PATTERN.finditer(output)]
    if expected_number not in numbers:
        return (
            f"expected numeric answer {expected_number} "
            "was not present in provider output"
        )
    return None


__all__ = ["AgentPingError", "AgentPingResult"]
