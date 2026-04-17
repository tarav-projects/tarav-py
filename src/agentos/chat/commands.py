from __future__ import annotations

import argparse
import math
import re
import select
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, TextIO

from agentos._core.errors import CliError
from agentos._core.path_validation import validate_string_for_path
from agentos.chat._cli_common import format_json_output, normalize_updated_since, optional_string_tuple
from agentos.chat.accounts import (
    chat_account_stats,
    format_chat_account_stats_markdown,
    format_chat_account_stats_usage,
    iter_chat_account_stats_refresh_payloads,
    supported_account_provider_families,
)
from agentos.chat.core import (
    find_chat_session,
    list_chat_sessions,
    supported_provider_families,
)
from agentos.chat.extractors.claude_code import extract_dialog_from_claude_code_session
from agentos.chat.extractors.common import DialogTurn
from agentos.chat.extractors.codex import extract_dialog_from_codex_rollout
from agentos.chat.extractors.copilot_cli import (
    extract_dialog_from_copilot_cli_session,
    infer_copilot_cli_session_id_from_path,
    load_copilot_cli_events,
)
from agentos.chat.extractors.gemini_cli import (
    extract_dialog_from_gemini_cli_session,
    load_gemini_cli_session_data,
)
from agentos.chat.extractors.opencode import (
    extract_dialog_from_opencode_session,
    resolve_opencode_db_path,
)
from agentos.chat.extractors.openclaw import (
    extract_dialog_from_openclaw_session,
    infer_openclaw_session_id_from_path,
    load_openclaw_session_records,
)
from agentos.chat.extractors import extract_chat_session
from agentos.chat.sessions import coerce_timestamp


_CHAT_PROVIDER_CHOICES = tuple(provider_family.family for provider_family in supported_provider_families())
_CHAT_ACCOUNTS_PROVIDER_CHOICES = tuple(
    provider_family.family for provider_family in supported_account_provider_families()
)
_CHAT_ACCOUNTS_LOOP_INTERVAL_SEC = 60.0
_CHAT_ACCOUNTS_LOOP_INTERVAL_RESET_SEC = 60.0
_CHAT_ACCOUNTS_LOOP_INTERVAL_INCREMENT_SEC = 1.0
_CHAT_ACCOUNTS_LOOP_INTERVAL_MAX_SEC = 600.0
_CHAT_ACCOUNTS_LOOP_COUNTDOWN_TICK_SEC = 1.0
_CHAT_ACCOUNTS_LOOP_REFRESHING_MESSAGE = "[loop] refreshing..."
_CHAT_ACCOUNTS_INLINE_BAR_GROUP_ID = "chat-accounts-stats"
_CHAT_ACCOUNTS_USAGE_TIME_RE = re.compile(
    r"^\s*usage/time\s*\|\s*(?P<used_percent>\d{1,3})%\s*/\s*(?P<elapsed_percent>\d{1,3})%"
    r"\s*=\s*(?P<ratio>n/a|\d+(?:\.\d+)?)"
)
_CHAT_ACCOUNTS_RESET_PROGRESS_TRACK_STYLE = "bright_white on grey15"
_CHAT_ACCOUNTS_USAGE_TIME_TRACK_STYLE = "bright_white on grey15"
_CHAT_ACCOUNTS_USAGE_BAR_PALETTE = (
    "#14b8a6",
    "#84cc16",
    "#facc15",
    "#f97316",
    "#dc2626",
)
_CHAT_ACCOUNTS_RESET_BAR_PALETTE = (
    "#0f766e",
    "#0891b2",
    "#2563eb",
)
_CHAT_ACCOUNTS_RATIO_SLOW_BAR_PALETTE = (
    "#64748b",
    "#3b82f6",
    "#1d4ed8",
)
_CHAT_ACCOUNTS_RATIO_FAST_BAR_PALETTE = (
    "#64748b",
    "#f59e0b",
    "#dc2626",
)
_CHAT_ACCOUNTS_USAGE_SUFFIX_MARKERS = (
    "🔥🔥",
    "❄️❄️",
    "🔥",
    "❄️",
    "☠️",
    "🕒",
)


@dataclass(frozen=True)
class _InlineBarGroupGeometry:
    prefix_width: int
    main_width: int
    suffix_width: int

    @property
    def center(self) -> int:
        return self.main_width // 2


@dataclass(frozen=True)
class _InlineProgressBar:
    percent: int | float


@dataclass(frozen=True)
class _InlineUsageTimeBar:
    used_percent: int | float
    ratio: float | None = None
    show_ratio_bar: bool = False


@dataclass(frozen=True)
class _InlineTextRow:
    text: str


@dataclass(frozen=True)
class _InlineBarRow:
    group_id: str
    prefix_text: str
    main_text: str
    suffix_text: str
    bar: _InlineProgressBar | _InlineUsageTimeBar


@dataclass(frozen=True)
class _UsageTimeLineData:
    used_percent: int
    elapsed_percent: int
    ratio: float | None


