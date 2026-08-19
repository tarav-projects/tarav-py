# $kw: --from Account.Management
"""Account-rotation workflow: periodic capture+rotate sweeps and drift reporting."""

from __future__ import annotations

from tarav.agent.monitor.clock import (
    ACCOUNT_ROTATION_PERIODIC_ALARM,
    MONITOR_AUTO_MATERIALIZE_TOGGLE_ALARM,
    MONITOR_ENTER_ALARM,
    MONITOR_MATERIALIZE_ALARM,
    MONITOR_STARTUP_ALARM,
    MonitorClockSnapshot,
)
from tarav.agent.monitor.models import (
    ACCOUNT_ROTATION_WORKFLOW,
    MonitorFrame,
    MonitorState,
)


class AccountRotationWorkflow:
    """Periodic capture+rotate sweep, materializing homes unless in manual-only mode.

    On its periodic alarm (or startup/enter) it sweeps every provider; in the
    default ``auto_materialize`` mode that sweep also reconciles drifted homes,
    which is what the old `m`-only policy deliberately withheld. Manual-only mode
    restores that policy: the tick stays registry-only and `m` remains the sole
    home write. The mode is session state — it starts from config and flips on the
    toggle alarm, so it never outlives the monitor process.
    """

    name = ACCOUNT_ROTATION_WORKFLOW
    periodic_alarm_name = ACCOUNT_ROTATION_PERIODIC_ALARM

    def __init__(
        self,
        *,
        auto_materialize: bool = True,
        refresh_interval_sec: float = 60.0,
    ) -> None:
        self.auto_materialize = auto_materialize
        self.refresh_interval_sec = refresh_interval_sec

    def priority_for_snapshot(self, snapshot: MonitorClockSnapshot) -> int:
        if snapshot.fired(MONITOR_MATERIALIZE_ALARM):
            return 0
        return 100

    def setup(self, state: MonitorState, frame: MonitorFrame) -> None:
        self._write_block(state, frame)

    def loop(
        self, state: MonitorState, frame: MonitorFrame, trigger: MonitorClockSnapshot
    ) -> None:
        from tarav.agent.monitor.account_rotation import (
            MATERIALIZE_STATUS_RUNNING,
            materialize_summary_payload,
            set_materialize_state,
            set_materialize_summary,
            sweep_rotations,
        )

        if trigger.fired(MONITOR_AUTO_MATERIALIZE_TOGGLE_ALARM):
            self.auto_materialize = not self.auto_materialize
        should_sweep = bool(
            {MONITOR_STARTUP_ALARM, MONITOR_ENTER_ALARM, ACCOUNT_ROTATION_PERIODIC_ALARM}
            .intersection(trigger.fired_alarm_names)
        )
        pressed = trigger.fired(MONITOR_MATERIALIZE_ALARM)
        if should_sweep or pressed:
            materialize = pressed or self.auto_materialize
            if materialize:
                set_materialize_state(
                    state.data,
                    tick=trigger.tick,
                    status=MATERIALIZE_STATUS_RUNNING,
                )
            results = sweep_rotations(materialize=materialize)
            if materialize:
                set_materialize_summary(
                    state.data,
                    materialize_summary_payload(
                        results,
                        tick=trigger.tick,
                    ),
                )
        self._write_block(state, frame)

    def _write_block(self, state: MonitorState, frame: MonitorFrame) -> None:
        from tarav.agent.accounts_log import read_recent_events
        from tarav.agent.monitor.account_rotation import (
            ACCOUNT_MATERIALIZE_BLOCK_TITLE,
            collect_non_aligned_homes,
            materialize_state_payload,
            materialize_status_block_rows,
            non_aligned_block_rows,
            rotation_block_rows,
        )

        frame.add_block(
            self.name,
            rows=rotation_block_rows(
                read_recent_events(event="rotate", limit=5),
                auto_materialize=self.auto_materialize,
            ),
            data={
                "workflow": self.name,
                "periodic_alarm_name": ACCOUNT_ROTATION_PERIODIC_ALARM,
                "refresh_interval_sec": self.refresh_interval_sec,
                "auto_materialize": self.auto_materialize,
            },
        )

        drifted = collect_non_aligned_homes()
        if drifted:
            frame.add_block(
                "non-aligned homes",
                rows=non_aligned_block_rows(drifted),
                data={"workflow": self.name, "count": len(drifted)},
            )
        materialize_summary = materialize_state_payload(state.data)
        if materialize_summary is not None:
            frame.add_block(
                ACCOUNT_MATERIALIZE_BLOCK_TITLE,
                rows=materialize_status_block_rows(materialize_summary),
                data={"workflow": self.name, **materialize_summary},
            )
