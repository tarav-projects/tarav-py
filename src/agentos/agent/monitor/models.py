from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


AUTO_PRIME_ZERO_LIMITS_WORKFLOW = "auto-prime-zero-limits"
LIMITS_TRACKING_WORKFLOW = "limits-tracking"
AUTO_PRIME_TRIGGER_ZERO_USAGE = "zero_usage"
AUTO_PRIME_TRIGGER_NEAR_ZERO_FULL_WINDOW = "near_zero_full_window"
AUTO_PRIME_TRIGGER_SLIDING_RESET = "sliding_reset"
AUTO_PRIME_TRIGGER_PERIOD_KEY_CHURN = "period_key_churn"
AUTO_PRIME_SUPPORTED_TRIGGERS = (
    AUTO_PRIME_TRIGGER_ZERO_USAGE,
    AUTO_PRIME_TRIGGER_NEAR_ZERO_FULL_WINDOW,
    AUTO_PRIME_TRIGGER_SLIDING_RESET,
    AUTO_PRIME_TRIGGER_PERIOD_KEY_CHURN,
)
AUTO_PRIME_UNINITIALIZED_TRIGGERS = frozenset(
    (
        AUTO_PRIME_TRIGGER_NEAR_ZERO_FULL_WINDOW,
        AUTO_PRIME_TRIGGER_SLIDING_RESET,
        AUTO_PRIME_TRIGGER_PERIOD_KEY_CHURN,
    )
)
AUTO_PRIME_PING_SUCCEEDED_STATUS = "ping_succeeded"
AUTO_PRIME_VERIFICATION_PENDING = "pending_verification"
AUTO_PRIME_VERIFICATION_EFFECTIVE = "effective"
AUTO_PRIME_VERIFICATION_INEFFECTIVE = "ineffective"


@dataclass(frozen=True)
class MonitorRenderContext:
    label_width: int = 24
    value_width: int = 24
    suffix_width: int = 12
    row_indent: str = "  "


DEFAULT_MONITOR_RENDER_CONTEXT = MonitorRenderContext()


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
    target_limit_ids: dict[str, tuple[str, ...]] = field(default_factory=dict)
    triggers: dict[str, tuple[str, ...]] = field(default_factory=dict)
    retry_cooldown_sec: float | None = None
    loaded_at: str | None = None
    config_fingerprint: str | None = None


@dataclass
class MonitorState:
    tick: int = 0
    workflow_run_counts: dict[str, int] = field(default_factory=dict)
    data: dict[str, object] = field(default_factory=dict)


@dataclass
class MonitorTextRow:
    text: str
    kind: Literal["text"] = "text"

    def render_frame(
        self, context: MonitorRenderContext = DEFAULT_MONITOR_RENDER_CONTEXT
    ) -> str:
        if not self.text:
            return ""
        return f"{context.row_indent}{self.text}"

    def step_animation(self) -> None:
        return None

    def summary(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "text": self.text,
        }


class _MonitorColumnRowMixin:
    label: str
    value: str | None
    suffix: str | None
    animation_tick: int

    @property
    def text(self) -> str:
        return _column_text(label=self.label, value=self.value, suffix=self.suffix)

    def render_frame(
        self, context: MonitorRenderContext = DEFAULT_MONITOR_RENDER_CONTEXT
    ) -> str:
        return _render_column_row(
            label=self.label,
            value=self.value,
            suffix=self.suffix,
            animation_tick=self.animation_tick,
            context=context,
        )

    def step_animation(self) -> None:
        self.animation_tick += 1


@dataclass
class MonitorAccountRow:
    label: str
    status: str | None = None
    kind: Literal["account"] = "account"
    animation_tick: int = field(default=0, init=False, repr=False, compare=False)

    @property
    def text(self) -> str:
        if self.status is None:
            return self.label
        return f"{self.label}  {self.status}"

    def render_frame(
        self, context: MonitorRenderContext = DEFAULT_MONITOR_RENDER_CONTEXT
    ) -> str:
        label = _render_cell(self.label, context.label_width, self.animation_tick)
        if self.status is None:
            return f"{context.row_indent}{label}"
        total_width = (
            context.label_width + context.value_width + context.suffix_width + 6
        )
        status_width = max(0, total_width - context.label_width - 3)
        status = _render_cell(self.status, status_width, self.animation_tick)
        return f"{context.row_indent}{label} | {status}"

    def step_animation(self) -> None:
        self.animation_tick += 1

    def summary(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "kind": self.kind,
            "text": self.text,
            "label": self.label,
        }
        if self.status is not None:
            payload["status"] = self.status
        return payload


@dataclass
class MonitorInfoRow(_MonitorColumnRowMixin):
    label: str
    value: str
    suffix: str | None = None
    kind: Literal["info"] = "info"
    animation_tick: int = field(default=0, init=False, repr=False, compare=False)

    def summary(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "kind": self.kind,
            "text": self.text,
            "label": self.label,
            "value": self.value,
        }
        if self.suffix is not None:
            payload["suffix"] = self.suffix
        return payload


