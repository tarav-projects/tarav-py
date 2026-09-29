from __future__ import annotations

from pathlib import Path

import pytest

from tarav.l0.testing import TaravTestEnvironment


def test_build_monitor_loop_runs_with_no_workflow_configs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The always-on account-rotation workflow makes the monitor runnable even
    when no limits-tracking (or other) workflow is configured."""
    TaravTestEnvironment.create(tmp_path).apply_environment(monkeypatch.setenv)
    from tarav.l1.agent.monitor.config import build_monitor_loop

    loop = build_monitor_loop(start_path=tmp_path, interval_sec=1.0, max_ticks=1)

    assert "account-rotation" in [w.name for w in loop.workflows]
