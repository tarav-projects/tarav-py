# $kw: ^agentos-daemon-runtime --from Agentos.Daemon --from Agentos.Hook --note [DC] local socket acceptance feeds one in-memory serial worker lane for registered daemon callbacks --supp ^c20260725-101u ^c20260725-106u ^c20260811-50u
from __future__ import annotations

import json
import os
import queue
import socketserver
import stat
import threading
from pathlib import Path

from agentos._core.project import agentos_home_dir
from agentos.hooks import HookRegistry

from .client import daemon_status
from .log import append_daemon_log
from .model import DaemonHookEvent, DaemonProtocolError, daemon_socket_path


MAX_DAEMON_REQUEST_BYTES = 8 * 1024 * 1024


class DaemonRuntimeError(RuntimeError):
    """The daemon runtime could not establish or maintain its local service."""


class _ThreadingUnixServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True

    def __init__(
        self,
        server_address: str,
        runtime: DaemonRuntime,
    ) -> None:
        self.runtime = runtime
        super().__init__(server_address, _DaemonRequestHandler)


class _DaemonRequestHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        runtime: DaemonRuntime = self.server.runtime  # type: ignore[attr-defined]
        raw = self.rfile.readline(MAX_DAEMON_REQUEST_BYTES + 1)
        if len(raw) > MAX_DAEMON_REQUEST_BYTES:
            self._respond({"status": "error", "error": "request-too-large"})
            return
        try:
            payload = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._respond({"status": "error", "error": "invalid-json"})
            return
        if not isinstance(payload, dict) or payload.get("schema_version") != 1:
            self._respond({"status": "error", "error": "invalid-request"})
            return
        request_type = payload.get("type")
        if request_type == "daemon.ping":
            self._respond({"status": "running", "pid": os.getpid()})
            return
        if request_type == "daemon.stop":
            self._respond({"status": "stopping", "pid": os.getpid()})
            threading.Thread(target=runtime.stop, daemon=True).start()
            return
        try:
            event = DaemonHookEvent.from_request(payload)
        except (DaemonProtocolError, ValueError):
            self._respond({"status": "error", "error": "invalid-hook-event"})
            return
        runtime.accept(event)
        self._respond({"status": "accepted", "event_id": event.event_id})

    def _respond(self, payload: dict[str, object]) -> None:
        self.wfile.write(
            (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
        )
        self.wfile.flush()


class DaemonRuntime:
    def __init__(
        self,
        registry: HookRegistry,
        *,
        socket_path: Path | None = None,
    ) -> None:
        self.registry = registry
        self.socket_path = (socket_path or daemon_socket_path()).expanduser().resolve()
        self._events: queue.Queue[DaemonHookEvent | None] = queue.Queue()
        self._server: _ThreadingUnixServer | None = None
        self._worker: threading.Thread | None = None

    def serve_forever(self, *, ready_event: threading.Event | None = None) -> None:
        self._prepare_socket_path()
        server = _ThreadingUnixServer(str(self.socket_path), self)
        try:
            os.chmod(self.socket_path, 0o600)
        except OSError:
            server.server_close()
            self._remove_owned_socket()
            raise
        self._server = server
        self._worker = threading.Thread(
            target=self._worker_loop,
            name="agentos-daemon-worker",
            daemon=True,
        )
        self._worker.start()
        append_daemon_log("daemon_started")
        if ready_event is not None:
            ready_event.set()
        try:
            server.serve_forever(poll_interval=0.05)
        finally:
            server.server_close()
            self._events.put(None)
            self._worker.join()
            self._worker = None
            self._server = None
            self._remove_owned_socket()
            append_daemon_log("daemon_stopped")

    def accept(self, event: DaemonHookEvent) -> None:
        append_daemon_log(
            "hook_accepted",
            event_id=event.event_id,
            invocation=event.invocation,
        )
        self._events.put_nowait(event)

    def stop(self) -> None:
        server = self._server
        if server is not None:
            server.shutdown()

    def _worker_loop(self) -> None:
        while True:
            event = self._events.get()
            try:
                if event is None:
                    return
                append_daemon_log(
                    "hook_dispatch_started",
                    event_id=event.event_id,
                    invocation=event.invocation,
                )
                self.registry.dispatch(
                    event.invocation,
                    execution="daemon",
                    failure_reporter=lambda invocation, callback_id, error: (
                        append_daemon_log(
                            "hook_consumer_failed",
                            event_id=event.event_id,
                            invocation=invocation,
                            callback_id=callback_id,
                            error=error,
                        )
                    ),
                )
                append_daemon_log(
                    "hook_dispatch_completed",
                    event_id=event.event_id,
                    invocation=event.invocation,
                )
            finally:
                self._events.task_done()

    def _prepare_socket_path(self) -> None:
        parent = self.socket_path.parent
        parent.mkdir(parents=True, exist_ok=True)
        daemon_root = agentos_home_dir() / "daemon"
        if parent == daemon_root or parent.is_relative_to(daemon_root):
            os.chmod(parent, 0o700)
        if not self.socket_path.exists():
            return
        try:
            mode = self.socket_path.stat().st_mode
        except OSError as exc:
            raise DaemonRuntimeError("cannot inspect existing daemon socket") from exc
        if not stat.S_ISSOCK(mode):
            raise DaemonRuntimeError("daemon socket path exists and is not a socket")
        if daemon_status(socket_path=self.socket_path) is not None:
            raise DaemonRuntimeError("Agentos daemon is already running")
        self.socket_path.unlink()

    def _remove_owned_socket(self) -> None:
        try:
            if self.socket_path.exists() and stat.S_ISSOCK(
                self.socket_path.stat().st_mode
            ):
                self.socket_path.unlink()
        except OSError:
            pass


__all__ = ["DaemonRuntime", "DaemonRuntimeError"]
