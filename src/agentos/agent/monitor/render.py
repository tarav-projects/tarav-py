from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass
from typing import Any

from agentos.agent.monitor.models import (
    DEFAULT_MONITOR_RENDER_CONTEXT,
    MonitorFrame,
    MonitorRenderContext,
    MonitorResetRow,
    MonitorRow,
    MonitorState,
    MonitorUsageTimeRow,
    _cell_offset_to_text_index,
    monitor_block_payload,
    monitor_block_rows,
)

_MONITOR_TRACK_STYLE = "bright_white on grey15"
_MONITOR_USAGE_BAR_PALETTE = (
    "#14b8a6",
    "#84cc16",
    "#facc15",
    "#f97316",
    "#dc2626",
)
_MONITOR_RESET_BAR_PALETTE = (
    "#0f766e",
    "#0891b2",
    "#2563eb",
)
_MONITOR_REFRESH_PER_SECOND = 4


@dataclass(frozen=True)
class _MonitorRenderTextRow:
    text: str


@dataclass(frozen=True)
class _MonitorRenderBarRow:
    row: MonitorUsageTimeRow | MonitorResetRow
    text: str


def monitor_result_payload(
    frame: MonitorFrame, state: MonitorState
) -> dict[str, object]:
    return {
        "status": "ok",
        "command": "agent accounts monitor",
        "tick": frame.tick,
        "workflow_run_counts": state.workflow_run_counts,
        "state": state.data,
        "frame": {
            "tick": frame.tick,
            "blocks": [monitor_block_payload(block) for block in frame.blocks],
            "status_lines": frame.status_lines,
            "warnings": frame.warnings,
            "errors": frame.errors,
        },
    }


def format_monitor_frame(frame: MonitorFrame) -> str:
    return "\n".join(row.text for row in _monitor_render_rows(frame))


def dumps_monitor_json(frame: MonitorFrame, state: MonitorState) -> str:
    return json.dumps(monitor_result_payload(frame, state), indent=2, sort_keys=True)


class RichMonitorRenderer:
    def __init__(self) -> None:
        self.console = _monitor_console()
        self.live = _monitor_live(self.console)

    def __enter__(self) -> RichMonitorRenderer:
        self.live.__enter__()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.live.__exit__(exc_type, exc, traceback)

    def render(self, frame: MonitorFrame, state: MonitorState) -> None:
        del state

        self.live.update(
            rich_monitor_frame(
                frame, width=self.console.width, pad_bars=self.console.is_terminal
            )
        )


def _monitor_console() -> Any:
    from rich.console import Console

    force_terminal = True if sys.stdout.isatty() else None
    return Console(force_terminal=force_terminal)


def _monitor_live(console: Any) -> Any:
    from rich.live import Live

    return Live(
        "",
        console=console,
        refresh_per_second=_MONITOR_REFRESH_PER_SECOND,
        screen=True,
        transient=False,
    )


def rich_monitor_frame(
    frame: MonitorFrame, *, width: int, pad_bars: bool = False
) -> Any:
    from rich.text import Text

    rows = _monitor_render_rows(frame)
    bar_width = _monitor_bar_width(rows, fallback_width=width)
    rendered = Text(overflow="fold")
    for index, row in enumerate(rows):
        if index > 0:
            rendered.append("\n")
        if isinstance(row, _MonitorRenderBarRow):
            rendered.append_text(
                _render_monitor_bar_row(row, width=bar_width, pad=pad_bars)
            )
            continue
        rendered.append(row.text)
    return rendered


