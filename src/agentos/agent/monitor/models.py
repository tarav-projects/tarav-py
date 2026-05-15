from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


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


@dataclass(frozen=True)
class MonitorTextRow:
    text: str
    kind: Literal["text"] = "text"

    def summary(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "text": self.text,
        }


@dataclass(frozen=True)
class MonitorUsageTimeRow:
    text: str
    used_percent: int
    elapsed_percent: int
    ratio: float | None
    label: str
    kind: Literal["usage_time"] = "usage_time"

    def summary(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "text": self.text,
            "used_percent": self.used_percent,
            "elapsed_percent": self.elapsed_percent,
            "ratio": self.ratio,
            "label": self.label,
        }


@dataclass(frozen=True)
class MonitorResetRow:
    text: str
    elapsed_percent: int
    marker_percent: int | None = None
    kind: Literal["reset"] = "reset"

    def summary(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "text": self.text,
            "elapsed_percent": self.elapsed_percent,
            "marker_percent": self.marker_percent,
        }


MonitorRow = MonitorTextRow | MonitorUsageTimeRow | MonitorResetRow


@dataclass
class MonitorFrame:
    tick: int = 0
    blocks: list[dict[str, object]] = field(default_factory=list)
    status_lines: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def prepare(self, *, tick: int) -> None:
        self.tick = tick
        self.blocks.clear()
        self.status_lines.clear()
        self.warnings.clear()
        self.errors.clear()

    def add_block(
        self,
        title: str,
        lines: list[str] | None = None,
        data: dict[str, object] | None = None,
        rows: list[MonitorRow] | None = None,
    ) -> None:
        block = monitor_block(title=title, lines=lines, data=data, rows=rows)
        self.blocks.append(block)

    def add_error(self, message: str) -> None:
        self.errors.append(message)


def monitor_block(
    *,
    title: str,
    lines: list[str] | None = None,
    data: dict[str, object] | None = None,
    rows: list[MonitorRow] | None = None,
) -> dict[str, object]:
    if rows is None:
        rows = [MonitorTextRow(line) for line in lines or []]
    if lines is None:
        lines = [row.text for row in rows]

    block: dict[str, object] = {
        "title": title,
        "lines": lines,
        "rows": rows,
    }
    if data is not None:
        block["data"] = data
    return block


def monitor_row_payload(row: object) -> dict[str, object] | None:
    if isinstance(row, MonitorTextRow | MonitorUsageTimeRow | MonitorResetRow):
        return row.summary()
    if isinstance(row, dict):
        return row
    return None


def monitor_block_payload(block: dict[str, object]) -> dict[str, object]:
    payload = dict(block)
    rows = block.get("rows")
    if isinstance(rows, list):
        payload["rows"] = [
            row_payload
            for row in rows
            if (row_payload := monitor_row_payload(row)) is not None
        ]
    return payload


def monitor_block_rows(block: dict[str, object]) -> list[MonitorRow]:
    rows = block.get("rows")
    if isinstance(rows, list) and all(
        isinstance(row, MonitorTextRow | MonitorUsageTimeRow | MonitorResetRow)
        for row in rows
    ):
        return rows
    lines = block.get("lines")
    if isinstance(lines, list):
        return [MonitorTextRow(line) for line in lines if isinstance(line, str)]
    return []
