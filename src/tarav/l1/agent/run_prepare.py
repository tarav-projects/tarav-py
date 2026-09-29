# $kw: --from Agentos.Agent.Adapter --from Agent.Profile
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from tarav.l1.agent.run_runtime import AgentCommandConfig

if TYPE_CHECKING:
    from tarav.l1.agent.primitives import AgentConfig


@dataclass(frozen=True)
class AgentRunPrepareRequest:
    agent: AgentConfig
    command_config: AgentCommandConfig
    start_path: Path
    dry_run: bool
    source: str


@dataclass(frozen=True)
class AgentRunPrepareResult:
    preamble_lines: tuple[str, ...] = ()
    env_overrides: dict[str, str] = field(default_factory=dict)
    env_display_overrides: dict[str, str] = field(default_factory=dict)
    action_summaries: tuple[dict[str, object], ...] = ()


def empty_agent_run_prepare_result() -> AgentRunPrepareResult:
    return AgentRunPrepareResult()