@dataclass
class _ChatAccountsStatsLoopFrame:
    interval_sec: float
    body_text: str = ""
    refresh_progress_text: str | None = None
    next_refresh_at_monotonic: float | None = None
    refreshing: bool = False

    def begin_refresh(self, *, interval_sec: float) -> None:
        self.interval_sec = interval_sec
        self.refreshing = True
        self.next_refresh_at_monotonic = None
        self.refresh_progress_text = None
        if not self.body_text:
            self.body_text = _CHAT_ACCOUNTS_LOOP_REFRESHING_MESSAGE

    def apply_payload(self, *, rendered_body_text: str, refresh_progress_text: str | None) -> None:
        self.body_text = rendered_body_text
        self.refresh_progress_text = refresh_progress_text

    def finish_refresh(self, *, next_refresh_at_monotonic: float) -> None:
        self.refreshing = False
        self.refresh_progress_text = None
        self.next_refresh_at_monotonic = next_refresh_at_monotonic

    def remaining_refresh_sec(self, *, now_monotonic: float) -> float:
        if self.next_refresh_at_monotonic is None:
            return 0.0
        return max(0.0, self.next_refresh_at_monotonic - now_monotonic)

    def render_text(self, *, now_monotonic: float) -> str:
        sections: list[str] = []
        sections.append(self.footer_text(now_monotonic=now_monotonic))
        if self.refresh_progress_text is not None:
            sections.append(self.refresh_progress_text)
        sections.append(self.body_text or _CHAT_ACCOUNTS_LOOP_REFRESHING_MESSAGE)
        return "\n\n".join(sections)

    def footer_text(self, *, now_monotonic: float) -> str:
        if self.refreshing or self.next_refresh_at_monotonic is None:
            return _format_chat_accounts_loop_refreshing_status(self.interval_sec)
        return _format_chat_accounts_loop_status(
            self.interval_sec,
            remaining_sec=self.remaining_refresh_sec(now_monotonic=now_monotonic),
        )