def _monitor_render_rows(
    frame: MonitorFrame,
) -> list[_MonitorRenderTextRow | _MonitorRenderBarRow]:
    rows: list[_MonitorRenderTextRow | _MonitorRenderBarRow] = [
        _MonitorRenderTextRow("Agent accounts monitor"),
        _MonitorRenderTextRow(f"Tick: {frame.tick}"),
    ]
    rows.extend(_MonitorRenderTextRow(f"Status: {line}") for line in frame.status_lines)
    if frame.errors:
        rows.extend(
            [
                _MonitorRenderTextRow(""),
                _MonitorRenderTextRow("Errors"),
            ]
        )
        rows.extend(_MonitorRenderTextRow(f"  {error}") for error in frame.errors)
    for block in frame.blocks:
        title = block.get("title")
        if isinstance(title, str):
            rows.extend(
                [
                    _MonitorRenderTextRow(""),
                    _MonitorRenderTextRow(title),
                ]
            )
        block_rows = monitor_block_rows(block)
        rows.extend(_monitor_render_block_rows(block_rows))
    return rows


def _monitor_render_block_rows(
    rows: list[MonitorRow],
) -> list[_MonitorRenderTextRow | _MonitorRenderBarRow]:
    return [
        _monitor_render_row(row, context=DEFAULT_MONITOR_RENDER_CONTEXT)
        for row in rows
    ]


def _monitor_render_row(
    row: MonitorRow,
    *,
    context: MonitorRenderContext,
) -> _MonitorRenderTextRow | _MonitorRenderBarRow:
    text = row.render_frame(context)
    if isinstance(row, MonitorUsageTimeRow | MonitorResetRow):
        return _MonitorRenderBarRow(row=row, text=text)
    return _MonitorRenderTextRow(text)


def _monitor_bar_width(
    rows: list[_MonitorRenderTextRow | _MonitorRenderBarRow], *, fallback_width: int
) -> int:
    from rich.cells import cell_len

    width = max(
        (cell_len(row.text) for row in rows if isinstance(row, _MonitorRenderBarRow)),
        default=0,
    )
    if width > 0:
        return width
    return max(1, fallback_width)


def _render_monitor_bar_row(row: _MonitorRenderBarRow, *, width: int, pad: bool) -> Any:
    if isinstance(row.row, MonitorUsageTimeRow):
        marker_percent = (
            row.row.elapsed_percent
            if row.row.elapsed_percent > row.row.used_percent
            else None
        )
        marker_palette = (
            _MONITOR_RESET_BAR_PALETTE if marker_percent is not None else None
        )
        return _inline_percent_text(
            row.text,
            row.row.used_percent,
            width=width,
            pad=pad,
            palette=_MONITOR_USAGE_BAR_PALETTE,
            marker_percent=marker_percent,
            marker_palette=marker_palette,
        )
    return _inline_percent_text(
        row.text,
        row.row.elapsed_percent,
        width=width,
        pad=pad,
        palette=_MONITOR_RESET_BAR_PALETTE,
        marker_percent=row.row.marker_percent,
        marker_palette=_MONITOR_USAGE_BAR_PALETTE
        if row.row.marker_percent is not None
        else None,
    )


def _inline_percent_text(
    label: str,
    percent: int | float,
    *,
    width: int,
    pad: bool,
    palette: tuple[str, ...],
    marker_percent: int | float | None = None,
    marker_palette: tuple[str, ...] | None = None,
) -> Any:
    from rich.cells import cell_len, set_cell_size
    from rich.text import Text

    label_width = cell_len(label)
    bar_width = max(width, label_width) if pad else label_width
    row = set_cell_size(label, bar_width) if pad else label
    text = Text(row, overflow="fold")
    text.stylize(_MONITOR_TRACK_STYLE, 0, len(row))
    _stylize_cell_gradient(
        text,
        row,
        *_percent_cell_range(percent, bar_width),
        width=bar_width,
        palette=palette,
    )
    _stylize_tip_marker(
        text,
        row,
        current_percent=percent,
        marker_percent=marker_percent,
        width=bar_width,
        marker_palette=marker_palette,
    )
    return text


def _percent_cell_range(percent: int | float, width: int) -> tuple[int, int]:
    normalized_percent = min(100.0, max(0.0, float(percent)))
    if normalized_percent <= 0 or width <= 0:
        return (0, 0)
    if normalized_percent >= 100:
        return (0, width)
    return (0, max(1, math.floor(width * normalized_percent / 100.0)))


