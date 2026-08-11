# $kw: ^agentos-daemon-launchd --from Agentos.Daemon --note [DC] one owned user LaunchAgent supplies login startup and abnormal-exit recovery for the existing foreground daemon runtime --supp ^c20260725-108u ^c20260725-106u ^c20260811-52u
from __future__ import annotations

from collections.abc import Callable
import os
from pathlib import Path
import plistlib
import subprocess
import tempfile
from typing import Any, TypeAlias

from agentos._core.errors import CliError


LAUNCH_AGENT_LABEL = "org.agentos.daemon"
LaunchctlRunner: TypeAlias = Callable[[list[str]], subprocess.CompletedProcess[str]]


def launch_agent_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT_LABEL}.plist"


def launch_agent_payload(agentos_executable: str) -> dict[str, object]:
    executable = Path(agentos_executable).expanduser()
    if not executable.is_absolute():
        raise CliError("LaunchAgent requires an absolute agentos executable path")
    return {
        "Label": LAUNCH_AGENT_LABEL,
        "ProgramArguments": [str(executable), "daemon", "run"],
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False},
        "ProcessType": "Background",
        "ThrottleInterval": 10,
    }


def launch_agent_status(
    *,
    plist_path: Path | None = None,
    run_command: LaunchctlRunner | None = None,
    uid: int | None = None,
) -> dict[str, object]:
    path = plist_path or launch_agent_path()
    installed = path.is_file()
    if installed:
        _require_owned_plist(path)
    return {
        "installed": installed,
        "label": LAUNCH_AGENT_LABEL,
        "loaded": _launch_agent_loaded(run_command=run_command, uid=uid),
        "path": str(path),
    }


def install_launch_agent(
    agentos_executable: str,
    *,
    plist_path: Path | None = None,
    run_command: LaunchctlRunner | None = None,
    uid: int | None = None,
) -> dict[str, object]:
    path = plist_path or launch_agent_path()
    desired = plistlib.dumps(
        launch_agent_payload(agentos_executable),
        fmt=plistlib.FMT_XML,
        sort_keys=True,
    )
    current = path.read_bytes() if path.is_file() else None
    if current is not None:
        _require_owned_plist(path)
    loaded = _launch_agent_loaded(run_command=run_command, uid=uid)
    changed = current != desired
    bootstrapped = False
    if changed and loaded:
        _launchctl(
            ["bootout", _service_target(uid)],
            run_command=run_command,
        )
        loaded = False
    if changed:
        _atomic_write(path, desired)
    if not loaded:
        _launchctl(
            ["bootstrap", _domain_target(uid), str(path)],
            run_command=run_command,
        )
        loaded = True
        bootstrapped = True
    return {
        "bootstrapped": bootstrapped,
        "changed": changed,
        "installed": True,
        "label": LAUNCH_AGENT_LABEL,
        "loaded": loaded,
        "path": str(path),
    }


def uninstall_launch_agent(
    *,
    plist_path: Path | None = None,
    run_command: LaunchctlRunner | None = None,
    uid: int | None = None,
) -> dict[str, object]:
    path = plist_path or launch_agent_path()
    installed = path.is_file()
    if installed:
        _require_owned_plist(path)
    loaded = _launch_agent_loaded(run_command=run_command, uid=uid)
    if loaded:
        _launchctl(
            ["bootout", _service_target(uid)],
            run_command=run_command,
        )
    if installed:
        path.unlink()
    return {
        "bootstrapped": False,
        "changed": installed or loaded,
        "installed": False,
        "label": LAUNCH_AGENT_LABEL,
        "loaded": False,
        "path": str(path),
    }


def kickstart_launch_agent(
    *,
    run_command: LaunchctlRunner | None = None,
    uid: int | None = None,
) -> None:
    _launchctl(
        ["kickstart", _service_target(uid)],
        run_command=run_command,
    )


def _launch_agent_loaded(
    *,
    run_command: LaunchctlRunner | None,
    uid: int | None,
) -> bool:
    result = _runner(run_command)(["launchctl", "print", _service_target(uid)])
    return result.returncode == 0


def _launchctl(
    arguments: list[str],
    *,
    run_command: LaunchctlRunner | None,
) -> subprocess.CompletedProcess[str]:
    command = ["launchctl", *arguments]
    result = _runner(run_command)(command)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
        raise CliError(f"launchctl {arguments[0]} failed: {detail}")
    return result


def _runner(run_command: LaunchctlRunner | None) -> LaunchctlRunner:
    return run_command or _run_command


def _run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        check=False,
        text=True,
    )


def _domain_target(uid: int | None) -> str:
    return f"gui/{os.getuid() if uid is None else uid}"


def _service_target(uid: int | None) -> str:
    return f"{_domain_target(uid)}/{LAUNCH_AGENT_LABEL}"


def _require_owned_plist(path: Path) -> dict[str, Any]:
    try:
        payload = plistlib.loads(path.read_bytes())
    except (OSError, plistlib.InvalidFileException) as exc:
        raise CliError(f"LaunchAgent file is not owned by Agentos: {path}") from exc
    if not isinstance(payload, dict) or payload.get("Label") != LAUNCH_AGENT_LABEL:
        raise CliError(f"LaunchAgent file is not owned by Agentos: {path}")
    return payload


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_path, 0o644)
        os.replace(temporary_path, path)
    finally:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass


__all__ = [
    "LAUNCH_AGENT_LABEL",
    "install_launch_agent",
    "kickstart_launch_agent",
    "launch_agent_path",
    "launch_agent_payload",
    "launch_agent_status",
    "uninstall_launch_agent",
]