@dataclass
class MonitorUsageTimeRow(_MonitorColumnRowMixin):
    label: str
    value: str
    suffix: str | None
    used_percent: int
    elapsed_percent: int
    ratio: float | None
    kind: Literal["usage_time"] = "usage_time"
    animation_tick: int = field(default=0, init=False, repr=False, compare=False)

    def summary(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "kind": self.kind,
            "text": self.text,
            "label": self.label,
            "value": self.value,
            "used_percent": self.used_percent,
            "elapsed_percent": self.elapsed_percent,
            "ratio": self.ratio,
        }
        if self.suffix is not None:
            payload["suffix"] = self.suffix
        return payload


@dataclass
class MonitorResetRow(_MonitorColumnRowMixin):
    label: str
    value: str
    suffix: str | None
    elapsed_percent: int
    marker_percent: int | None = None
    kind: Literal["reset"] = "reset"
    animation_tick: int = field(default=0, init=False, repr=False, compare=False)

    def summary(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "kind": self.kind,
            "text": self.text,
            "label": self.label,
            "value": self.value,
            "elapsed_percent": self.elapsed_percent,
            "marker_percent": self.marker_percent,
        }
        if self.suffix is not None:
            payload["suffix"] = self.suffix
        return payload


MonitorRow = (
    MonitorTextRow
    | MonitorAccountRow
    | MonitorInfoRow
    | MonitorUsageTimeRow
    | MonitorResetRow
)


def _column_text(*, label: str, value: str | None, suffix: str | None) -> str:
    if value is None:
        return label
    if suffix is None:
        return f"{label} | {value}"
    return f"{label} | {value} | {suffix}"


def _render_column_row(
    *,
    label: str,
    value: str | None,
    suffix: str | None,
    animation_tick: int,
    context: MonitorRenderContext,
) -> str:
    label_text = _render_cell(label, context.label_width, animation_tick)
    if value is None:
        return f"{context.row_indent}{label_text}"
    value_text = _render_cell(value, context.value_width, animation_tick)
    if suffix is None:
        return f"{context.row_indent}{label_text} | {value_text}"
    suffix_text = _render_cell(suffix, context.suffix_width, animation_tick)
    return f"{context.row_indent}{label_text} | {value_text} | {suffix_text}"


def _render_cell(value: str, width: int, animation_tick: int) -> str:
    from rich.cells import cell_len, set_cell_size

    if width <= 0:
        return value
    if cell_len(value) <= width:
        return set_cell_size(value, width)
    return set_cell_size(_circular_cell_viewport(value, animation_tick, width), width)


def _circular_cell_viewport(value: str, animation_tick: int, width: int) -> str:
    from rich.cells import cell_len

    separator = " | "
    cycle_width = cell_len(value) + cell_len(separator)
    offset = animation_tick % cycle_width
    return _cell_viewport(f"{value}{separator}{value}", offset, width)


def _cell_viewport(value: str, offset: int, width: int) -> str:
    start_index = _cell_offset_to_text_index(value, offset)
    end_index = _cell_offset_to_text_index(value, offset + width)
    return value[start_index:end_index]


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

    def step_animations(self) -> None:
        for block in self.blocks:
            for row in monitor_block_rows(block):
                row.step_animation()

    def inherit_animation_state_from(self, previous: MonitorFrame) -> None:
        for row, previous_row in zip(_frame_rows(self), _frame_rows(previous)):
            _inherit_row_animation_state(row, previous_row)


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
    if isinstance(
        row,
        MonitorTextRow
        | MonitorAccountRow
        | MonitorInfoRow
        | MonitorUsageTimeRow
        | MonitorResetRow,
    ):
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
        isinstance(
            row,
            MonitorTextRow
            | MonitorAccountRow
            | MonitorInfoRow
            | MonitorUsageTimeRow
            | MonitorResetRow,
        )
        for row in rows
    ):
        return rows
    lines = block.get("lines")
    if isinstance(lines, list):
        return [MonitorTextRow(line) for line in lines if isinstance(line, str)]
    return []


def _frame_rows(frame: MonitorFrame) -> list[MonitorRow]:
    rows: list[MonitorRow] = []
    for block in frame.blocks:
        rows.extend(monitor_block_rows(block))
    return rows


def _inherit_row_animation_state(row: MonitorRow, previous_row: MonitorRow) -> None:
    if type(row) is not type(previous_row):
        return
    if not isinstance(row, MonitorAccountRow | _MonitorColumnRowMixin) or not isinstance(
        previous_row, MonitorAccountRow | _MonitorColumnRowMixin
    ):
        return
    if row.text != previous_row.text:
        return
    row.animation_tick = previous_row.animation_tick
