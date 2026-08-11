# $kw: ^agentos-hook-invocation-model --from Agentos.Hook.Invocation --note [DF] validated provider-neutral hook envelope carrying an exact name, optional context type, and opaque JSON object --supp ^c20260811-12u
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass


class HookError(ValueError):
    """The hook contract was given an invalid value."""


def validate_hook_name(name: str) -> str:
    if not isinstance(name, str):
        raise HookError("hook name must be a string")
    parts = name.split(".")
    if len(parts) < 2 or any(
        not part or part != part.strip() or any(char.isspace() for char in part)
        for part in parts
    ):
        raise HookError("hook name must be a nonempty dot-separated namespace")
    return name


@dataclass(frozen=True)
class HookInvocation:
    name: str
    ctx: dict[str, object]
    ctx_type: str | None = None

    def __post_init__(self) -> None:
        validate_hook_name(self.name)
        if not isinstance(self.ctx, dict):
            raise HookError("hook context must be a JSON object")
        if self.ctx_type is not None:
            if not isinstance(self.ctx_type, str) or not self.ctx_type.strip():
                raise HookError("hook context type must be a nonempty string")

    def isolated_copy(self) -> HookInvocation:
        return HookInvocation(
            name=self.name,
            ctx=deepcopy(self.ctx),
            ctx_type=self.ctx_type,
        )


__all__ = ["HookError", "HookInvocation", "validate_hook_name"]
