from __future__ import annotations

from tarav.agent.monitor.workflows.state import AutoPrimeTargetState

import datetime





def _target_state() -> AutoPrimeTargetState:
    return AutoPrimeTargetState(
        provider="codex",
        account="jp",
        home="/tmp/codex-jp",
    )

def _limit(
    *,
    used_percent: int,
    now: datetime.datetime,
    limit_id: str = "burst",
    end_offset_mins: int = 300,
    duration_mins: int = 300,
) -> dict[str, object]:
    period_ends_at = now + datetime.timedelta(minutes=end_offset_mins)
    period_started_at = period_ends_at - datetime.timedelta(minutes=duration_mins)
    return {
        "limit_id": limit_id,
        "usage_over_time": {
            "used_percent": used_percent,
            "period_started_at": period_started_at.isoformat(),
            "period_ends_at": period_ends_at.isoformat(),
            "period_duration_mins": duration_mins,
            "resets_at": period_ends_at.isoformat(),
        },
    }
