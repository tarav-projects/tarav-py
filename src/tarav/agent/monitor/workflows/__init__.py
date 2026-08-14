# $kw: --from Account.Management
"""Monitor workflows package.

Submodule ownership:
- ``limits_tracking``: usage refresh, transition/error logging, limit row rendering.
- ``auto_prime``: trigger detection, eligibility, prime pings, and status parts.
- ``account_rotation``: periodic capture+rotate sweeps and drift reporting.
- ``builder``: assembly of configured workflows, including multi-config merging.
- ``_common``: shared value parsing, formatting, and target-key helpers.
"""

from tarav.agent.monitor.workflows.account_rotation import (
    ACCOUNT_ROTATION_WORKFLOW,
    AccountRotationWorkflow,
)
from tarav.agent.monitor.workflows.auto_prime import AutoPrimeZeroLimitsWorkflow
from tarav.agent.monitor.workflows.builder import build_monitor_workflows
from tarav.agent.monitor.workflows.limits_tracking import LimitsTrackingWorkflow

__all__ = [
    "ACCOUNT_ROTATION_WORKFLOW",
    "AccountRotationWorkflow",
    "AutoPrimeZeroLimitsWorkflow",
    "LimitsTrackingWorkflow",
    "build_monitor_workflows",
]