class _ChatAccountsStatsLoopTTYRenderer:
    def __init__(
        self,
        *,
        output_stream: TextIO,
        now_monotonic: Callable[[], float] = time.monotonic,
        live_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.output_stream = output_stream
        self.now_monotonic = now_monotonic
        self._live_factory = live_factory
        self._console: Any | None = None
        self._live: Any | None = None

    def start(self) -> None:
        if self._live is not None:
            return
        from rich.console import Console
        from rich.live import Live
        from rich.text import Text

        if self._console is None:
            self._console = Console(
                file=self.output_stream,
                force_terminal=True,
                color_system="auto",
                no_color=False,
            )
        live_factory = self._live_factory or Live
        self._live = live_factory(
            Text(""),
            console=self._console,
            screen=True,
            auto_refresh=False,
            transient=False,
            redirect_stdout=False,
            redirect_stderr=False,
            vertical_overflow="ellipsis",
        )
        self._live.start(refresh=True)

    def stop(self) -> None:
        if self._live is None:
            return
        live = self._live
        self._live = None
        live.stop()

    def paint(self, frame: _ChatAccountsStatsLoopFrame) -> None:
        if self._live is None:
            self.start()

        assert self._live is not None
        assert self._console is not None
        self._live.update(
            _render_chat_accounts_stats_loop_rich_text(
                frame,
                now_monotonic=self.now_monotonic(),
                width=self._console.width,
            ),
            refresh=True,
        )


def _render_chat_accounts_stats_loop_rich_text(
    frame: _ChatAccountsStatsLoopFrame,
    *,
    now_monotonic: float,
    width: int,
) -> Any:
    from rich.text import Text

    rendered_text = frame.render_text(now_monotonic=now_monotonic)
    lines = rendered_text.splitlines()
    rows = _inline_bar_rows(lines)
    group_geometries = _inline_bar_group_geometries(rows, fallback_width=width)
    rendered = Text(overflow="fold")
    for line_index, row in enumerate(rows):
        if line_index > 0:
            rendered.append("\n")

        if isinstance(row, _InlineTextRow):
            rendered.append(row.text)
            continue
        rendered.append_text(_render_inline_bar_row(row, group_geometries[row.group_id]))
    return rendered


def _inline_bar_rows(lines: list[str]) -> list[_InlineTextRow | _InlineBarRow]:
    rows: list[_InlineTextRow | _InlineBarRow] = []
    current_group_id: str | None = None
    current_elapsed_percent: int | None = None
    next_usage_time_is_aggregate = False

    for line in lines:
        if line == "Selected accounts aggregate:":
            next_usage_time_is_aggregate = True
            rows.append(_InlineTextRow(line))
            continue

        usage_time_data = _usage_time_line_data(line)
        if usage_time_data is not None:
            main_text, suffix_text = _split_usage_time_main_suffix(line)
            rows.append(
                _InlineBarRow(
                    group_id=_CHAT_ACCOUNTS_INLINE_BAR_GROUP_ID,
                    prefix_text="",
                    main_text=main_text,
                    suffix_text=suffix_text,
                    bar=_InlineUsageTimeBar(
                        used_percent=usage_time_data.used_percent,
                        ratio=usage_time_data.ratio,
                        show_ratio_bar=next_usage_time_is_aggregate,
                    ),
                )
            )
            next_usage_time_is_aggregate = False
            current_group_id = _CHAT_ACCOUNTS_INLINE_BAR_GROUP_ID
            current_elapsed_percent = usage_time_data.elapsed_percent
            continue

        if _is_reset_line(line) and current_group_id is not None and current_elapsed_percent is not None:
            rows.append(
                _InlineBarRow(
                    group_id=current_group_id,
                    prefix_text="",
                    main_text=line,
                    suffix_text="",
                    bar=_InlineProgressBar(current_elapsed_percent),
                )
            )
            current_group_id = None
            current_elapsed_percent = None
            continue

        if not line.strip():
            current_group_id = None
            current_elapsed_percent = None
            next_usage_time_is_aggregate = False
        rows.append(_InlineTextRow(line))

    return rows


def _inline_bar_group_geometries(
    rows: list[_InlineTextRow | _InlineBarRow],
    *,
    fallback_width: int,
) -> dict[str, _InlineBarGroupGeometry]:
    from rich.cells import cell_len

    grouped_rows: dict[str, list[_InlineBarRow]] = {}
    for row in rows:
        if isinstance(row, _InlineBarRow):
            grouped_rows.setdefault(row.group_id, []).append(row)

    geometries: dict[str, _InlineBarGroupGeometry] = {}
    for group_id, group_rows in grouped_rows.items():
        geometries[group_id] = _InlineBarGroupGeometry(
            prefix_width=max((cell_len(row.prefix_text) for row in group_rows), default=0),
            main_width=max((cell_len(row.main_text) for row in group_rows), default=max(1, int(fallback_width))),
            suffix_width=max((cell_len(row.suffix_text) for row in group_rows), default=0),
        )
    return geometries


def _render_inline_bar_row(row: _InlineBarRow, geometry: _InlineBarGroupGeometry) -> Any:
    from rich.cells import set_cell_size

    if isinstance(row.bar, _InlineProgressBar):
        rendered = _inline_progress_text(row.main_text, row.bar.percent, geometry)
    else:
        rendered = _inline_usage_time_text(
            row.main_text,
            used_percent=row.bar.used_percent,
            ratio=row.bar.ratio,
            show_ratio_bar=row.bar.show_ratio_bar,
            geometry=geometry,
        )

    if geometry.suffix_width > 0:
        rendered.append(set_cell_size(row.suffix_text, geometry.suffix_width))
    if geometry.prefix_width > 0:
        prefixed = _unstyled_text(set_cell_size(row.prefix_text, geometry.prefix_width))
        prefixed.append_text(rendered)
        return prefixed
    return rendered


def _inline_progress_text(label: str, percent: int | float, geometry: _InlineBarGroupGeometry) -> Any:
    from rich.text import Text

    normalized_percent = min(100.0, max(0.0, float(percent)))
    row = _inline_bar_row(label, geometry)
    if normalized_percent <= 0:
        fill_cells = 0
    elif normalized_percent >= 100:
        fill_cells = geometry.main_width
    else:
        fill_cells = max(1, math.floor(geometry.main_width * normalized_percent / 100.0))
    text = Text(row, overflow="fold")
    text.stylize(_CHAT_ACCOUNTS_RESET_PROGRESS_TRACK_STYLE, 0, len(row))
    _stylize_cell_gradient(
        text,
        row,
        0,
        fill_cells,
        width=geometry.main_width,
        palette=_CHAT_ACCOUNTS_RESET_BAR_PALETTE,
    )
    return text


def _inline_usage_time_text(
    label: str,
    *,
    used_percent: int | float,
    geometry: _InlineBarGroupGeometry,
    ratio: float | None = None,
    show_ratio_bar: bool = False,
) -> Any:
    from rich.text import Text

    row = _inline_bar_row(label, geometry)
    text = Text(row, overflow="fold")
    text.stylize(_CHAT_ACCOUNTS_USAGE_TIME_TRACK_STYLE, 0, len(row))

    if show_ratio_bar:
        ratio_range = _ratio_cell_range(ratio, geometry)
        if ratio_range is not None:
            ratio_start, ratio_end, ratio_palette = ratio_range
            _stylize_cell_gradient(
                text,
                row,
                ratio_start,
                ratio_end,
                width=geometry.main_width,
                palette=ratio_palette,
            )
    else:
        usage_range = _percent_cell_range(used_percent, geometry.main_width)
        _stylize_cell_gradient(
            text,
            row,
            *usage_range,
            width=geometry.main_width,
            palette=_CHAT_ACCOUNTS_USAGE_BAR_PALETTE,
        )
    return text


def _percent_cell_range(percent: int | float, width: int) -> tuple[int, int]:
    normalized_percent = min(100.0, max(0.0, float(percent)))
    if normalized_percent <= 0:
        return (0, 0)
    if normalized_percent >= 100:
        return (0, width)
    return (0, max(1, math.floor(width * normalized_percent / 100.0)))


def _ratio_cell_range(
    ratio: float | None,
    geometry: _InlineBarGroupGeometry,
) -> tuple[int, int, tuple[str, ...]] | None:
    if ratio is None:
        return None

    normalized_ratio = min(2.0, max(0.0, ratio))
    if math.isclose(normalized_ratio, 1.0):
        return None

    center = geometry.center
    if normalized_ratio > 1.0:
        right_width = geometry.main_width - center
        fill_width = _inline_centered_ratio_fill_width(right_width, normalized_ratio - 1.0)
        return (center, center + fill_width, _CHAT_ACCOUNTS_RATIO_FAST_BAR_PALETTE)

    left_width = center
    fill_width = _inline_centered_ratio_fill_width(left_width, 1.0 - normalized_ratio)
    return (center - fill_width, center, _CHAT_ACCOUNTS_RATIO_SLOW_BAR_PALETTE)


def _inline_bar_row(label: str, geometry: _InlineBarGroupGeometry) -> str:
    from rich.cells import cell_len, set_cell_size

    return set_cell_size(label, max(geometry.main_width, cell_len(label)))


def _unstyled_text(value: str) -> Any:
    from rich.text import Text

    return Text(value, overflow="fold")


def _cell_offset_to_text_index(text: str, cell_offset: int) -> int:
    from rich.cells import split_graphemes

    if cell_offset <= 0:
        return 0
    cell_position = 0
    graphemes, _ = split_graphemes(text)
    for start, end, cell_size in graphemes:
        next_cell_position = cell_position + cell_size
        if next_cell_position == cell_offset:
            return end
        if next_cell_position > cell_offset:
            return start
        cell_position = next_cell_position
    return len(text)


def _stylize_cell_range(text: Any, row: str, start_cell: int, end_cell: int, style: str) -> None:
    if end_cell <= start_cell:
        return
    style_start = _cell_offset_to_text_index(row, start_cell)
    style_end = _cell_offset_to_text_index(row, end_cell)
    if style_end > style_start:
        text.stylize(style, style_start, style_end)


def _stylize_cell_gradient(
    text: Any,
    row: str,
    start_cell: int,
    end_cell: int,
    *,
    width: int,
    palette: tuple[str, ...],
) -> None:
    for run_start, run_end, style in _cell_gradient_runs(start_cell, end_cell, width=width, palette=palette):
        _stylize_cell_range(text, row, run_start, run_end, style)


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
        position = _clamp(cell / (width - 1), 0.0, 1.0)
    return _background_palette_style(palette, position)


def _background_palette_style(palette: tuple[str, ...], position: float) -> str:
    return f"bright_white on {_sample_hex_palette(palette, position)}"


def _sample_hex_palette(palette: tuple[str, ...], position: float) -> str:
    if not palette:
        raise ValueError("palette must contain at least one color")
    if len(palette) == 1:
        return palette[0]

    normalized_position = _clamp(position, 0.0, 1.0)
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
    normalized_fraction = _clamp(fraction, 0.0, 1.0)
    channels = tuple(
        round(left_channel + ((right_channel - left_channel) * normalized_fraction))
        for left_channel, right_channel in zip(left_rgb, right_rgb)
    )
    return f"#{channels[0]:02x}{channels[1]:02x}{channels[2]:02x}"


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        raise ValueError(f"invalid hex color: {color}")
    return (int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16))


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return min(maximum, max(minimum, value))


