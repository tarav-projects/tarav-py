from __future__ import annotations

import os
import pty
from pathlib import Path
from types import SimpleNamespace

import pytest

from tarav.l1.agent.account_status import AccountStatusError
from tarav.l1.agent.providers.claude_code import account_status


def _stub_agent(home: Path) -> SimpleNamespace:
    command = SimpleNamespace(argv=("claude",), env_overrides={})
    return SimpleNamespace(
        provider="claude-code",
        account=None,
        home=home,
        _build_command=lambda _config: command,
    )


@pytest.mark.parametrize(
    ("spawn_error", "error_type"),
    [
        (OSError(8, "Exec format error"), "command_failed"),
        (FileNotFoundError(2, "No such file or directory"), "command_not_found"),
    ],
)
def test_failed_spawn_closes_pty_fds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    spawn_error: OSError,
    error_type: str,
) -> None:
    monkeypatch.setenv("TARAV_HOME", str(tmp_path / "tarav-home"))
    opened: list[int] = []
    real_openpty = pty.openpty

    def recording_openpty() -> tuple[int, int]:
        fds = real_openpty()
        opened.extend(fds)
        return fds

    def failing_popen(*_args: object, **_kwargs: object) -> None:
        raise spawn_error

    monkeypatch.setattr(account_status.pty, "openpty", recording_openpty)
    monkeypatch.setattr(account_status.subprocess, "Popen", failing_popen)

    with pytest.raises(AccountStatusError) as exc_info:
        account_status._run_claude_statusline_refresh_session(
            _stub_agent(tmp_path / "home"),
            cwd=tmp_path,
            capture_path=tmp_path / "capture.json",
            settings_path=tmp_path / "settings.json",
            timeout_sec=1,
        )

    assert exc_info.value.error_type == error_type
    assert len(opened) == 2
    for fd in opened:
        with pytest.raises(OSError):
            os.fstat(fd)
