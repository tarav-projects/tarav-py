from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

PALETTE = [
    "#0f766e",
    "#2563eb",
    "#ea580c",
    "#7c3aed",
    "#dc2626",
    "#0891b2",
    "#65a30d",
    "#c2410c",
]
PROVIDER_COLORS = {
    "codex": "#2563eb",
    "claude-code": "#ea580c",
    "copilot": "#0f766e",
    "copilot-cli": "#7c3aed",
}
SURFACE = "#fbf7ef"
GRID = "#ddd6c8"
TEXT = "#231f1a"
MUTED = "#6e665e"

RAW_SCRIPT_PATH = Path(sys.argv[0]) if sys.argv and sys.argv[0] else Path(__file__)
SCRIPT_PATH = RAW_SCRIPT_PATH.absolute()
REPO_ROOT = SCRIPT_PATH.parents[1]
DEFAULT_TAPE_ROOT = Path.home() / ".agentos" / "chat-account-stats" / "history"
DEFAULT_OUTPUT_DIR = SCRIPT_PATH.parent / "plots"


def maybe_str(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    value = value.strip()
    return value or None


def maybe_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(round(value))
    try:
        return int(round(float(str(value))))
    except (TypeError, ValueError):
        return None


def parse_utc(value: object) -> dt.datetime | None:
    text = maybe_str(value)
    if text is None:
        return None
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def iso_utc(value: dt.datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def pretty_ts(value: dt.datetime | None) -> str:
    if value is None:
        return "n/a"
    return value.astimezone().strftime("%Y-%m-%d %H:%M")


def provider_title(provider: str | None) -> str:
    mapping = {
        "codex": "Codex",
        "claude-code": "Claude Code",
        "copilot": "Copilot",
        "copilot-cli": "Copilot CLI",
    }
    return mapping.get(provider or "", provider or "unknown")


def codex_window_name(window_duration_mins: int | None, window_key: str | None) -> str:
    if window_duration_mins == 300:
        return "burst"
    if window_duration_mins == 1440:
        return "daily"
    if window_duration_mins == 10080:
        return "weekly"
    if window_duration_mins is not None:
        return f"{window_duration_mins}m"
    return window_key or "usage"


def codex_window_label(window_duration_mins: int | None, window_key: str | None) -> str:
    if window_duration_mins == 300:
        return "Burst"
    if window_duration_mins == 1440:
        return "24h"
    if window_duration_mins == 10080:
        return "Weekly"
    if window_duration_mins is not None:
        return f"{window_duration_mins}m"
    return window_key or "usage"


def claude_limit_name(limit_type: str | None) -> str:
    mapping = {
        "five_hour": "burst",
        "seven_day": "weekly",
        "seven_day_opus": "weekly_opus",
        "seven_day_sonnet": "weekly_sonnet",
        "overage": "extra",
    }
    return mapping.get(limit_type or "", limit_type or "usage")


def claude_limit_label(limit_type: str | None) -> str:
    mapping = {
        "five_hour": "Burst",
        "seven_day": "Weekly",
        "seven_day_opus": "Weekly Opus",
        "seven_day_sonnet": "Weekly Sonnet",
        "overage": "extra",
    }
    return mapping.get(limit_type or "", limit_type or "usage")


def copilot_limit_name(limit_label: str | None) -> str:
    label = (limit_label or "usage").strip().lower()
    if "premium" in label:
        return "premium"
    if "chat" in label:
        return "chat"
    return label.replace(" ", "_")


def compute_elapsed_percent(
    recorded_at: dt.datetime,
    period_started_at: dt.datetime | None,
    period_ends_at: dt.datetime | None,
) -> int | None:
    if period_started_at is None or period_ends_at is None:
        return None
    if period_ends_at <= period_started_at:
        return None
    span = (period_ends_at - period_started_at).total_seconds()
    if span <= 0:
        return None
    elapsed = (recorded_at - period_started_at).total_seconds()
    ratio = max(0.0, min(1.0, elapsed / span))
    return round(ratio * 100)


def normalize_limit_payload(limit_payload: dict[str, Any], provider: str) -> dict[str, Any] | None:
    usage_over_time = limit_payload.get("usage_over_time")
    if isinstance(usage_over_time, dict):
        limit_name = maybe_str(limit_payload.get("limit_name"))
        limit_label = maybe_str(limit_payload.get("limit_label"))
        provider_limit = limit_payload.get("provider_limit")
        if not isinstance(provider_limit, dict):
            provider_limit = {}
        if limit_name is None and provider == "copilot":
            limit_name = copilot_limit_name(limit_label)
        if limit_name is None:
            limit_name = "usage"
        if limit_label is None:
            limit_label = limit_name.replace("_", " ").title()
        return {
            "limit_class": maybe_str(limit_payload.get("limit_class")) or "usage_over_time",
            "limit_name": limit_name,
            "limit_label": limit_label,
            "used_percent": maybe_int(usage_over_time.get("used_percent")),
            "period_started_at": parse_utc(usage_over_time.get("period_started_at")),
            "period_ends_at": parse_utc(usage_over_time.get("period_ends_at") or usage_over_time.get("resets_at")),
            "period_duration_mins": maybe_int(usage_over_time.get("period_duration_mins")),
            "resets_at": parse_utc(usage_over_time.get("resets_at") or usage_over_time.get("period_ends_at")),
        }

    used_percent = maybe_int(limit_payload.get("used_percent"))
    if used_percent is None:
        return None

    period_duration_mins = maybe_int(
        limit_payload.get("period_duration_mins") or limit_payload.get("window_duration_mins")
    )
    period_started_at = parse_utc(limit_payload.get("period_started_at"))
    period_ends_at = parse_utc(limit_payload.get("period_ends_at") or limit_payload.get("resets_at"))
    resets_at = parse_utc(limit_payload.get("resets_at") or limit_payload.get("period_ends_at"))

    if provider == "codex" or "window_key" in limit_payload or "limit_id" in limit_payload:
        window_key = maybe_str(limit_payload.get("window_key"))
        limit_name = codex_window_name(period_duration_mins, window_key)
        limit_label = codex_window_label(period_duration_mins, window_key)
    elif provider == "claude-code" or "limit_type" in limit_payload:
        limit_type = maybe_str(limit_payload.get("limit_type"))
        limit_name = claude_limit_name(limit_type)
        limit_label = claude_limit_label(limit_type)
    else:
        limit_label = maybe_str(limit_payload.get("limit_label")) or "usage"
        limit_name = copilot_limit_name(limit_label)

    return {
        "limit_class": "usage_over_time" if period_started_at or period_ends_at or period_duration_mins else "usage_snapshot",
        "limit_name": limit_name,
        "limit_label": limit_label,
        "used_percent": used_percent,
        "period_started_at": period_started_at,
        "period_ends_at": period_ends_at,
        "period_duration_mins": period_duration_mins,
        "resets_at": resets_at,
    }


def iter_tape_records(tape_root: Path) -> Any:
    for segment_path in sorted((tape_root / "segments").glob("*.jsonl")):
        with segment_path.open(encoding="utf-8") as handle:
            for line_no, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise RuntimeError(f"invalid json in {segment_path}:{line_no}: {exc}") from exc
                if isinstance(payload, dict):
                    yield payload


def build_usage_dataset(tape_root: Path) -> dict[str, list[dict[str, Any]]]:
    snapshot_rows: list[dict[str, Any]] = []
    account_rows: list[dict[str, Any]] = []
    limit_rows: list[dict[str, Any]] = []
    aggregate_rows: list[dict[str, Any]] = []

    for record in iter_tape_records(tape_root):
        recorded_at = parse_utc(record.get("recorded_at"))
        if recorded_at is None:
            continue
        recorded_day = recorded_at.date().isoformat()
        providers = record.get("providers")
        if not isinstance(providers, list):
            providers = []

        snapshot_rows.append(
            {
                "recorded_at": recorded_at,
                "recorded_day": recorded_day,
                "provider_count": maybe_int(record.get("provider_count")) or 0,
                "account_count": maybe_int(record.get("account_count")) or 0,
                "ok_count": maybe_int(record.get("ok_count")) or 0,
                "error_count": maybe_int(record.get("error_count")) or 0,
            }
        )

        usage_total = record.get("accounts_usage_total")
        if isinstance(usage_total, dict):
            aggregate = usage_total.get("aggregate")
            if isinstance(aggregate, dict):
                aggregate_rows.append(
                    {
                        "recorded_at": recorded_at,
                        "recorded_day": recorded_day,
                        "label": maybe_str(usage_total.get("label")) or "Selected accounts aggregate",
                        "used_percent": maybe_int(aggregate.get("used_percent")),
                        "elapsed_percent": maybe_int(aggregate.get("elapsed_percent")),
                        "ratio": aggregate.get("ratio"),
                        "included_count": maybe_int(usage_total.get("included_count")),
                    }
                )

        for provider_payload in providers:
            if not isinstance(provider_payload, dict):
                continue
            provider = maybe_str(provider_payload.get("provider")) or "unknown"
            accounts = provider_payload.get("accounts")
            if not isinstance(accounts, list):
                continue

            for account in accounts:
                if not isinstance(account, dict):
                    continue
                account_id = maybe_str(account.get("id")) or "unknown"
                account_label = maybe_str(account.get("label")) or account_id
                account_key = f"{provider}:{account_id}"
                account_rows.append(
                    {
                        "recorded_at": recorded_at,
                        "recorded_day": recorded_day,
                        "provider": provider,
                        "account_id": account_id,
                        "account_label": account_label,
                        "account_key": account_key,
                        "check_status": maybe_str(account.get("check_status")) or "unknown",
                        "usage_status": maybe_str(account.get("usage_status")),
                    }
                )

                usage = account.get("usage")
                if not isinstance(usage, dict):
                    continue
                raw_limits = usage.get("limits")
                if not isinstance(raw_limits, list):
                    continue

                for raw_limit in raw_limits:
                    if not isinstance(raw_limit, dict):
                        continue
                    normalized = normalize_limit_payload(raw_limit, provider)
                    if normalized is None:
                        continue
                    elapsed_percent = compute_elapsed_percent(
                        recorded_at,
                        normalized["period_started_at"],
                        normalized["period_ends_at"],
                    )
                    used_percent = normalized["used_percent"]
                    usage_gap = None
                    if isinstance(used_percent, int) and isinstance(elapsed_percent, int):
                        usage_gap = used_percent - elapsed_percent
                    series_key = f"{account_key}:{normalized['limit_name']}"
                    series_label = f"{provider_title(provider)} / {account_label} / {normalized['limit_label']}"
                    period_signature = (
                        iso_utc(normalized["period_started_at"]),
                        iso_utc(normalized["period_ends_at"]),
                        iso_utc(normalized["resets_at"]),
                        normalized["period_duration_mins"],
                    )
                    limit_rows.append(
                        {
                            "recorded_at": recorded_at,
                            "recorded_day": recorded_day,
                            "provider": provider,
                            "account_id": account_id,
                            "account_label": account_label,
                            "account_key": account_key,
                            "limit_name": normalized["limit_name"],
                            "limit_label": normalized["limit_label"],
                            "series_key": series_key,
                            "series_label": series_label,
                            "used_percent": used_percent,
                            "elapsed_percent": elapsed_percent,
                            "usage_gap": usage_gap,
                            "period_signature": period_signature,
                        }
                    )

    snapshot_rows.sort(key=lambda row: row["recorded_at"])
    account_rows.sort(key=lambda row: (row["recorded_at"], row["account_key"]))
    limit_rows.sort(key=lambda row: (row["recorded_at"], row["series_key"]))
    aggregate_rows.sort(key=lambda row: row["recorded_at"])

    return {
        "snapshot_rows": snapshot_rows,
        "account_rows": account_rows,
        "limit_rows": limit_rows,
        "aggregate_rows": aggregate_rows,
    }


def build_speed_rows(limit_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in limit_rows:
        if isinstance(row.get("used_percent"), int):
            grouped[row["series_key"]].append(row)

    speed_rows: list[dict[str, Any]] = []
    for series_key, rows in grouped.items():
        rows = sorted(rows, key=lambda row: row["recorded_at"])
        previous: dict[str, Any] | None = None
        for row in rows:
            if previous is not None and row["period_signature"] == previous["period_signature"]:
                delta_minutes = (row["recorded_at"] - previous["recorded_at"]).total_seconds() / 60.0
                delta_used = row["used_percent"] - previous["used_percent"]
                if delta_minutes > 0 and delta_used >= 0:
                    speed_rows.append(
                        {
                            "series_key": series_key,
                            "series_label": row["series_label"],
                            "started_at": previous["recorded_at"],
                            "ended_at": row["recorded_at"],
                            "delta_minutes": delta_minutes,
                            "delta_used": delta_used,
                            "percent_per_hour": (delta_used / delta_minutes) * 60.0,
                        }
                    )
            previous = row

    speed_rows.sort(key=lambda row: row["ended_at"], reverse=True)
    return speed_rows


def stable_index(name: str, size: int) -> int:
    digest = hashlib.sha1(name.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % size


def hex_to_rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return tuple(int(color[index : index + 2], 16) for index in (0, 2, 4))


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#" + "".join(f"{max(0, min(255, channel)):02x}" for channel in rgb)


def blend(color_a: str, color_b: str, weight: float) -> str:
    a = hex_to_rgb(color_a)
    b = hex_to_rgb(color_b)
    mixed = tuple(round((1 - weight) * left + weight * right) for left, right in zip(a, b))
    return rgb_to_hex(mixed)


def color_for(name: str, provider: str | None = None) -> str:
    base = PROVIDER_COLORS.get(provider or "", PALETTE[stable_index(name, len(PALETTE))])
    accent = PALETTE[stable_index(name + "-accent", len(PALETTE))]
    return blend(base, accent, 0.18)


def format_percent(value: object, signed: bool = False) -> str:
    if value is None:
        return "n/a"
    if signed:
        return f"{int(value):+d}%"
    return f"{int(value)}%"


def axis_time_label(value: dt.datetime, span: dt.timedelta) -> str:
    if span.days >= 10:
        return value.strftime("%b %d")
    if span.days >= 1:
        return value.strftime("%b %d %H:%M")
    return value.strftime("%H:%M")


def sample_points(points: list[tuple[dt.datetime, float, str]], max_points: int = 1200) -> list[tuple[dt.datetime, float, str]]:
    if len(points) <= max_points:
        return points
    step = max(1, math.ceil(len(points) / max_points))
    sampled = points[::step]
    if sampled[-1] != points[-1]:
        sampled.append(points[-1])
    return sampled


def render_line_chart(
    series_list: list[dict[str, Any]],
    *,
    title: str,
    subtitle: str,
    width: int = 1200,
    height: int = 360,
    y_domain: tuple[float, float] | None = None,
    y_ticks: int = 5,
    baseline_values: tuple[float, ...] = (),
    unit: str = "%",
) -> str:
    filtered_series = []
    x_values: list[dt.datetime] = []
    y_values: list[float] = []
    for series in series_list:
        points = [(point[0], point[1], point[2]) for point in series["points"] if point[1] is not None]
        if not points:
            continue
        points = sample_points(points)
        filtered_series.append({**series, "points": points})
        x_values.extend(point[0] for point in points)
        y_values.extend(point[1] for point in points)

    if not filtered_series:
        return simple_svg_message(title=title, subtitle=subtitle, message="No points available.")

    x_min = min(x_values)
    x_max = max(x_values)
    if x_min == x_max:
        x_min -= dt.timedelta(minutes=30)
        x_max += dt.timedelta(minutes=30)
    span = x_max - x_min

    if y_domain is None:
        y_min = min(y_values)
        y_max = max(y_values)
        if y_min == y_max:
            pad = 1.0 if y_min == 0 else abs(y_min) * 0.1
        else:
            pad = (y_max - y_min) * 0.08
        y_min -= pad
        y_max += pad
        if y_min > 0:
            y_min = 0.0
        if y_max < 0:
            y_max = 0.0
    else:
        y_min, y_max = y_domain

    if y_max <= y_min:
        y_max = y_min + 1.0

    margin_left = 64
    margin_right = 26
    margin_top = 28
    margin_bottom = 52
    inner_width = width - margin_left - margin_right
    inner_height = height - margin_top - margin_bottom

    def x_scale(value: dt.datetime) -> float:
        return margin_left + ((value - x_min).total_seconds() / span.total_seconds()) * inner_width

    def y_scale(value: float) -> float:
        return margin_top + (1.0 - ((value - y_min) / (y_max - y_min))) * inner_height

    svg_parts = [
        f"<rect x='0' y='0' width='{width}' height='{height}' rx='22' fill='{SURFACE}' />"
    ]

    for tick_index in range(y_ticks + 1):
        value = y_min + ((y_max - y_min) * tick_index / y_ticks)
        y_pos = y_scale(value)
        label = f"{value:.0f}{unit}" if unit else f"{value:.0f}"
        svg_parts.append(
            f"<line x1='{margin_left}' y1='{y_pos:.2f}' x2='{width - margin_right}' y2='{y_pos:.2f}' stroke='{GRID}' stroke-width='1' />"
        )
        svg_parts.append(
            f"<text x='{margin_left - 10}' y='{y_pos + 4:.2f}' fill='{MUTED}' font-size='11' text-anchor='end'>{html.escape(label)}</text>"
        )

    for baseline in baseline_values:
        if y_min <= baseline <= y_max:
            y_pos = y_scale(baseline)
            svg_parts.append(
                f"<line x1='{margin_left}' y1='{y_pos:.2f}' x2='{width - margin_right}' y2='{y_pos:.2f}' stroke='{TEXT}' stroke-width='1.2' stroke-dasharray='5 5' opacity='0.45' />"
            )

    tick_count = 6
    for tick_index in range(tick_count):
        ratio = tick_index / max(1, tick_count - 1)
        tick_time = x_min + dt.timedelta(seconds=span.total_seconds() * ratio)
        x_pos = x_scale(tick_time)
        svg_parts.append(
            f"<line x1='{x_pos:.2f}' y1='{margin_top + inner_height}' x2='{x_pos:.2f}' y2='{margin_top + inner_height + 6}' stroke='{GRID}' stroke-width='1' />"
        )
        svg_parts.append(
            f"<text x='{x_pos:.2f}' y='{height - 18}' fill='{MUTED}' font-size='11' text-anchor='middle'>{html.escape(axis_time_label(tick_time, span))}</text>"
        )

    legend_items: list[str] = []
    for series in filtered_series:
        color = series.get("color") or color_for(series["name"], series.get("provider"))
        points = sorted(series["points"], key=lambda point: point[0])
        polyline_points = " ".join(f"{x_scale(point[0]):.2f},{y_scale(point[1]):.2f}" for point in points)
        dasharray = series.get("dasharray")
        dash_attr = f" stroke-dasharray='{dasharray}'" if dasharray else ""
        svg_parts.append(
            f"<polyline fill='none' stroke='{color}' stroke-width='2.6' stroke-linejoin='round' stroke-linecap='round'{dash_attr} points='{polyline_points}' />"
        )
        if len(points) <= 80:
            for point in points:
                svg_parts.append(
                    f"<circle cx='{x_scale(point[0]):.2f}' cy='{y_scale(point[1]):.2f}' r='2.8' fill='{color}'><title>{html.escape(point[2])}</title></circle>"
                )
        legend_items.append(
            f"<span class='legend-item'><span class='legend-dot' style='background:{color}'></span>{html.escape(series['name'])}</span>"
        )

    svg = f"<svg viewBox='0 0 {width} {height}' width='100%'>{''.join(svg_parts)}</svg>"
    legend_html = "<div class='legend'>" + "".join(legend_items) + "</div>"
    return wrap_panel(svg=svg, title=title, subtitle=subtitle, extra=legend_html)


def render_bar_chart(
    items: list[dict[str, Any]],
    *,
    title: str,
    subtitle: str,
    width: int = 1200,
    height: int = 300,
    unit: str = "",
) -> str:
    if not items:
        return simple_svg_message(title=title, subtitle=subtitle, message="No bars available.")

    values = [item["value"] for item in items]
    max_value = max(values) or 1
    margin_left = 58
    margin_right = 24
    margin_top = 28
    margin_bottom = 54
    inner_width = width - margin_left - margin_right
    inner_height = height - margin_top - margin_bottom
    bar_width = inner_width / max(1, len(items))

    svg_parts = [
        f"<rect x='0' y='0' width='{width}' height='{height}' rx='22' fill='{SURFACE}' />"
    ]

    for tick_index in range(5):
        value = max_value * tick_index / 4
        y_pos = margin_top + inner_height - ((value / max_value) * inner_height)
        label = f"{value:.0f}{unit}" if unit else f"{value:.0f}"
        svg_parts.append(
            f"<line x1='{margin_left}' y1='{y_pos:.2f}' x2='{width - margin_right}' y2='{y_pos:.2f}' stroke='{GRID}' stroke-width='1' />"
        )
        svg_parts.append(
            f"<text x='{margin_left - 10}' y='{y_pos + 4:.2f}' fill='{MUTED}' font-size='11' text-anchor='end'>{html.escape(label)}</text>"
        )

    label_step = max(1, math.ceil(len(items) / 12))
    for index, item in enumerate(items):
        value = item["value"]
        x_pos = margin_left + index * bar_width + 2
        bar_height = (value / max_value) * inner_height if max_value else 0
        y_pos = margin_top + inner_height - bar_height
        color = item.get("color") or PALETTE[index % len(PALETTE)]
        tooltip = html.escape(f"{item['label']}: {value}{unit}")
        svg_parts.append(
            f"<rect x='{x_pos:.2f}' y='{y_pos:.2f}' width='{max(1.0, bar_width - 4.0):.2f}' height='{bar_height:.2f}' rx='4' fill='{color}' opacity='0.92'><title>{tooltip}</title></rect>"
        )
        if index % label_step == 0:
            svg_parts.append(
                f"<text x='{x_pos + (bar_width - 4.0) / 2:.2f}' y='{height - 18}' fill='{MUTED}' font-size='10' text-anchor='middle'>{html.escape(str(item['label']))}</text>"
            )

    svg = f"<svg viewBox='0 0 {width} {height}' width='100%'>{''.join(svg_parts)}</svg>"
    return wrap_panel(svg=svg, title=title, subtitle=subtitle)


def wrap_panel(*, svg: str, title: str, subtitle: str, extra: str = "") -> str:
    return (
        "<figure class='plot-panel'>"
        f"<figcaption><h2>{html.escape(title)}</h2><p>{html.escape(subtitle)}</p></figcaption>"
        f"{svg}{extra}</figure>"
    )


def simple_svg_message(*, title: str, subtitle: str, message: str) -> str:
    svg = (
        "<svg viewBox='0 0 1200 200' width='100%'>"
        f"<rect x='0' y='0' width='1200' height='200' rx='22' fill='{SURFACE}' />"
        f"<text x='600' y='108' fill='{MUTED}' font-size='22' text-anchor='middle'>{html.escape(message)}</text>"
        "</svg>"
    )
    return wrap_panel(svg=svg, title=title, subtitle=subtitle)


def latest_rows_by_key(rows: list[dict[str, Any]], key_field: str) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        latest[row[key_field]] = row
    return latest


def write_plot(path: Path, plot_html: str, *, title: str, subtitle: str) -> None:
    page = f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{html.escape(title)}</title>
    <style>
      body {{
        margin: 0;
        padding: 32px;
        background: linear-gradient(180deg, #faf6ee 0%, #f4efe3 100%);
        color: {TEXT};
        font-family: "Avenir Next", "Helvetica Neue", "Trebuchet MS", sans-serif;
      }}
      .plot-panel {{
        max-width: 1280px;
        margin: 0 auto;
        background: #ffffff;
        border: 1px solid #e7dece;
        border-radius: 24px;
        padding: 20px;
        box-shadow: 0 18px 40px rgba(35, 31, 26, 0.08);
      }}
      h2 {{
        margin: 0 0 4px 0;
        font-size: 22px;
      }}
      p {{
        margin: 0 0 16px 0;
        color: {MUTED};
      }}
      .legend {{
        margin-top: 12px;
        display: flex;
        flex-wrap: wrap;
        gap: 10px 14px;
        font-size: 12px;
        color: #403a33;
      }}
      .legend-item {{
        display: inline-flex;
        align-items: center;
        gap: 6px;
      }}
      .legend-dot {{
        width: 10px;
        height: 10px;
        border-radius: 999px;
        display: inline-block;
      }}
    </style>
  </head>
  <body>
    {plot_html}
  </body>
</html>
"""
    path.write_text(page, encoding="utf-8")


def save_plot_bundle(output_dir: Path, name: str, plot_html: str, *, title: str, subtitle: str) -> None:
    html_path = output_dir / f"{name}.html"
    write_plot(html_path, plot_html, title=title, subtitle=subtitle)


def choose_recent_series(
    limit_rows: list[dict[str, Any]],
    *,
    lookback_days: int,
    max_series: int,
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    if not limit_rows:
        return ([], {})
    anchor_time = limit_rows[-1]["recorded_at"]
    start_time = anchor_time - dt.timedelta(days=lookback_days)
    filtered_rows = [row for row in limit_rows if row["recorded_at"] >= start_time]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in filtered_rows:
        grouped[row["series_key"]].append(row)
    latest = [rows[-1] for rows in grouped.values()]
    latest.sort(
        key=lambda row: (
            row["recorded_at"],
            row["used_percent"] if isinstance(row["used_percent"], int) else -1,
            row["series_label"],
        ),
        reverse=True,
    )
    selected = latest[:max_series]
    selected_keys = {row["series_key"] for row in selected}
    selected_grouped = {key: grouped[key] for key in selected_keys}
    return (selected, selected_grouped)


def build_overview_plots(
    dataset: dict[str, list[dict[str, Any]]],
    *,
    lookback_days: int,
    max_series: int,
    cadence_days: int,
) -> dict[str, str]:
    snapshot_rows = dataset["snapshot_rows"]
    account_rows = dataset["account_rows"]
    limit_rows = dataset["limit_rows"]
    aggregate_rows = dataset["aggregate_rows"]

    daily_snapshot_counts: Counter[str] = Counter(row["recorded_day"] for row in snapshot_rows)
    cadence_items = [
        {"label": day[5:], "value": count, "color": "#b45309"}
        for day, count in sorted(daily_snapshot_counts.items())[-cadence_days:]
    ]
    cadence_plot = render_bar_chart(
        cadence_items,
        title="Snapshot cadence",
        subtitle=f"How often the account tape was refreshed per day over the last {len(cadence_items)} captured days.",
    )

    aggregate_plot = simple_svg_message(
        title="Selected-accounts aggregate",
        subtitle="This appears once aggregate usage snapshots exist in the tape.",
        message="No aggregate usage rows found.",
    )
    if aggregate_rows:
        recent = aggregate_rows[-1200:]
        aggregate_plot = render_line_chart(
            [
                {
                    "name": f"{recent[-1]['label']} used",
                    "color": "#111827",
                    "points": [
                        (
                            row["recorded_at"],
                            row["used_percent"],
                            f"{pretty_ts(row['recorded_at'])} | used {format_percent(row['used_percent'])} | elapsed {format_percent(row['elapsed_percent'])}",
                        )
                        for row in recent
                        if row["used_percent"] is not None
                    ],
                },
                {
                    "name": f"{recent[-1]['label']} elapsed",
                    "color": "#d97706",
                    "dasharray": "6 5",
                    "points": [
                        (
                            row["recorded_at"],
                            row["elapsed_percent"],
                            f"{pretty_ts(row['recorded_at'])} | elapsed {format_percent(row['elapsed_percent'])}",
                        )
                        for row in recent
                        if row["elapsed_percent"] is not None
                    ],
                },
            ],
            title="Selected-accounts aggregate",
            subtitle="Average used percent versus average elapsed percent for the configured aggregate selection.",
            y_domain=(0, 100),
            baseline_values=(100,),
        )

    selected_latest, selected_grouped = choose_recent_series(
        limit_rows,
        lookback_days=lookback_days,
        max_series=max_series,
    )

    usage_plot = simple_svg_message(
        title="Usage trajectories",
        subtitle="Used percent over time for the most recent series.",
        message="No limit rows found.",
    )
    gap_plot = simple_svg_message(
        title="Lead or lag versus cycle progress",
        subtitle="Positive values mean usage is ahead of elapsed cycle time.",
        message="No comparable cycle-progress rows found.",
    )
    if selected_latest:
        usage_plot = render_line_chart(
            [
                {
                    "name": row["series_label"],
                    "provider": row["provider"],
                    "color": color_for(row["series_key"], row["provider"]),
                    "points": [
                        (
                            item["recorded_at"],
                            item["used_percent"],
                            f"{item['series_label']} | {pretty_ts(item['recorded_at'])} | used {format_percent(item['used_percent'])} | elapsed {format_percent(item['elapsed_percent'])}",
                        )
                        for item in selected_grouped[row["series_key"]]
                        if item["used_percent"] is not None
                    ],
                }
                for row in selected_latest
            ],
            title="Usage trajectories",
            subtitle=f"Used percent over time for the {len(selected_latest)} most recent series in the last {lookback_days} days.",
            y_domain=(0, 100),
            baseline_values=(100,),
        )
        gap_series = [
            {
                "name": row["series_label"],
                "provider": row["provider"],
                "color": color_for(row["series_key"], row["provider"]),
                "points": [
                    (
                        item["recorded_at"],
                        item["usage_gap"],
                        f"{item['series_label']} | {pretty_ts(item['recorded_at'])} | gap {format_percent(item['usage_gap'], signed=True)}",
                    )
                    for item in selected_grouped[row["series_key"]]
                    if item["usage_gap"] is not None
                ],
            }
            for row in selected_latest
            if any(item["usage_gap"] is not None for item in selected_grouped[row["series_key"]])
        ]
        if gap_series:
            gap_plot = render_line_chart(
                gap_series,
                title="Lead or lag versus cycle progress",
                subtitle="Positive values mean usage is running ahead of elapsed cycle time; negative values mean it is behind.",
                y_domain=(-100, 100),
                baseline_values=(0,),
            )

    if account_rows:
        anchor_time = account_rows[-1]["recorded_at"]
        start_time = anchor_time - dt.timedelta(days=lookback_days)
        recent_accounts = [row for row in account_rows if row["recorded_at"] >= start_time]
    else:
        recent_accounts = []
    error_counts = Counter(row["recorded_day"] for row in recent_accounts if row["check_status"] != "ok")
    if error_counts:
        error_items = [
            {"label": day[5:], "value": error_counts[day], "color": "#dc2626"}
            for day in sorted(error_counts)
        ]
    else:
        days = sorted({row["recorded_day"] for row in recent_accounts})[-30:]
        error_items = [{"label": day[5:], "value": 0, "color": "#dc2626"} for day in days]
    error_plot = render_bar_chart(
        error_items[-30:],
        title="Daily error counts",
        subtitle=f"Account check failures across the last {lookback_days} days.",
    )

    return {
        "snapshot_cadence": cadence_plot,
        "aggregate_usage": aggregate_plot,
        "usage_trajectories": usage_plot,
        "usage_gap": gap_plot,
        "error_counts": error_plot,
    }


def render_index_html(
    *,
    dataset: dict[str, list[dict[str, Any]]],
    speed_rows: list[dict[str, Any]],
    plots: dict[str, str],
) -> str:
    snapshot_rows = dataset["snapshot_rows"]
    account_rows = dataset["account_rows"]
    limit_rows = dataset["limit_rows"]

    first_snapshot = snapshot_rows[0]["recorded_at"] if snapshot_rows else None
    last_snapshot = snapshot_rows[-1]["recorded_at"] if snapshot_rows else None
    unique_accounts = sorted({row["account_key"] for row in account_rows})
    unique_providers = sorted({row["provider"] for row in account_rows})
    unique_series = sorted({row["series_key"] for row in limit_rows})
    days_covered = 0
    if first_snapshot and last_snapshot:
        days_covered = (last_snapshot.date() - first_snapshot.date()).days + 1

    cards = [
        ("Snapshots", f"{len(snapshot_rows):,}", f"{days_covered} days of capture history"),
        ("Accounts Seen", str(len(unique_accounts)), ", ".join(provider_title(provider) for provider in unique_providers)),
        ("Limit Series", str(len(unique_series)), "normalized across schema changes"),
        ("Latest Snapshot", pretty_ts(last_snapshot), "most recent tape record"),
    ]
    card_html = "".join(
        "<div class='card'>"
        f"<div class='kicker'>{html.escape(label)}</div>"
        f"<div class='value'>{html.escape(value)}</div>"
        f"<div class='note'>{html.escape(note)}</div>"
        "</div>"
        for label, value, note in cards
    )

    latest_accounts = latest_rows_by_key(account_rows, "account_key")
    account_rows_html = "".join(
        "<tr>"
        f"<td>{html.escape(provider_title(row['provider']))}</td>"
        f"<td>{html.escape(row['account_label'])}</td>"
        f"<td>{html.escape(row['check_status'])}</td>"
        f"<td>{html.escape(row['usage_status'] or '-')}</td>"
        f"<td>{html.escape(pretty_ts(row['recorded_at']))}</td>"
        "</tr>"
        for _, row in sorted(latest_accounts.items(), key=lambda item: item[1]["provider"] + item[1]["account_label"])
    )

    top_speed_rows = speed_rows[:12]
    speed_rows_html = "".join(
        "<tr>"
        f"<td>{html.escape(row['series_label'])}</td>"
        f"<td>{html.escape(pretty_ts(row['started_at']))}</td>"
        f"<td>{html.escape(pretty_ts(row['ended_at']))}</td>"
        f"<td>{html.escape(format_percent(row['delta_used']))}</td>"
        f"<td>{html.escape(f'{row['delta_minutes']:.1f}')}</td>"
        f"<td>{html.escape(f'{row['percent_per_hour']:.2f}')}</td>"
        "</tr>"
        for row in top_speed_rows
    )

    plot_sections = []
    for key, label in [
        ("snapshot_cadence", "Snapshot cadence"),
        ("aggregate_usage", "Selected-accounts aggregate"),
        ("usage_trajectories", "Usage trajectories"),
        ("usage_gap", "Lead or lag versus cycle progress"),
        ("error_counts", "Daily error counts"),
    ]:
        html_name = f"{key}.html"
        plot_sections.append(
            "<section class='plot-link'>"
            f"<h2>{html.escape(label)}</h2>"
            f"<iframe src='{html.escape(html_name)}' loading='lazy'></iframe>"
            "</section>"
        )

    return f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Account usage plots</title>
    <style>
      :root {{
        color-scheme: light;
      }}
      body {{
        margin: 0;
        padding: 32px;
        background:
          radial-gradient(circle at top left, rgba(245, 158, 11, 0.15), transparent 28%),
          radial-gradient(circle at top right, rgba(37, 99, 235, 0.14), transparent 30%),
          linear-gradient(180deg, #fbf7ef 0%, #f4efe3 100%);
        color: {TEXT};
        font-family: "Avenir Next", "Helvetica Neue", "Trebuchet MS", sans-serif;
      }}
      main {{
        max-width: 1320px;
        margin: 0 auto;
      }}
      h1 {{
        margin: 0 0 10px 0;
        font-size: 42px;
        line-height: 1.05;
      }}
      .lede {{
        margin: 0 0 26px 0;
        color: {MUTED};
        max-width: 900px;
        font-size: 16px;
      }}
      .card-grid {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 14px;
        margin: 0 0 28px 0;
      }}
      .card {{
        background: white;
        border: 1px solid #e7dece;
        border-radius: 18px;
        padding: 16px 18px;
        box-shadow: 0 16px 38px rgba(35, 31, 26, 0.08);
      }}
      .kicker {{
        font-size: 11px;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: {MUTED};
        margin-bottom: 6px;
      }}
      .value {{
        font-size: 30px;
        font-weight: 700;
      }}
      .note {{
        margin-top: 6px;
        font-size: 12px;
        color: {MUTED};
      }}
      .plot-link {{
        margin: 0 0 22px 0;
      }}
      .plot-link h2 {{
        margin: 0 0 8px 0;
        font-size: 20px;
      }}
      .plot-link iframe {{
        width: 100%;
        height: 520px;
        border: 0;
        border-radius: 24px;
        box-shadow: 0 18px 40px rgba(35, 31, 26, 0.08);
        background: white;
      }}
      .table-panel {{
        background: white;
        border: 1px solid #e7dece;
        border-radius: 24px;
        padding: 18px 20px;
        box-shadow: 0 16px 38px rgba(35, 31, 26, 0.08);
        margin: 0 0 22px 0;
      }}
      .table-panel h2 {{
        margin: 0 0 4px 0;
        font-size: 20px;
      }}
      .table-panel p {{
        margin: 0 0 14px 0;
        color: {MUTED};
      }}
      table {{
        width: 100%;
        border-collapse: collapse;
        font-size: 13px;
      }}
      th, td {{
        text-align: left;
        padding: 9px 10px;
        border-bottom: 1px solid #efe7d8;
        vertical-align: top;
      }}
      th {{
        font-size: 11px;
        letter-spacing: 0.07em;
        text-transform: uppercase;
        color: {MUTED};
      }}
    </style>
  </head>
  <body>
    <main>
      <h1>Account usage plots</h1>
      <p class="lede">
        These plots come straight from the periodic `agentos` account-stats tape at
        <code>{html.escape(str(DEFAULT_TAPE_ROOT))}</code>. The pipeline normalizes older provider-native
        snapshots and newer unified usage snapshots into one plotting view.
      </p>
      <section class="card-grid">{card_html}</section>
      {''.join(plot_sections)}
      <section class="table-panel">
        <h2>Latest account snapshot</h2>
        <p>The most recent known status row for each account instance seen in the tape.</p>
        <table>
          <thead>
            <tr>
              <th>Provider</th>
              <th>Account</th>
              <th>Check</th>
              <th>Usage</th>
              <th>Recorded</th>
            </tr>
          </thead>
          <tbody>{account_rows_html}</tbody>
        </table>
      </section>
      <section class="table-panel">
        <h2>Fastest burn-rate intervals</h2>
        <p>Only consecutive points inside the same reset window are compared.</p>
        <table>
          <thead>
            <tr>
              <th>Series</th>
              <th>From</th>
              <th>To</th>
              <th>Delta</th>
              <th>Minutes</th>
              <th>%/hour</th>
            </tr>
          </thead>
          <tbody>{speed_rows_html}</tbody>
        </table>
      </section>
    </main>
  </body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build account-usage plots from the agentos chat-account-stats tape."
    )
    parser.add_argument(
        "--tape-root",
        type=Path,
        default=DEFAULT_TAPE_ROOT,
        help="Path to the chat-account-stats history tape root.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory where plot HTML files will be written.",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=21,
        help="Recent window used for the trajectory, gap, and error plots.",
    )
    parser.add_argument(
        "--max-series",
        type=int,
        default=6,
        help="Maximum number of recent usage series to plot together.",
    )
    parser.add_argument(
        "--cadence-days",
        type=int,
        default=45,
        help="How many captured days to include in the cadence bar chart.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tape_root = args.tape_root.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()

    if not (tape_root / "segments").exists():
        raise SystemExit(f"tape segments directory does not exist: {tape_root / 'segments'}")

    output_dir.mkdir(parents=True, exist_ok=True)

    dataset = build_usage_dataset(tape_root)
    speed_rows = build_speed_rows(dataset["limit_rows"])
    plots = build_overview_plots(
        dataset,
        lookback_days=args.lookback_days,
        max_series=args.max_series,
        cadence_days=args.cadence_days,
    )

    for plot_name, plot_html in plots.items():
        save_plot_bundle(
            output_dir,
            plot_name,
            plot_html,
            title=plot_name.replace("_", " ").title(),
            subtitle="Generated from the account-usage tape.",
        )

    index_html = render_index_html(
        dataset=dataset,
        speed_rows=speed_rows,
        plots=plots,
    )
    (output_dir / "index.html").write_text(index_html, encoding="utf-8")

    print(f"Wrote plots to {output_dir}")
    for name in sorted(plots):
        print(f"- {output_dir / (name + '.html')}")
    print(f"- {output_dir / 'index.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