def _inline_centered_ratio_fill_width(half_width: int, fraction: float) -> int:
    if half_width <= 0:
        return 0
    if fraction <= 0:
        return 0
    if fraction >= 1:
        return half_width
    return max(1, math.floor(half_width * fraction))


def _usage_time_line_data(line: str) -> _UsageTimeLineData | None:
    match = _CHAT_ACCOUNTS_USAGE_TIME_RE.match(line)
    if match is None:
        return None
    raw_ratio = match.group("ratio")
    ratio = None if raw_ratio == "n/a" else float(raw_ratio)
    return _UsageTimeLineData(
        used_percent=min(100, int(match.group("used_percent"))),
        elapsed_percent=min(100, int(match.group("elapsed_percent"))),
        ratio=ratio,
    )


def _split_usage_time_main_suffix(line: str) -> tuple[str, str]:
    main_text = line.rstrip()
    suffix_markers: list[str] = []
    while True:
        matched_marker = None
        for marker in _CHAT_ACCOUNTS_USAGE_SUFFIX_MARKERS:
            if main_text.endswith(marker):
                marker_start = len(main_text) - len(marker)
                if marker_start == 0 or main_text[marker_start - 1].isspace():
                    matched_marker = marker
                    break
        if matched_marker is None:
            break
        suffix_markers.append(matched_marker)
        main_text = main_text[: -len(matched_marker)].rstrip()

    if not suffix_markers:
        return line, ""
    return main_text, " " + " ".join(reversed(suffix_markers))


def _is_reset_line(line: str) -> bool:
    return line.strip().startswith("resets |")


def _normalize_session_limit(limit: int | None) -> int | None:
    if limit is None:
        return None
    if limit < 1:
        raise CliError("session limit must be greater than 0")
    return limit


def _normalize_session_query(query: str) -> str:
    normalized = query.strip()
    if normalized.startswith("agentos://chat-session/"):
        if not normalized[len("agentos://chat-session/"):]:
            raise CliError("session query must not be empty")
        return normalized
    return validate_string_for_path(normalized, field_name="session query")


def _cmd_chat_debug_list(args: argparse.Namespace) -> int:
    user_contain = args.user_contain
    limit = _normalize_session_limit(args.limit)
    payload = list_chat_sessions(
        sort=args.sort,
        full_output=args.full_output,
        limit=None if user_contain is not None else limit,
        providers=optional_string_tuple(args.providers),
        extractable_only=args.extractable,
        updated_after=normalize_updated_since(args.updated_since),
    )
    payload["command"] = "chat debug list"
    if user_contain is not None:
        payload = _filter_payload_by_user_contain(payload, query=user_contain, limit=limit)
        payload["command"] = "chat debug list"
    if args.output_format == "card":
        print(_format_chat_session_list_card(payload, now=time.time()))
        return 0
    print(format_json_output(payload))
    return 0


def _cmd_chat_debug_find(args: argparse.Namespace) -> int:
    query = _normalize_session_query(args.query)
    payload = find_chat_session(
        query,
        include_artifacts=args.artifacts,
        include_grep=args.grep,
        full_output=args.full_output,
    )
    payload["command"] = "chat debug find"
    print(format_json_output(payload))
    return 0


def _normalize_optional_session_query(
    session_query: str | None,
    *,
    file_path: str | None,
) -> str | None:
    if session_query is None:
        if file_path is not None:
            return None
        raise CliError("session query is required unless --file is provided")

    return _normalize_session_query(session_query)


