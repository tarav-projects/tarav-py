from __future__ import annotations



from tarav.agent.monitor.loop import MonitorLoop, _workflow_alarm_names, _workflows_for_snapshot
from tarav.agent.monitor.models import (
    MonitorAccountRow,
    MonitorColumnVariant,
    MonitorFrame,
    MonitorMarqueeRow,
    MonitorRenderContext,
    MonitorState,
    MonitorTextRow,
    MonitorUsageTimeRow,
)
from tarav.agent.monitor.clock import (
    ACCOUNT_ROTATION_PERIODIC_ALARM,
    LIMITS_TRACKING_PERIODIC_ALARM,
    MONITOR_MATERIALIZE_ALARM,
    MONITOR_USAGE_VARIANT_TOGGLE_ALARM,
    MonitorClockSnapshot,
)
from tarav.agent.monitor.render import format_monitor_frame, monitor_result_payload



def test_monitor_account_row_renders_status_as_full_lane() -> None:
    row = MonitorAccountRow(label="account:", status="fresh")
    context = MonitorRenderContext(
        label_width=12,
        value_width=10,
        suffix_width=8,
        row_indent="",
    )

    rendered = row.render_frame(context)

    assert rendered[:12] == "account:    "
    assert rendered[12:15] == " | "
    assert rendered[15:].startswith("fresh")
    assert rendered.count("|") == 1
    assert row.summary()["status"] == "fresh"

def test_usage_time_row_variant_follows_render_context() -> None:
    row = MonitorUsageTimeRow(
        label="    usage/time [used]",
        value="63% / 40% = 1.6 [%]",
        suffix="Weekly",
        used_percent=63,
        elapsed_percent=40,
        ratio=1.575,
        variants=(
            MonitorColumnVariant(
                label="    usage/time [used]",
                value="63% / 40% = 1.6 [%]",
            ),
            MonitorColumnVariant(
                label="    time/usage [left]",
                value="20.2 / 2.4 = 8.6 [Burst]",
            ),
        ),
    )
    used_context = MonitorRenderContext(row_indent="")
    left_context = MonitorRenderContext(row_indent="", usage_variant="left")

    assert "usage/time [used]" in row.render_frame(used_context)
    assert "63% / 40% = 1.6 [%]" in row.render_frame(used_context)
    for _ in range(5):
        row.step_animation()
    assert "63% / 40% = 1.6 [%]" in row.render_frame(used_context)
    assert "usage/time [used]" in row.render_frame(used_context)

    assert "time/usage [left]" in row.render_frame(left_context)
    assert "20.2 / 2.4 = 8.6 [Burst]" in row.render_frame(left_context)

def test_monitor_loop_surfaces_config_fingerprint_drift() -> None:
    loop = MonitorLoop(
        workflows=(),
        interval_sec=0,
        max_ticks=1,
        config_fingerprint="old",
        config_fingerprint_loader=lambda: "new",
    )

    loop._check_config_fingerprint()

    setup = loop.state.data["monitor_setup"]
    assert isinstance(setup, dict)
    assert setup["config_stale"] is True
    assert setup["current_config_fingerprint"] == "new"

def test_monitor_loop_usage_variant_toggle_alarm_changes_display_only() -> None:
    loop = MonitorLoop(workflows=(), interval_sec=0, max_ticks=1)
    assert loop.state.data["monitor_display"] == {"usage_variant": "used"}
    row = MonitorUsageTimeRow(
        label="    usage/time [used]",
        value="63% / 40% = 1.6 [%]",
        suffix="Weekly",
        used_percent=63,
        elapsed_percent=40,
        ratio=1.575,
        variants=(
            MonitorColumnVariant(
                label="    usage/time [used]",
                value="63% / 40% = 1.6 [%]",
            ),
            MonitorColumnVariant(
                label="    time/usage [left]",
                value="20.2 / 2.4 = 8.6 [Burst]",
            ),
        ),
    )
    loop.visible_frame.add_block("limits-tracking", rows=[row])
    loop.clock.set_one_shot(MONITOR_USAGE_VARIANT_TOGGLE_ALARM, remaining_ticks=0)
    snapshot = loop.clock.step()

    loop._apply_display_alarms(snapshot)

    assert loop.state.data["monitor_display"] == {"usage_variant": "left"}
    assert "time/usage [left]" in format_monitor_frame(
        loop.visible_frame, loop.state
    )
    refreshed_frame = MonitorFrame()
    refreshed_frame.add_block("limits-tracking", rows=[row])
    assert "time/usage [left]" in format_monitor_frame(refreshed_frame, loop.state)
    assert MONITOR_USAGE_VARIANT_TOGGLE_ALARM not in _workflow_alarm_names(
        snapshot.fired_alarm_names
    )

    loop.clock.set_one_shot(MONITOR_USAGE_VARIANT_TOGGLE_ALARM, remaining_ticks=0)
    snapshot = loop.clock.step()

    loop._apply_display_alarms(snapshot)

    assert loop.state.data["monitor_display"] == {"usage_variant": "used"}
    assert "usage/time [used]" in format_monitor_frame(loop.visible_frame, loop.state)

