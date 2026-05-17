from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Literal


MonitorAlarmKind = Literal["one-shot", "periodic"]


@dataclass
class _MonitorAlarm:
    name: str
    kind: MonitorAlarmKind
    remaining_ticks: int
    period_ticks: int | None = None
    armed: bool = True


@dataclass(frozen=True)
class MonitorAlarmSnapshot:
    name: str
    kind: MonitorAlarmKind
    remaining_ticks: int
    period_ticks: int | None
    armed: bool
    fired: bool


@dataclass(frozen=True)
class MonitorClockSnapshot:
    tick: int
    alarms: dict[str, MonitorAlarmSnapshot]
    fired_alarm_names: tuple[str, ...]

    def fired(self, name: str) -> bool:
        return name in self.fired_alarm_names


class MonitorClock:
    def __init__(self) -> None:
        self._tick = 0
        self._alarms: dict[str, _MonitorAlarm] = {}
        self._lock = Lock()

    @property
    def tick(self) -> int:
        with self._lock:
            return self._tick

    def set_one_shot(self, name: str, *, remaining_ticks: int = 0) -> None:
        with self._lock:
            self._alarms[name] = _MonitorAlarm(
                name=name,
                kind="one-shot",
                remaining_ticks=max(0, remaining_ticks),
            )

    def set_periodic(
        self,
        name: str,
        *,
        period_ticks: int,
        remaining_ticks: int | None = None,
    ) -> None:
        period_ticks = max(1, period_ticks)
        with self._lock:
            self._alarms[name] = _MonitorAlarm(
                name=name,
                kind="periodic",
                remaining_ticks=max(
                    0, period_ticks if remaining_ticks is None else remaining_ticks
                ),
                period_ticks=period_ticks,
            )

    def snapshot(self) -> MonitorClockSnapshot:
        with self._lock:
            return self._snapshot_locked(fired_alarm_names=())

    def step(self) -> MonitorClockSnapshot:
        with self._lock:
            self._tick += 1
            fired_alarm_names: list[str] = []
            for alarm in self._alarms.values():
                if not alarm.armed:
                    continue
                if alarm.remaining_ticks > 0:
                    alarm.remaining_ticks -= 1
                if alarm.remaining_ticks > 0:
                    continue
                fired_alarm_names.append(alarm.name)
                if alarm.kind == "periodic":
                    alarm.remaining_ticks = alarm.period_ticks or 1
                else:
                    alarm.armed = False
            return self._snapshot_locked(fired_alarm_names=tuple(fired_alarm_names))

    def _snapshot_locked(
        self, *, fired_alarm_names: tuple[str, ...]
    ) -> MonitorClockSnapshot:
        fired = set(fired_alarm_names)
        return MonitorClockSnapshot(
            tick=self._tick,
            alarms={
                name: MonitorAlarmSnapshot(
                    name=alarm.name,
                    kind=alarm.kind,
                    remaining_ticks=alarm.remaining_ticks,
                    period_ticks=alarm.period_ticks,
                    armed=alarm.armed,
                    fired=name in fired,
                )
                for name, alarm in self._alarms.items()
            },
            fired_alarm_names=fired_alarm_names,
        )