def _cmd_chat_debug_extract(args: argparse.Namespace) -> int:
    session_query = _normalize_optional_session_query(args.session_query, file_path=args.file_path)
    output = extract_chat_session(
        session_query=session_query,
        file_path=args.file_path,
        output_format=args.output_format,
        raw=args.raw,
    )
    print(output)
    return 0


def _cmd_chat_accounts_stats(args: argparse.Namespace) -> int:
    if args.loop:
        return _loop_chat_accounts_stats(args)

    print(_render_chat_accounts_stats_output(args))
    return 0


def _render_chat_accounts_stats_output(args: argparse.Namespace) -> str:
    payload = chat_account_stats(
        instance_ids=optional_string_tuple(args.instance_ids),
        providers=optional_string_tuple(args.providers),
        refresh_usage=args.refresh_usage,
        full_output=args.full_output,
    )
    return _format_chat_accounts_stats_payload_output(args, payload)


def _format_chat_accounts_stats_payload_output(
    args: argparse.Namespace,
    payload: dict[str, object],
) -> str:
    if args.output_format == "markdown":
        return format_chat_account_stats_markdown(payload)
    if args.output_format == "usage":
        return format_chat_account_stats_usage(payload)
    return format_json_output(payload)


def _loop_chat_accounts_stats(
    args: argparse.Namespace,
    *,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
    interval_sec: float = _CHAT_ACCOUNTS_LOOP_INTERVAL_SEC,
    wait_for_trigger: Callable[[float, TextIO], bool] | None = None,
) -> int:
    input_stream = input_stream or sys.stdin
    output_stream = output_stream or sys.stdout
    wait_for_trigger = wait_for_trigger or _wait_for_chat_accounts_loop_trigger
    tty_output = _stream_is_tty(output_stream)
    current_interval_sec = interval_sec
    tty_frame = _ChatAccountsStatsLoopFrame(interval_sec=current_interval_sec) if tty_output else None
    tty_renderer = (
        _ChatAccountsStatsLoopTTYRenderer(output_stream=output_stream) if tty_output else None
    )

    first_iteration = True
    if tty_renderer is not None:
        tty_renderer.start()
    try:
        while True:
            if tty_output:
                _render_chat_accounts_stats_progressive_tty(
                    args,
                    frame=tty_frame,
                    renderer=tty_renderer,
                    interval_sec=current_interval_sec,
                )
                assert tty_frame is not None
                assert tty_renderer is not None
                tty_frame.finish_refresh(next_refresh_at_monotonic=time.monotonic() + current_interval_sec)
                tty_renderer.paint(tty_frame)
            else:
                rendered_output = _render_chat_accounts_stats_output(args)
                if not first_iteration:
                    output_stream.write("\n")
                output_stream.write(rendered_output)
                output_stream.write(
                    f"\n\n[loop] refreshes every {int(current_interval_sec)}s; press Enter to refresh now; Ctrl-C to stop\n"
                )
                output_stream.flush()
            first_iteration = False

            if tty_output and wait_for_trigger is _wait_for_chat_accounts_loop_trigger:
                triggered_by_user = _wait_for_chat_accounts_loop_trigger_with_tty_countdown(
                    tty_frame,
                    tty_renderer,
                    input_stream,
                )
            else:
                triggered_by_user = wait_for_trigger(current_interval_sec, input_stream)

            if triggered_by_user:
                current_interval_sec = _CHAT_ACCOUNTS_LOOP_INTERVAL_RESET_SEC
            else:
                current_interval_sec = min(
                    _CHAT_ACCOUNTS_LOOP_INTERVAL_MAX_SEC,
                    current_interval_sec + _CHAT_ACCOUNTS_LOOP_INTERVAL_INCREMENT_SEC,
                )

            if not tty_output:
                output_stream.write(_CHAT_ACCOUNTS_LOOP_REFRESHING_MESSAGE + "\n")
                output_stream.flush()
    except KeyboardInterrupt:
        return 0
    finally:
        if tty_renderer is not None:
            tty_renderer.stop()


def _render_chat_accounts_stats_progressive_tty(
    args: argparse.Namespace,
    *,
    frame: _ChatAccountsStatsLoopFrame | None,
    renderer: _ChatAccountsStatsLoopTTYRenderer | None,
    interval_sec: float,
) -> None:
    if frame is None or renderer is None:
        raise CliError("TTY frame rendering requires both a frame and renderer")

    frame.begin_refresh(interval_sec=interval_sec)
    renderer.paint(frame)
    for payload in iter_chat_account_stats_refresh_payloads(
        instance_ids=optional_string_tuple(args.instance_ids),
        providers=optional_string_tuple(args.providers),
        refresh_usage=args.refresh_usage,
        full_output=args.full_output,
    ):
        frame.apply_payload(
            rendered_body_text=_format_chat_accounts_stats_payload_output(args, payload),
            refresh_progress_text=_format_chat_accounts_refresh_progress(payload),
        )
        renderer.paint(frame)


def _format_chat_accounts_refresh_progress(payload: dict[str, object]) -> str | None:
    raw_pending_count = payload.get("pending_count")
    raw_completed_count = payload.get("completed_count")
    raw_account_count = payload.get("account_count")
    if not isinstance(raw_pending_count, int) or not isinstance(raw_completed_count, int):
        return None
    if not isinstance(raw_account_count, int) or raw_pending_count < 0 or raw_completed_count < 0:
        return None
    return f"[refresh] {raw_completed_count}/{raw_account_count} complete; {raw_pending_count} pending"