def test_monitor_result_payload_exposes_top_rows_and_heading_rows() -> None:
    frame = MonitorFrame()
    frame.add_top_row(MonitorTextRow("Agent accounts monitor", indent=False))
    frame.add_top_row(MonitorMarqueeRow("Enter refresh | r toggle used/left | m materialize"))
    frame.add_block("limits-tracking", rows=[MonitorTextRow("hello")])
    payload = monitor_result_payload(frame, MonitorState())

    top_rows = payload["frame"]["top_rows"]  # type: ignore[index]
    block = payload["frame"]["blocks"][0]  # type: ignore[index]
    assert top_rows[0]["text"] == "Agent accounts monitor"
    assert top_rows[1]["kind"] == "marquee"
    assert block["heading_rows"][0]["text"] == "limits-tracking"
    assert block["title"] == "limits-tracking"
    assert "lines" not in block


def test_monitor_render_uses_canonical_block_order_after_materialize_priority() -> None:
    frame = MonitorFrame()
    frame.add_block("account-rotation", rows=[MonitorTextRow("rotations")])
    frame.add_block("account-materialize", rows=[MonitorTextRow("done")])
    frame.add_block(
        "limits-tracking | next in 168 ticks | reset 2 ticks ago",
        rows=[MonitorTextRow("limits")],
        data={"workflow": "limits-tracking"},
    )

    rendered = format_monitor_frame(frame)
    payload = monitor_result_payload(frame, MonitorState())
    payload_titles = [
        block["title"] for block in payload["frame"]["blocks"]  # type: ignore[index]
    ]

    assert rendered.index("limits-tracking") < rendered.index("account-rotation")
    assert rendered.index("account-rotation") < rendered.index("account-materialize")
    assert payload_titles == [
        "limits-tracking | next in 168 ticks | reset 2 ticks ago",
        "account-rotation",
        "account-materialize",
    ]


def test_monitor_frame_inherits_marquee_animation_state() -> None:
    first = MonitorFrame()
    first.add_top_row(MonitorMarqueeRow("Enter refresh | r toggle used/left | m materialize"))
    first.step_animations()
    second = MonitorFrame()
    second.add_top_row(MonitorMarqueeRow("Enter refresh | r toggle used/left | m materialize"))

    second.inherit_animation_state_from(first)

    marquee = second.top_rows[0]
    assert isinstance(marquee, MonitorMarqueeRow)
    assert marquee.animation_tick == 1

def test_monitor_loop_prepares_top_rows_with_shortcuts_and_waiting_status() -> None:
    loop = MonitorLoop(workflows=(), interval_sec=0, max_ticks=1)

    loop._prepare_visible_frame_for_render()

    texts = [row.text for row in loop.visible_frame.top_rows]
    assert texts[:3] == [
        "Agent accounts monitor",
        "Tick: 0",
        "Enter refresh | r toggle used/left | m materialize",
    ]
    assert texts[-1] == "waiting for workflow frame"

def test_monitor_loop_prepares_materialize_requested_top_row() -> None:
    loop = MonitorLoop(workflows=(), interval_sec=0, max_ticks=1)

    loop.set_alarm(MONITOR_MATERIALIZE_ALARM)
    loop._prepare_visible_frame_for_render()

    texts = [row.text for row in loop.visible_frame.top_rows]
    assert "materialize: requested" in texts

