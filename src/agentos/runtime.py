from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from agentos.chatlas.hook_consumers import register_chatlas_hook_callbacks
from agentos.codex.usage_hooks import register_codex_usage_hook_callbacks
from agentos.hooks import HookRegistry, register_hook_sampling_callbacks


HookRegistrar = Callable[[HookRegistry], None]


@dataclass(frozen=True, slots=True)
class AgentosRuntime:
    """One composed in-process Agentos runtime."""

    hooks: HookRegistry


def create_runtime(
    *,
    hook_registrars: Sequence[HookRegistrar] = (),
) -> AgentosRuntime:
    registry = HookRegistry()
    register_hook_sampling_callbacks(registry)
    register_codex_usage_hook_callbacks(registry)
    register_chatlas_hook_callbacks(registry)
    for registrar in hook_registrars:
        registrar(registry)
    return AgentosRuntime(hooks=registry)


__all__ = ["AgentosRuntime", "HookRegistrar", "create_runtime"]
