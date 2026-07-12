"""Account-rotation workflow: periodic capture+rotate sweeps and drift reporting."""

from __future__ import annotations

from agentos.agent.monitor.clock import (
    ACCOUNT_ROTATION_PERIODIC_ALARM,
    MONITOR_ENTER_ALARM,
    MONITOR_MATERIALIZE_ALARM,
    MONITOR_STARTUP_ALARM,
    MonitorClockSnapshot,
)
from agentos.agent.monitor.models import MonitorFrame, MonitorState


ACCOUNT_ROTATION_WORKFLOW = "account-rotation"


class AccountRotationWorkflow:
    """Periodic capture+rotate sweep — registry-only, never writes a home.

    On its periodic alarm (or startup/enter) it sweeps every provider and records
    the rotations that changed the active pointer into a small in-state ring; every
    loop pass it rewrites the `account-rotation` block from that ring (so an
    `m`-triggered materialize sweep surfaces on the next tick). Home writes belong
    only to the `m` keystroke, not here.
    """

    name = ACCOUNT_ROTATION_WORKFLOW
    periodic_alarm_name = ACCOUNT_ROTATION_PERIODIC_ALARM
    refresh_interval_sec = 60.0

    def setup(self, state: MonitorState, frame: MonitorFrame) -> None:
        self._write_block(state, frame)

    def loop(
        self, state: MonitorState, frame: MonitorFrame, trigger: MonitorClockSnapshot
    ) -> None:
        from agentos.agent.monitor.account_rotation import (
            materialize_sweep,
            sweep_rotations,
        )

        should_sweep = bool(
            {MONITOR_STARTUP_ALARM, MONITOR_ENTER_ALARM, ACCOUNT_ROTATION_PERIODIC_ALARM}
            .intersection(trigger.fired_alarm_names)
        )
        if should_sweep:
            sweep_rotations(materialize=False)
        if trigger.fired(MONITOR_MATERIALIZE_ALARM):
            state.data["account_materialize"] = {
                "tick": trigger.tick,
                "status": "running",
            }
            results = materialize_sweep()
            from agentos.agent.monitor.account_rotation import materialize_summary_payload

            state.data["account_materialize"] = materialize_summary_payload(
                results,
                tick=trigger.tick,
            )
        self._write_block(state, frame)

    def _write_block(self, state: MonitorState, frame: MonitorFrame) -> None:
        from agentos.agent.accounts_log import read_recent_events
        from agentos.agent.monitor.account_rotation import (
            collect_non_aligned_homes,
            materialize_status_block_rows,
            non_aligned_block_rows,
            rotation_block_rows,
        )

        frame.add_block(
            self.name,
            rows=rotation_block_rows(read_recent_events(event="rotate", limit=5)),
            data={
                "workflow": self.name,
                "periodic_alarm_name": ACCOUNT_ROTATION_PERIODIC_ALARM,
                "refresh_interval_sec": self.refresh_interval_sec,
            },
        )
        # Current drifted homes — a second, read-only block shown only when drift exists.
        drifted = collect_non_aligned_homes()
        if drifted:
            frame.add_block(
                "non-aligned homes",
                rows=non_aligned_block_rows(drifted),
                data={"workflow": self.name, "count": len(drifted)},
            )
        materialize_summary = state.data.get("account_materialize")
        if isinstance(materialize_summary, dict):
            frame.add_block(
                "account-materialize",
                rows=materialize_status_block_rows(materialize_summary),
                data={"workflow": self.name, **materialize_summary},
            )
