# $kw: ^agentos-daemon-hook-envelope --from Agentos.Daemon --from Agentos.Hook.Invocation --note [DF] closed local protocol envelope carrying one validated hook invocation to registered daemon consumers --supp ^c20260811-50u
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from tarav.l0._core.project import tarav_home_dir
from tarav.hooks import HookInvocation


DAEMON_PROTOCOL_SCHEMA_VERSION = 1
DAEMON_HOOK_REQUEST_TYPE = "hook.dispatch"


class DaemonProtocolError(ValueError):
    """The local daemon protocol received an invalid message."""


def daemon_socket_path() -> Path:
    configured = os.getenv("TARAV_DAEMON_SOCKET")
    if configured:
        return Path(configured).expanduser().resolve()
    return tarav_home_dir() / "daemon" / "tarav.sock"


@dataclass(frozen=True)
class DaemonHookEvent:
    event_id: str
    invocation: HookInvocation

    @classmethod
    def create(cls, invocation: HookInvocation) -> DaemonHookEvent:
        if not isinstance(invocation, HookInvocation):
            raise DaemonProtocolError("daemon hook event requires a HookInvocation")
        return cls(event_id=uuid4().hex, invocation=invocation.isolated_copy())

    def to_request(self, *, wait: bool = False) -> dict[str, object]:
        return {
            "schema_version": DAEMON_PROTOCOL_SCHEMA_VERSION,
            "type": DAEMON_HOOK_REQUEST_TYPE,
            "event_id": self.event_id,
            "wait": wait,
            "invocation": {
                "name": self.invocation.name,
                "ctx_type": self.invocation.ctx_type,
                "ctx": self.invocation.ctx,
            },
        }

    @classmethod
    def from_request(cls, payload: object) -> DaemonHookEvent:
        if not isinstance(payload, dict):
            raise DaemonProtocolError("daemon request must be an object")
        if payload.get("schema_version") != DAEMON_PROTOCOL_SCHEMA_VERSION:
            raise DaemonProtocolError("unsupported daemon protocol schema")
        if payload.get("type") != DAEMON_HOOK_REQUEST_TYPE:
            raise DaemonProtocolError("daemon request is not a hook dispatch")
        event_id = payload.get("event_id")
        raw_invocation = payload.get("invocation")
        if not isinstance(event_id, str) or not event_id.strip():
            raise DaemonProtocolError("daemon hook event id must be nonempty")
        if not isinstance(raw_invocation, dict):
            raise DaemonProtocolError("daemon hook invocation must be an object")
        name = raw_invocation.get("name")
        ctx = raw_invocation.get("ctx")
        ctx_type = raw_invocation.get("ctx_type")
        if not isinstance(name, str) or not isinstance(ctx, dict):
            raise DaemonProtocolError("daemon hook invocation is malformed")
        if ctx_type is not None and not isinstance(ctx_type, str):
            raise DaemonProtocolError("daemon hook context type must be a string")
        return cls(
            event_id=event_id,
            invocation=HookInvocation(name=name, ctx=ctx, ctx_type=ctx_type),
        )


__all__ = [
    "DAEMON_HOOK_REQUEST_TYPE",
    "DAEMON_PROTOCOL_SCHEMA_VERSION",
    "DaemonHookEvent",
    "DaemonProtocolError",
    "daemon_socket_path",
]
