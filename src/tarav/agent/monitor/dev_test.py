# $kw: --from Account.Management
"""Dev-only render candidates for the account monitor.

A sandbox for eyeballing monitor row rendering — overflow bars, markers, and any
other communication snippet we want to see without a live provider. Rendered by
`tarav accounts monitor dev-test`; nothing here runs in the live loop. Add new
candidate rows as we design new monitor communication.
"""

from __future__ import annotations

from tarav.agent.monitor.models import (
    MonitorFrame,
    MonitorTextRow,
    MonitorUsageTimeRow,
)
from tarav.agent.monitor.workflows.limits_tracking import (
    _usage_time_ratio,
    _usage_time_value,
)


def _usage_candidate(
    suffix: str, *, used_percent: int, elapsed_percent: int
) -> MonitorUsageTimeRow:
    """A usage/time row built through the production formatters.

    ``used_percent`` is passed through uncapped (floored at 0) so overflow
    candidates exercise the same saturate-bar / truthful-number / boundary
    marker path the real usage rows use.
    """
    ratio = _usage_time_ratio(used_percent, elapsed_percent)
    return MonitorUsageTimeRow(
        label="    usage/time",
        value=_usage_time_value(
            used_percent=used_percent,
            elapsed_percent=elapsed_percent,
            ratio=ratio,
        ),
        suffix=suffix,
        used_percent=max(0, used_percent),
        elapsed_percent=max(0, min(100, elapsed_percent)),
        ratio=ratio,
    )


def build_dev_test_frame() -> MonitorFrame:
    """Candidate rows for visual review of the usage-bar rendering."""
    frame = MonitorFrame()
    frame.add_block(
        title="dev-test · usage bar candidates",
        rows=[
            MonitorTextRow("normal fill (bar tracks the number)"),
            _usage_candidate("Burst   0%", used_percent=0, elapsed_percent=20),
            _usage_candidate("Burst  45%", used_percent=45, elapsed_percent=50),
            _usage_candidate("Burst  99%", used_percent=99, elapsed_percent=90),
            _usage_candidate("Burst 100%", used_percent=100, elapsed_percent=100),
            MonitorTextRow(""),
            MonitorTextRow("overflow (bar saturates, 100% line marker, true %)"),
            _usage_candidate("Burst 126%", used_percent=126, elapsed_percent=40),
            _usage_candidate("Burst 180%", used_percent=180, elapsed_percent=60),
            _usage_candidate("Burst 250%", used_percent=250, elapsed_percent=30),
        ],
    )
    return frame
