# $kw: ^agentos-daemon-client --from Agentos.Daemon --from Agentos.Hook.Invocation --note [DC] hook ingress defaults to daemon acceptance while an explicit wait keeps the connection through dispatch completion --supp ^c20260811-50u ^c20260813-27u
from __future__ import annotations

import json
import socket
from pathlib import Path
from typing import Any

from tarav.l1.hooks import HookInvocation

from .model import DaemonHookEvent, daemon_socket_path


DEFAULT_DAEMON_CLIENT_TIMEOUT_SEC = 0.5
MAX_DAEMON_RESPONSE_BYTES = 64 * 1024


class DaemonUnavailableError(RuntimeError):
    def __init__(self, message: str, *, event_id: str | None = None) -> None:
        super().__init__(message)
        self.event_id = event_id


def submit_hook_invocation(
    invocation: HookInvocation,
    *,
    socket_path: Path | None = None,
    timeout: float = DEFAULT_DAEMON_CLIENT_TIMEOUT_SEC,
    wait: bool = False,
) -> str:
    event = DaemonHookEvent.create(invocation)
    try:
        response = _request(
            event.to_request(wait=wait),
            socket_path=socket_path,
            timeout=timeout,
            response_timeout=None if wait else timeout,
        )
    except Exception as exc:
        if isinstance(exc, DaemonUnavailableError):
            raise DaemonUnavailableError(str(exc), event_id=event.event_id) from exc
        raise DaemonUnavailableError(
            "Tarav daemon submission failed",
            event_id=event.event_id,
        ) from exc
    expected_status = "completed" if wait else "accepted"
    if (
        response.get("status") != expected_status
        or response.get("event_id") != event.event_id
    ):
        raise DaemonUnavailableError(
            "Tarav daemon rejected the hook event",
            event_id=event.event_id,
        )
    return event.event_id


def daemon_status(
    *,
    socket_path: Path | None = None,
    timeout: float = DEFAULT_DAEMON_CLIENT_TIMEOUT_SEC,
) -> dict[str, Any] | None:
    try:
        response = _request(
            {"schema_version": 1, "type": "daemon.ping"},
            socket_path=socket_path,
            timeout=timeout,
        )
    except DaemonUnavailableError:
        return None
    return response if response.get("status") == "running" else None


def request_daemon_stop(
    *,
    socket_path: Path | None = None,
    timeout: float = DEFAULT_DAEMON_CLIENT_TIMEOUT_SEC,
) -> bool:
    try:
        response = _request(
            {"schema_version": 1, "type": "daemon.stop"},
            socket_path=socket_path,
            timeout=timeout,
        )
    except DaemonUnavailableError:
        return False
    return response.get("status") == "stopping"


def _request(
    payload: dict[str, object],
    *,
    socket_path: Path | None,
    timeout: float,
    response_timeout: float | None = DEFAULT_DAEMON_CLIENT_TIMEOUT_SEC,
) -> dict[str, Any]:
    path = (socket_path or daemon_socket_path()).expanduser().resolve()
    request = (
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(timeout)
            client.connect(str(path))
            client.sendall(request)
            client.settimeout(response_timeout)
            response = _read_line(client)
    except (OSError, TimeoutError, socket.timeout) as exc:
        raise DaemonUnavailableError("Tarav daemon is unavailable") from exc
    try:
        parsed = json.loads(response)
    except json.JSONDecodeError as exc:
        raise DaemonUnavailableError("Tarav daemon returned invalid JSON") from exc
    if not isinstance(parsed, dict):
        raise DaemonUnavailableError("Tarav daemon returned a non-object response")
    return parsed


def _read_line(client: socket.socket) -> str:
    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = client.recv(4096)
        if not chunk:
            break
        chunks.append(chunk)
        size += len(chunk)
        if size > MAX_DAEMON_RESPONSE_BYTES:
            raise DaemonUnavailableError("Tarav daemon response is too large")
        if b"\n" in chunk:
            break
    raw = b"".join(chunks).split(b"\n", 1)[0]
    if not raw:
        raise DaemonUnavailableError("Tarav daemon closed without a response")
    return raw.decode("utf-8")


__all__ = [
    "DaemonUnavailableError",
    "daemon_status",
    "request_daemon_stop",
    "submit_hook_invocation",
]