def _stylize_cell_gradient(
    text: Any,
    row: str,
    start_cell: int,
    end_cell: int,
    *,
    width: int,
    palette: tuple[str, ...],
) -> None:
    for run_start, run_end, style in _cell_gradient_runs(
        start_cell, end_cell, width=width, palette=palette
    ):
        _stylize_cell_range(text, row, run_start, run_end, style)


def _stylize_tip_marker(
    text: Any,
    row: str,
    *,
    current_percent: int | float,
    marker_percent: int | float | None,
    width: int,
    marker_palette: tuple[str, ...] | None,
) -> None:
    marker_cell = _tip_marker_cell(current_percent, marker_percent, width=width)
    if marker_cell is None or marker_palette is None:
        return
    _stylize_cell_range(
        text,
        row,
        marker_cell,
        marker_cell + 1,
        _cell_gradient_style(marker_cell, width=width, palette=marker_palette),
    )


def _cell_gradient_runs(
    start_cell: int,
    end_cell: int,
    *,
    width: int,
    palette: tuple[str, ...],
) -> list[tuple[int, int, str]]:
    if end_cell <= start_cell or width <= 0:
        return []

    runs: list[tuple[int, int, str]] = []
    current_style: str | None = None
    current_start = start_cell
    last_cell = start_cell
    for cell in range(start_cell, end_cell):
        style = _cell_gradient_style(cell, width=width, palette=palette)
        if current_style is None:
            current_style = style
            current_start = cell
        elif style != current_style:
            runs.append((current_start, cell, current_style))
            current_style = style
            current_start = cell
        last_cell = cell + 1

    if current_style is not None:
        runs.append((current_start, last_cell, current_style))
    return runs


def _cell_gradient_style(cell: int, *, width: int, palette: tuple[str, ...]) -> str:
    if width <= 1:
        position = 1.0
    else:
        position = min(1.0, max(0.0, cell / (width - 1)))
    return f"bright_white on {_sample_hex_palette(palette, position)}"


def _stylize_cell_range(
    text: Any, row: str, start_cell: int, end_cell: int, style: str
) -> None:
    if end_cell <= start_cell:
        return
    style_start = _cell_offset_to_text_index(row, start_cell)
    style_end = _cell_offset_to_text_index(row, end_cell)
    if style_end > style_start:
        text.stylize(style, style_start, style_end)


def _tip_marker_cell(
    current_percent: int | float,
    marker_percent: int | float | None,
    *,
    width: int,
) -> int | None:
    if marker_percent is None or width <= 0:
        return None
    current_end = _percent_cell_range(current_percent, width)[1]
    marker_end = _percent_cell_range(marker_percent, width)[1]
    if marker_end <= 0 or marker_end <= current_end:
        return None
    return marker_end - 1


def _sample_hex_palette(palette: tuple[str, ...], position: float) -> str:
    if not palette:
        raise ValueError("palette must contain at least one color")
    if len(palette) == 1:
        return palette[0]

    normalized_position = min(1.0, max(0.0, position))
    scaled_position = normalized_position * (len(palette) - 1)
    left_index = int(math.floor(scaled_position))
    right_index = min(len(palette) - 1, left_index + 1)
    if left_index == right_index:
        return palette[left_index]
    return _interpolate_hex_color(
        palette[left_index],
        palette[right_index],
        scaled_position - left_index,
    )


def _interpolate_hex_color(left_color: str, right_color: str, fraction: float) -> str:
    left_rgb = _hex_to_rgb(left_color)
    right_rgb = _hex_to_rgb(right_color)
    normalized_fraction = min(1.0, max(0.0, fraction))
    channels = tuple(
        round(left_channel + ((right_channel - left_channel) * normalized_fraction))
        for left_channel, right_channel in zip(left_rgb, right_rgb)
    )
    return f"#{channels[0]:02x}{channels[1]:02x}{channels[2]:02x}"


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    if len(color) != 7 or not color.startswith("#"):
        raise ValueError(f"invalid hex color: {color}")
    try:
        return (int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16))
    except ValueError as exc:
        raise ValueError(f"invalid hex color: {color}") from exc
