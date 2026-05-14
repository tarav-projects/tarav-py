from __future__ import annotations

import json

from agentos.agent.monitor.models import MonitorFrame, MonitorState


def monitor_result_payload(frame: MonitorFrame, state: MonitorState) -> dict[str, object]:
    return {
        "status": "ok",
        "command": "agent accounts monitor",
        "tick": frame.tick,
        "workflow_run_counts": state.workflow_run_counts,
        "state": state.data,
        "frame": {
            "tick": frame.tick,
            "blocks": frame.blocks,
            "status_lines": frame.status_lines,
            "warnings": frame.warnings,
            "errors": frame.errors,
        },
    }


def format_monitor_frame(frame: MonitorFrame) -> str:
    lines = ["Agent accounts monitor", f"Tick: {frame.tick}"]
    if frame.status_lines:
        lines.extend(f"Status: {line}" for line in frame.status_lines)
    if frame.errors:
        lines.extend(["", "Errors"])
        lines.extend(f"  {error}" for error in frame.errors)
    for block in frame.blocks:
        title = block.get("title")
        if isinstance(title, str):
            lines.extend(["", title])
        block_lines = block.get("lines")
        if isinstance(block_lines, list):
            lines.extend(f"  {line}" for line in block_lines if isinstance(line, str))
    return "\n".join(lines)


def dumps_monitor_json(frame: MonitorFrame, state: MonitorState) -> str:
    return json.dumps(monitor_result_payload(frame, state), indent=2, sort_keys=True)


class RichMonitorRenderer:
    def __init__(self) -> None:
        from rich.console import Console
        from rich.live import Live

        self.console = Console()
        self.live = Live(
            "",
            console=self.console,
            refresh_per_second=4,
            transient=False,
        )

    def __enter__(self) -> RichMonitorRenderer:
        self.live.__enter__()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.live.__exit__(exc_type, exc, traceback)

    def render(self, frame: MonitorFrame, state: MonitorState) -> None:
        from rich.text import Text

        self.live.update(Text(format_monitor_frame(frame)))