def _wait_for_chat_accounts_loop_trigger(interval_sec: float, input_stream: TextIO) -> bool:
    if interval_sec <= 0:
        return False

    if not _stream_is_tty(input_stream):
        time.sleep(interval_sec)
        return False

    ready, _, _ = select.select([input_stream], [], [], interval_sec)
    if not ready:
        return False

    input_stream.readline()
    return True


def _wait_for_chat_accounts_loop_trigger_with_tty_countdown(
    frame: _ChatAccountsStatsLoopFrame | None,
    renderer: _ChatAccountsStatsLoopTTYRenderer | None,
    input_stream: TextIO,
    *,
    tick_sec: float = _CHAT_ACCOUNTS_LOOP_COUNTDOWN_TICK_SEC,
) -> bool:
    if frame is None or renderer is None:
        raise CliError("TTY countdown requires both a frame and renderer")
    if frame.next_refresh_at_monotonic is None:
        return False

    tty_input = _stream_is_tty(input_stream)
    while True:
        remaining_sec = frame.remaining_refresh_sec(now_monotonic=time.monotonic())
        if remaining_sec <= 0:
            renderer.paint(frame)
            return False

        wait_timeout = min(tick_sec, remaining_sec)
        if tty_input:
            ready, _, _ = select.select([input_stream], [], [], wait_timeout)
            if ready:
                input_stream.readline()
                return True
        else:
            time.sleep(wait_timeout)
        renderer.paint(frame)
        if remaining_sec <= tick_sec:
            return False


def _stream_is_tty(stream: TextIO) -> bool:
    isatty = getattr(stream, "isatty", None)
    if isatty is None:
        return False
    try:
        return bool(isatty())
    except OSError:
        return False


def _format_chat_accounts_loop_status(interval_sec: float, *, remaining_sec: float | None = None) -> str:
    interval_text = f"{int(interval_sec)}s"
    if remaining_sec is None:
        return f"[loop] refreshes every {interval_text}; press Enter to refresh now; Ctrl-C to stop"
    remaining_text = _format_chat_accounts_loop_countdown(remaining_sec)
    return (
        f"[loop] refreshes every {interval_text}; next refresh in {remaining_text}; "
        "press Enter to refresh now; Ctrl-C to stop"
    )


def _format_chat_accounts_loop_refreshing_status(interval_sec: float) -> str:
    interval_text = f"{int(interval_sec)}s"
    return f"[loop] refreshing... next interval {interval_text}; Ctrl-C to stop"


def _format_chat_accounts_loop_countdown(remaining_sec: float) -> str:
    total_seconds = max(0, math.ceil(remaining_sec))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def _filter_payload_by_user_contain(
    payload: dict[str, object],
    *,
    query: str,
    limit: int | None = None,
) -> dict[str, object]:
    raw_sessions = payload.get("sessions")
    if not isinstance(raw_sessions, list):
        return payload

    query_lower = query.lower()
    filtered: list[dict[str, object]] = []
    for session in raw_sessions:
        if not isinstance(session, dict):
            continue
        if _session_user_messages_contain(session, query_lower):
            filtered.append(session)
            if limit is not None and len(filtered) >= limit:
                break

    selection = payload.get("selection")
    normalized_selection = dict(selection) if isinstance(selection, dict) else {}
    filters = normalized_selection.get("filters")
    normalized_filters = dict(filters) if isinstance(filters, dict) else {}
    normalized_filters["user_contain"] = query
    normalized_filters["limit"] = limit
    normalized_selection["filters"] = normalized_filters

    return {
        **payload,
        "selection": normalized_selection,
        "sessions": filtered,
        "session_count": len(filtered),
    }


def _session_user_messages_contain(session: dict[str, object], query_lower: str) -> bool:
    turns = _load_session_user_turns(session)
    for turn in turns:
        if query_lower in turn.text.lower():
            return True
    return False


def _load_session_user_turns(session: dict[str, object]) -> list[DialogTurn]:
    path = _primary_artifact_path(session)
    if path is None or not path.is_file():
        return []

    provider = _string_or_none(session.get("provider"))
    session_id = _string_or_none(session.get("session_id")) or ""
    turns = _safe_load_session_turns(provider=provider, path=path, session_id=session_id)
    if turns is None:
        return []

    return [turn for turn in turns if turn.role == "user"]


def _load_session_turns(
    *,
    provider: str | None,
    path: Path,
    session_id: str,
    gemini_session_data: dict[str, object] | None = None,
) -> list[DialogTurn]:
    if provider == "claude-code":
        if path.suffix == ".jsonl":
            return extract_dialog_from_claude_code_session(path, raw=False)
        return []

    if provider == "codex":
        return extract_dialog_from_codex_rollout(path, raw=False)

    if provider == "copilot-cli":
        events = load_copilot_cli_events(path)
        return extract_dialog_from_copilot_cli_session(
            events=events,
            session_id=infer_copilot_cli_session_id_from_path(path) or session_id,
            raw=False,
        )

    if provider == "gemini-cli":
        session_data = gemini_session_data
        if session_data is None:
            session_data = load_gemini_cli_session_data(path)
        return extract_dialog_from_gemini_cli_session(
            session_data=session_data,
            session_id=str(session_data.get("sessionId") or session_id),
            raw=False,
        )

    if provider == "openclaw":
        records = load_openclaw_session_records(path)
        return extract_dialog_from_openclaw_session(
            records=records,
            session_id=infer_openclaw_session_id_from_path(path) or session_id,
            raw=False,
        )

    if provider == "opencode":
        db_path = resolve_opencode_db_path(path)
        return extract_dialog_from_opencode_session(
            db_path=db_path,
            session_id=session_id,
            raw=False,
        )

    return []


