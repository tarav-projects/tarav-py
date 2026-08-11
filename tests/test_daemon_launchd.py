from __future__ import annotations

from pathlib import Path
import plistlib
import subprocess

import pytest

from agentos._core.errors import CliError
from agentos.daemon.launchd import (
    LAUNCH_AGENT_LABEL,
    LAUNCH_AGENT_THROTTLE_SECONDS,
    install_launch_agent,
    kickstart_launch_agent,
    launch_agent_payload,
    uninstall_launch_agent,
)


class LaunchctlHarness:
    def __init__(self) -> None:
        self.loaded = False
        self.commands: list[list[str]] = []

    def __call__(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        self.commands.append(command)
        action = command[1]
        if action == "print":
            return subprocess.CompletedProcess(
                command,
                0 if self.loaded else 113,
                stdout="service" if self.loaded else "",
                stderr="" if self.loaded else "not found",
            )
        if action == "bootstrap":
            self.loaded = True
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if action == "bootout":
            self.loaded = False
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if action == "kickstart":
            self.loaded = True
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        raise AssertionError(f"unexpected launchctl command: {command}")


def test_launch_agent_payload_starts_at_login_and_restarts_only_failures() -> None:
    payload = launch_agent_payload("/opt/agentos/bin/agentos-daemon")

    assert payload == {
        "KeepAlive": {"SuccessfulExit": False},
        "Label": LAUNCH_AGENT_LABEL,
        "ProcessType": "Background",
        "ProgramArguments": [
            "/opt/agentos/bin/agentos-daemon",
        ],
        "RunAtLoad": True,
        "ThrottleInterval": LAUNCH_AGENT_THROTTLE_SECONDS,
    }


def test_launch_agent_install_is_atomic_and_idempotent(tmp_path: Path) -> None:
    plist_path = tmp_path / "LaunchAgents" / f"{LAUNCH_AGENT_LABEL}.plist"
    launchctl = LaunchctlHarness()

    first = install_launch_agent(
        "/opt/agentos/bin/agentos-daemon",
        plist_path=plist_path,
        run_command=launchctl,
        uid=501,
    )
    first_stat = plist_path.stat()
    second = install_launch_agent(
        "/opt/agentos/bin/agentos-daemon",
        plist_path=plist_path,
        run_command=launchctl,
        uid=501,
    )

    assert first == {
        "bootstrapped": True,
        "changed": True,
        "installed": True,
        "label": LAUNCH_AGENT_LABEL,
        "loaded": True,
        "path": str(plist_path),
    }
    assert second == {**first, "bootstrapped": False, "changed": False}
    assert plist_path.stat().st_mtime_ns == first_stat.st_mtime_ns
    assert plistlib.loads(plist_path.read_bytes()) == launch_agent_payload(
        "/opt/agentos/bin/agentos-daemon"
    )
    assert launchctl.commands == [
        ["launchctl", "print", f"gui/501/{LAUNCH_AGENT_LABEL}"],
        ["launchctl", "bootstrap", "gui/501", str(plist_path)],
        ["launchctl", "print", f"gui/501/{LAUNCH_AGENT_LABEL}"],
    ]


def test_launch_agent_install_refuses_unowned_existing_file(tmp_path: Path) -> None:
    plist_path = tmp_path / f"{LAUNCH_AGENT_LABEL}.plist"
    plist_path.write_bytes(
        plistlib.dumps(
            {
                "Label": "example.unrelated",
                "ProgramArguments": ["/bin/true"],
            }
        )
    )

    with pytest.raises(CliError, match="not owned by Agentos"):
        install_launch_agent(
            "/opt/agentos/bin/agentos-daemon",
            plist_path=plist_path,
            run_command=LaunchctlHarness(),
            uid=501,
        )


def test_launch_agent_uninstall_is_idempotent(tmp_path: Path) -> None:
    plist_path = tmp_path / f"{LAUNCH_AGENT_LABEL}.plist"
    launchctl = LaunchctlHarness()
    install_launch_agent(
        "/opt/agentos/bin/agentos-daemon",
        plist_path=plist_path,
        run_command=launchctl,
        uid=501,
    )

    first = uninstall_launch_agent(
        plist_path=plist_path,
        run_command=launchctl,
        uid=501,
    )
    second = uninstall_launch_agent(
        plist_path=plist_path,
        run_command=launchctl,
        uid=501,
    )

    assert first == {
        "bootstrapped": False,
        "changed": True,
        "installed": False,
        "label": LAUNCH_AGENT_LABEL,
        "loaded": False,
        "path": str(plist_path),
    }
    assert second == {**first, "changed": False}
    assert not plist_path.exists()
    assert [command[1] for command in launchctl.commands].count("bootout") == 1


def test_launch_agent_kickstart_can_force_a_restart() -> None:
    launchctl = LaunchctlHarness()

    kickstart_launch_agent(force=True, run_command=launchctl, uid=501)

    assert launchctl.commands == [
        ["launchctl", "kickstart", "-k", f"gui/501/{LAUNCH_AGENT_LABEL}"]
    ]