def test_monitor_loop_prepares_materialize_queued_top_row() -> None:
    loop = MonitorLoop(workflows=(), interval_sec=0, max_ticks=1)
    loop.set_alarm(MONITOR_MATERIALIZE_ALARM)
    snapshot = MonitorClockSnapshot(
        tick=1,
        alarms={},
        fired_alarm_names=(MONITOR_MATERIALIZE_ALARM,),
    )

    loop._queue_workflow_snapshot(snapshot)
    loop._prepare_visible_frame_for_render()

    texts = [row.text for row in loop.visible_frame.top_rows]
    assert "materialize: requested" not in texts
    assert "materialize: queued" in texts

def test_monitor_marquee_renders_single_line_viewport() -> None:
    frame = MonitorFrame()
    frame.add_top_row(MonitorMarqueeRow("Enter refresh | r toggle used/left | m materialize"))

    rendered = format_monitor_frame(frame, width=20)

    lines = rendered.splitlines()
    assert len(lines) == 1
    assert len(lines[0]) <= 20

def test_monitor_loop_usage_variant_toggle_alarm_does_not_hide_workflow_alarms() -> None:
    assert _workflow_alarm_names(
        (MONITOR_USAGE_VARIANT_TOGGLE_ALARM, LIMITS_TRACKING_PERIODIC_ALARM)
    ) == (LIMITS_TRACKING_PERIODIC_ALARM,)
    assert _workflow_alarm_names(
        (MONITOR_USAGE_VARIANT_TOGGLE_ALARM, MONITOR_MATERIALIZE_ALARM)
    ) == (MONITOR_MATERIALIZE_ALARM,)

def test_monitor_loop_merges_pending_workflow_alarm_names() -> None:
    loop = MonitorLoop(workflows=(), interval_sec=0, max_ticks=1)
    first = MonitorClockSnapshot(
        tick=2,
        alarms={},
        fired_alarm_names=(MONITOR_MATERIALIZE_ALARM,),
    )
    second = MonitorClockSnapshot(
        tick=3,
        alarms={},
        fired_alarm_names=(ACCOUNT_ROTATION_PERIODIC_ALARM,),
    )

    loop._queue_workflow_snapshot(first)
    loop._queue_workflow_snapshot(second)
    merged = loop._take_workflow_snapshot()

    assert merged is not None
    assert merged.tick == 3
    assert merged.fired_alarm_names == (
        MONITOR_MATERIALIZE_ALARM,
        ACCOUNT_ROTATION_PERIODIC_ALARM,
    )

def test_monitor_loop_prioritizes_account_rotation_for_materialize_alarm() -> None:
    class Workflow:
        def __init__(self, name: str, priority: int = 100) -> None:
            self.name = name
            self._priority = priority

        def priority_for_snapshot(self, snapshot: MonitorClockSnapshot) -> int:
            return self._priority

    limits = Workflow("limits-tracking")
    rotation = Workflow("not-hard-coded-by-name", priority=0)
    snapshot = MonitorClockSnapshot(
        tick=1,
        alarms={},
        fired_alarm_names=(MONITOR_MATERIALIZE_ALARM, LIMITS_TRACKING_PERIODIC_ALARM),
    )

    ordered = _workflows_for_snapshot((limits, rotation), snapshot)

    assert ordered == (rotation, limits)

def test_monitor_loop_titles_include_ticks_since_reset_for_periodic_workflows() -> None:
    loop = MonitorLoop(workflows=(), interval_sec=0, max_ticks=1)
    loop.visible_frame.add_block(
        "limits-tracking",
        data={
            "workflow": "limits-tracking",
            "periodic_alarm_name": "limits-tracking.periodic",
        },
    )
    loop.visible_frame.add_block(
        "auto-prime-zero-limits",
        data={
            "workflow": "auto-prime-zero-limits",
            "periodic_alarm_name": "auto-prime-zero-limits.periodic",
        },
    )
    loop.clock.set_periodic(
        "limits-tracking.periodic",
        period_ticks=170,
        remaining_ticks=168,
    )
    loop.clock.set_periodic(
        "auto-prime-zero-limits.periodic",
        period_ticks=8,
        remaining_ticks=8,
    )
    loop._clock_snapshot = loop.clock.snapshot()

    loop._apply_clock_feedback_to_visible_frame()

    assert loop.visible_frame.blocks[0].title == (
        "limits-tracking | next in 168 ticks | reset 2 ticks ago"
    )
    assert loop.visible_frame.blocks[1].title == (
        "auto-prime-zero-limits | next in 8 ticks | reset 0 ticks ago"
    )