def _safe_load_session_turns(
    *,
    provider: str | None,
    path: Path,
    session_id: str,
    gemini_session_data: dict[str, object] | None = None,
) -> list[DialogTurn] | None:
    try:
        return _load_session_turns(
            provider=provider,
            path=path,
            session_id=session_id,
            gemini_session_data=gemini_session_data,
        )
    except (CliError, OSError, json.JSONDecodeError):
        return None


def _load_turn_summary_for_card_session_context(
    *,
    provider: str | None,
    path: Path,
    session_id: str,
    gemini_session_data: dict[str, object] | None = None,
) -> tuple[float | None, str | None] | None:
    turns = _safe_load_session_turns(
        provider=provider,
        path=path,
        session_id=session_id,
        gemini_session_data=gemini_session_data,
    )
    if not turns:
        return None
    return _created_and_preview_from_turns(turns)


def _format_chat_session_list_card(payload: dict[str, object], *, now: float) -> str:
    raw_sessions = payload.get("sessions")
    sessions = raw_sessions if isinstance(raw_sessions, list) else []
    separator = "────────────────────────────────────────"
    cards: list[str] = []

    for raw_session in sessions:
        if not isinstance(raw_session, dict):
            continue
        created_at, preview = _summarize_session_for_card_output(raw_session)
        updated_at = coerce_timestamp(raw_session.get("updated_at"))
        provider = _string_or_none(raw_session.get("provider")) or "-"
        session_id = _string_or_none(raw_session.get("session_id")) or "-"
        card_lines = [
            separator,
            provider,
            session_id,
            "",
            f"created {_format_relative_age(created_at, now=now)}",
            f"updated {_format_relative_age(updated_at, now=now)}",
            "",
            preview,
        ]
        cards.append("\n".join(card_lines))

    if not cards:
        return "(no sessions)"
    return "\n\n".join(cards)


def _summarize_session_for_card_output(session: dict[str, object]) -> tuple[float | None, str]:
    path = _primary_artifact_path(session)
    display_name = _string_or_none(session.get("display_name"))
    session_id = _string_or_none(session.get("session_id")) or "-"

    preview: str | None = None
    created_at = coerce_timestamp(session.get("created_at"))
    if path is not None:
        loaded_created_at, preview = _load_card_session_context(
            provider=_string_or_none(session.get("provider")),
            path=path,
            session_id=session_id,
        )
        created_at = loaded_created_at or created_at

    if preview is None:
        preview = display_name or session_id
    return created_at, _truncate_preview(preview)


def _load_card_session_context(
    *,
    provider: str | None,
    path: Path,
    session_id: str,
) -> tuple[float | None, str | None]:
    try:
        if provider == "claude-code":
            if path.suffix == ".jsonl":
                loaded = _load_turn_summary_for_card_session_context(
                    provider=provider,
                    path=path,
                    session_id=session_id,
                )
                if loaded is not None:
                    return loaded
            if path.suffix == ".json":
                obj = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
                if isinstance(obj, dict):
                    created_at = coerce_timestamp(obj.get("createdAt")) or coerce_timestamp(obj.get("lastActivityAt"))
                    preview = _string_or_none(obj.get("title"))
                    return created_at, preview

        if provider == "gemini-cli":
            session_data = load_gemini_cli_session_data(path)
            loaded = _load_turn_summary_for_card_session_context(
                provider=provider,
                path=path,
                session_id=session_id,
                gemini_session_data=session_data,
            )
            if loaded is not None:
                created_at, preview = loaded
                return created_at or coerce_timestamp(session_data.get("startTime")), preview

        loaded = _load_turn_summary_for_card_session_context(
            provider=provider,
            path=path,
            session_id=session_id,
        )
        if loaded is not None:
            return loaded
    except (CliError, OSError, json.JSONDecodeError):
        return None, None

    return None, None


def _created_and_preview_from_turns(turns: list[object]) -> tuple[float | None, str | None]:
    created_at: float | None = None
    preview: str | None = None

    for turn in turns:
        timestamp = coerce_timestamp(getattr(turn, "timestamp", None))
        if timestamp is not None and created_at is None:
            created_at = timestamp

        role = getattr(turn, "role", None)
        text = _string_or_none(getattr(turn, "text", None))
        if not text:
            continue
        if preview is None:
            preview = text
        if role == "user":
            preview = text
            break

    return created_at, preview


def _primary_artifact_path(session: dict[str, object]) -> Path | None:
    raw_artifact = session.get("primary_backing_artifact")
    if not isinstance(raw_artifact, dict):
        return None
    path_text = _string_or_none(raw_artifact.get("path"))
    if path_text is None:
        return None
    return Path(path_text)


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped:
            return stripped
    return None


def _truncate_preview(text: str, *, max_length: int = 120) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= max_length:
        return normalized
    return normalized[: max_length - 3].rstrip() + "..."


def _format_relative_age(timestamp: float | None, *, now: float) -> str:
    if timestamp is None:
        return "-"

    delta_seconds = max(0, int(now - timestamp))
    if delta_seconds < 60:
        return "just now"

    units = (
        ("year", 365 * 24 * 60 * 60),
        ("month", 30 * 24 * 60 * 60),
        ("week", 7 * 24 * 60 * 60),
        ("day", 24 * 60 * 60),
        ("hour", 60 * 60),
        ("minute", 60),
    )
    for unit_name, unit_seconds in units:
        if delta_seconds >= unit_seconds:
            value = delta_seconds // unit_seconds
            suffix = "" if value == 1 else "s"
            return f"{value} {unit_name}{suffix} ago"
    return "just now"


