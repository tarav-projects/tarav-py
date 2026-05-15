from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class MonitorTarget:
    provider: str
    account: str
    home: Path

    def summary(self) -> dict[str, str]:
        return {
            "provider": self.provider,
            "account": self.account,
            "home": str(self.home),
        }


@dataclass(frozen=True)
class MonitorWorkflowConfig:
    name: str
    targets: tuple[MonitorTarget, ...]
    refresh_interval_sec: float
    raw_config: dict[str, object]


@dataclass
class MonitorState:
    tick: int = 0
    workflow_run_counts: dict[str, int] = field(default_factory=dict)
    data: dict[str, object] = field(default_factory=dict)


@dataclass
class MonitorFrame:
    tick: int = 0
    blocks: list[dict[str, object]] = field(default_factory=list)
    status_lines: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def add_block(self, title: str, lines: list[str], data: dict[str, object] | None = None) -> None:
        block: dict[str, object] = {
            "title": title,
            "lines": lines,
        }
        if data is not None:
            block["data"] = data
        self.blocks.append(block)

    def add_error(self, message: str) -> None:
        self.errors.append(message)

    def replace_block(
        self,
        index: int,
        *,
        title: str,
        lines: list[str],
        data: dict[str, object] | None = None,
    ) -> None:
        block: dict[str, object] = {
            "title": title,
            "lines": lines,
        }
        if data is not None:
            block["data"] = data
        self.blocks[index] = block
