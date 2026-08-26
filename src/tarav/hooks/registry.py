# $kw: ^agentos-hook-registry --from Agentos.Hook --note [DC] exact-name callbacks execute sequentially in registration order; failures are logged without context and dispatch continues --supp ^c20260811-5u ^c20260811-6u ^c20260811-7u ^c20260811-9u
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, TypeAlias

from tarav._core.operational_logging import event_extra

from .model import HookError, HookInvocation, validate_hook_name


LOGGER = logging.getLogger(__name__)
HookCallback: TypeAlias = Callable[[HookInvocation], object]
HookFailureReporter: TypeAlias = Callable[[HookInvocation, str, BaseException], object]


@dataclass(frozen=True)
class _RegisteredCallback:
    callback_id: str
    callback: HookCallback


class HookRegistry:
    def __init__(self) -> None:
        self._callbacks: dict[str, list[_RegisteredCallback]] = defaultdict(list)

    def register(
        self,
        name: str,
        callback: HookCallback,
        *,
        callback_id: str | None = None,
    ) -> None:
        validate_hook_name(name)
        if not callable(callback):
            raise HookError("hook callback must be callable")
        resolved_id = callback_id or _callback_id(callback)
        if not resolved_id.strip():
            raise HookError("hook callback id must be a nonempty string")
        self._callbacks[name].append(
            _RegisteredCallback(
                callback_id=resolved_id,
                callback=callback,
            )
        )

    def has_callbacks(self, name: str) -> bool:
        validate_hook_name(name)
        return bool(self._callbacks.get(name))

    def dispatch(
        self,
        invocation: HookInvocation,
        *,
        failure_reporter: HookFailureReporter | None = None,
    ) -> None:
        if not isinstance(invocation, HookInvocation):
            raise HookError("dispatch requires a HookInvocation")
        for registered in tuple(self._callbacks.get(invocation.name, ())):
            try:
                registered.callback(invocation.isolated_copy())
            except Exception as exc:
                LOGGER.error(
                    "hook callback failed: hook=%s callback=%s error_type=%s",
                    invocation.name,
                    registered.callback_id,
                    type(exc).__name__,
                    extra=event_extra(
                        "hooks.callback.failed",
                        hook=invocation.name,
                        callback=registered.callback_id,
                        error_type=type(exc).__name__,
                    ),
                )
                if failure_reporter is not None:
                    try:
                        failure_reporter(
                            invocation.isolated_copy(),
                            registered.callback_id,
                            exc,
                        )
                    except Exception as reporter_exc:
                        LOGGER.error(
                            "hook failure reporter failed: hook=%s callback=%s "
                            "error_type=%s",
                            invocation.name,
                            registered.callback_id,
                            type(reporter_exc).__name__,
                            extra=event_extra(
                                "hooks.failure_reporter.failed",
                                hook=invocation.name,
                                callback=registered.callback_id,
                                error_type=type(reporter_exc).__name__,
                            ),
                        )


def _callback_id(callback: HookCallback) -> str:
    module = getattr(callback, "__module__", callback.__class__.__module__)
    qualname = getattr(callback, "__qualname__", callback.__class__.__qualname__)
    return f"{module}.{qualname}"


__all__ = [
    "HookCallback",
    "HookFailureReporter",
    "HookRegistry",
]