def register_chat_commands(subparsers: argparse._SubParsersAction) -> None:
    chat_parser = subparsers.add_parser(
        "chat",
        help="Provider-aware chat workflow utilities.",
    )
    chat_subparsers = chat_parser.add_subparsers(dest="chat_command", required=True)

    debug_parser = chat_subparsers.add_parser(
        "debug",
        help="Live provider-side debug utilities that bypass Chatlas dataset queries.",
    )
    debug_subparsers = debug_parser.add_subparsers(
        dest="chat_debug_command",
        required=True,
    )

    list_parser = debug_subparsers.add_parser(
        "list",
        help="List live provider sessions directly from configured homes.",
    )
    list_parser.add_argument(
        "--sort",
        choices=("lexical", "newest", "oldest"),
        default="lexical",
        help="Sort order for returned sessions across all providers (default: lexical).",
    )
    list_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of sessions to return overall.",
    )
    list_parser.add_argument(
        "--provider",
        choices=_CHAT_PROVIDER_CHOICES,
        action="append",
        dest="providers",
        help="Restrict listing to a provider. Repeat to include multiple providers.",
    )
    list_parser.add_argument(
        "--full-output",
        action="store_true",
        help="Include provider diagnostics even for providers with no matching sessions.",
    )
    list_parser.add_argument(
        "--extractable",
        action="store_true",
        help="Keep only sessions with an extractable primary artifact.",
    )
    list_parser.add_argument(
        "--updated-since",
        default=None,
        help="Keep only sessions updated within the given lookback, e.g. 72h or 3d.",
    )
    list_parser.add_argument(
        "--user-contain",
        default=None,
        dest="user_contain",
        help="Keep only sessions where at least one user message contains the given text (case-insensitive).",
    )
    list_parser.add_argument(
        "--output",
        choices=("card", "json"),
        default="card",
        dest="output_format",
        help="Output format (default: card).",
    )
    list_parser.set_defaults(handler=_cmd_chat_debug_list)

    find_parser = debug_subparsers.add_parser(
        "find",
        help="Search live provider homes using a provider-agnostic session query.",
    )
    find_parser.add_argument(
        "query",
        help="Session query string. Each provider tries all matching strategies it supports.",
    )
    find_parser.add_argument(
        "--artifacts",
        action="store_true",
        help="Expand matched sessions with their canonical backing artifacts.",
    )
    find_parser.add_argument(
        "--grep",
        action="store_true",
        help="Include grep-based search evidence as separate search_findings output.",
    )
    find_parser.add_argument(
        "--full-output",
        action="store_true",
        help="Include provider diagnostics even for providers with no matched sessions.",
    )
    find_parser.set_defaults(handler=_cmd_chat_debug_find)

    extract_parser = debug_subparsers.add_parser(
        "extract",
        help="Extract dialog directly from live provider resolution or a raw artifact path.",
    )
    extract_parser.add_argument(
        "session_query",
        nargs="?",
        help="Session query string. Each provider tries all matching strategies it supports.",
    )
    extract_parser.add_argument(
        "--format",
        choices=("jsonl", "markdown"),
        default="jsonl",
        dest="output_format",
        help="Output format (default: jsonl).",
    )
    extract_parser.add_argument(
        "--file",
        default=None,
        dest="file_path",
        help="Session artifact path directly; extractor is inferred from file provenance.",
    )
    extract_parser.add_argument(
        "--raw",
        action="store_true",
        help="Skip all filtering; emit every content block verbatim.",
    )
    extract_parser.set_defaults(handler=_cmd_chat_debug_extract)

    accounts_parser = chat_subparsers.add_parser(
        "accounts",
        help="Query configured account status across supported providers.",
    )
    accounts_subparsers = accounts_parser.add_subparsers(
        dest="chat_accounts_command",
        required=True,
    )

    accounts_stats_parser = accounts_subparsers.add_parser(
        "stats",
        help="Aggregate configured account status and usage checks across supported providers.",
    )
    accounts_stats_parser.add_argument(
        "instance_ids",
        nargs="*",
        help="Optional configured account instance ids to query. Defaults to all configured instances.",
    )
    accounts_stats_parser.add_argument(
        "--provider",
        choices=_CHAT_ACCOUNTS_PROVIDER_CHOICES,
        action="append",
        dest="providers",
        help="Restrict checks to a provider. Repeat to include multiple providers.",
    )
    accounts_stats_parser.add_argument(
        "--output",
        choices=("json", "markdown", "usage"),
        default="json",
        dest="output_format",
        help="Output format (default: json).",
    )
    accounts_stats_parser.add_argument(
        "--full-output",
        action="store_true",
        help="Keep zero-account provider diagnostics in the providers array.",
    )
    accounts_stats_parser.add_argument(
        "--refresh-usage",
        action="store_true",
        help=(
            "Allow provider adapters to issue live refresh requests for usage data when needed "
            "(for example Claude Code)."
        ),
    )
    accounts_stats_parser.add_argument(
        "--loop",
        action="store_true",
        help="Refresh forever every 60 seconds; press Enter to refresh immediately.",
    )
    accounts_stats_parser.set_defaults(handler=_cmd_chat_accounts_stats)
