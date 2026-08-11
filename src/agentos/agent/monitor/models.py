# $kw: --from Normalization.Pipeline::Account.Usage.Model
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

MonitorUsageVariant = Literal["used", "left"]


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
    value_width: int = 25
    suffix_width: int = 12
    row_indent: str = "  "
    usage_variant: MonitorUsageVariant = "used"


DEFAULT_MONITOR_RENDER_CONTEXT = MonitorRenderContext()


@dataclass(frozen=True)
class MonitorTarget:
    provider: str
    account: str
    home: Path
    profile: str | None = None

    def summary(self) -> dict[str, str]:
        payload = {
            "provider": self.provider,
            "account": self.account,
            "home": str(self.home),
        }
        if self.profile is not None:
            payload["profile"] = self.profile
        return payload


@dataclass(frozen=True)
class MonitorWorkflowConfig:
    name: str
    targets: tuple[MonitorTarget, ...]
    refresh_interval_sec: float
    raw_config: dict[str, object]
    start_path: Path | None = None
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


def _text_row_render(
    text: str, *, indent: bool, context: MonitorRenderContext
) -> str:
    if not text:
        return ""
    if indent:
        return f"{context.row_indent}{text}"
    return text


def _text_row_summary(
    *, kind: str, text: str, indent: bool, default_indent: bool
) -> dict[str, object]:
    payload: dict[str, object] = {
        "kind": kind,
        "text": text,
    }
    if indent is not default_indent:
        payload["indent"] = indent
    return payload


@dataclass
class MonitorTextRow:
    text: str
    indent: bool = True
    kind: Literal["text"] = "text"

    def render_frame(
        self, context: MonitorRenderContext = DEFAULT_MONITOR_RENDER_CONTEXT
    ) -> str:
        return _text_row_render(self.text, indent=self.indent, context=context)

    def step_animation(self) -> None:
        return None

    def summary(self) -> dict[str, object]:
        return _text_row_summary(
            kind=self.kind, text=self.text, indent=self.indent, default_indent=True
        )


@dataclass
class MonitorMarqueeRow:
    text: str
    indent: bool = False
    kind: Literal["marquee"] = "marquee"
    animation_tick: int = field(default=0, init=False, repr=False, compare=False)

    def render_frame(
        self, context: MonitorRenderContext = DEFAULT_MONITOR_RENDER_CONTEXT
    ) -> str:
        return _text_row_render(self.text, indent=self.indent, context=context)

    def step_animation(self) -> None:
        self.animation_tick += 1

    def summary(self) -> dict[str, object]:
        return _text_row_summary(
            kind=self.kind, text=self.text, indent=self.indent, default_indent=False
        )


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


@dataclass(frozen=True)
class MonitorColumnVariant:
    label: str
    value: str

    def summary(self) -> dict[str, object]:
        return {
            "label": self.label,
            "value": self.value,
        }


@dataclass
class MonitorUsageTimeRow(_MonitorColumnRowMixin):
    label: str
    value: str
    suffix: str | None
    used_percent: int
    elapsed_percent: int
    ratio: float | None
    variants: tuple[MonitorColumnVariant, ...] = ()
    burst_unit: dict[str, object] | None = None
    kind: Literal["usage_time"] = "usage_time"
    animation_tick: int = field(default=0, init=False, repr=False, compare=False)

    def render_frame(
        self, context: MonitorRenderContext = DEFAULT_MONITOR_RENDER_CONTEXT
    ) -> str:
        return _render_column_row(
            label=self._active_label(context),
            value=self._active_value(context),
            suffix=self.suffix,
            animation_tick=self.animation_tick,
            context=context,
        )

    def _active_label(self, context: MonitorRenderContext) -> str:
        variant = self._active_variant(context)
        if variant is None:
            return self.label
        return variant.label

    def _active_value(self, context: MonitorRenderContext) -> str:
        variant = self._active_variant(context)
        if variant is None:
            return self.value
        return variant.value

    def _active_variant(
        self, context: MonitorRenderContext
    ) -> MonitorColumnVariant | None:
        if not self.variants:
            return None
        index = 1 if context.usage_variant == "left" else 0
        if index >= len(self.variants):
            index = 0
        return self.variants[index]

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
        if self.variants:
            payload["variants"] = [variant.summary() for variant in self.variants]
        if self.burst_unit is not None:
            payload["burst_unit"] = dict(self.burst_unit)
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
    | MonitorMarqueeRow
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
class MonitorBlock:
    title: str | None = None
    rows: list[MonitorRow] = field(default_factory=list)
    data: dict[str, object] | None = None

    @property
    def heading_rows(self) -> list[MonitorRow]:


        if self.title is None:
            return []
        return [MonitorTextRow(self.title, indent=False)]

    def payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "heading_rows": [row.summary() for row in self.heading_rows],
            "rows": [row.summary() for row in self.rows],
        }
        if self.title is not None:
            payload["title"] = self.title
        if self.data is not None:
            payload["data"] = self.data
        return payload


@dataclass
class MonitorFrame:
    tick: int = 0
    top_rows: list[MonitorRow] = field(default_factory=list)
    blocks: list[MonitorBlock] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def prepare(self, *, tick: int) -> None:
        self.tick = tick
        self.top_rows.clear()
        self.blocks.clear()
        self.warnings.clear()
        self.errors.clear()

    def add_top_row(self, row: MonitorRow) -> None:
        self.top_rows.append(row)

    def add_block(
        self,
        title: str | None = None,
        data: dict[str, object] | None = None,
        rows: list[MonitorRow] | None = None,
    ) -> None:
        self.blocks.append(
            MonitorBlock(title=title, rows=list(rows or []), data=data)
        )

    def add_error(self, message: str) -> None:
        self.errors.append(message)

    def step_animations(self) -> None:
        for row in _frame_rows(self):
            row.step_animation()

    def inherit_animation_state_from(self, previous: MonitorFrame) -> None:

        for row, previous_row in zip(_frame_rows(self), _frame_rows(previous), strict=False):
            _inherit_row_animation_state(row, previous_row)


def _frame_rows(frame: MonitorFrame) -> list[MonitorRow]:
    rows: list[MonitorRow] = list(frame.top_rows)
    for block in frame.blocks:
        rows.extend(block.heading_rows)
        rows.extend(block.rows)
    return rows


def _inherit_row_animation_state(row: MonitorRow, previous_row: MonitorRow) -> None:
    if type(row) is not type(previous_row):
        return
    if not isinstance(
        row, MonitorMarqueeRow | MonitorAccountRow | _MonitorColumnRowMixin
    ) or not isinstance(
        previous_row, MonitorMarqueeRow | MonitorAccountRow | _MonitorColumnRowMixin
    ):
        return
    if row.text != previous_row.text:
        return
    row.animation_tick = previous_row.animation_tick
