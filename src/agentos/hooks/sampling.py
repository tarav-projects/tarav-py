# $kw: ^agentos-hook-prompt-sampling --from Agentos.Hook --from Agentos.Hook.Invocation --note [DC] prompt-submission contexts enter the existing bounded private provider-hook sample store --supp ^c20260811-5u ^c20260811-12u ^c20260811-25u
from __future__ import annotations

import os
from pathlib import Path

from agentos.agent.usage_report import append_hook_context_sample
from agentos.providers import canonical_provider_spec_for_name

from .model import HookError, HookInvocation
from .registry import HookRegistry


_PROVIDER_HOME_ENV_VARS = {
    "claude-code": "CLAUDE_CONFIG_DIR",
    "codex": "CODEX_HOME",
    "copilot-cli": "COPILOT_HOME",
}


def register_hook_sampling_callbacks(registry: HookRegistry) -> None:
    """Register bounded development sampling for prompt-submission contexts."""

    registry.register(
        "agent.prompt.submit",
        _sample_prompt_submission,
        callback_id="agentos.hooks.sample-prompt-submission",
    )


def _sample_prompt_submission(invocation: HookInvocation) -> None:
    provider = invocation.ctx_type
    if provider is None:
        raise HookError("prompt-submission sampling requires a context type")
    append_hook_context_sample(
        provider=provider,
        home=_provider_home(provider),
        raw_context=invocation.ctx,
    )


def _provider_home(provider: str) -> Path:
    env_var = _PROVIDER_HOME_ENV_VARS.get(provider)
    if env_var:
        configured_home = os.getenv(env_var)
        if configured_home:
            return Path(configured_home)

    provider_spec = canonical_provider_spec_for_name(provider)
    if provider_spec is None:
        raise HookError(f"cannot sample context for unknown provider: {provider}")
    return Path(provider_spec.home_spec.default_home).expanduser()


__all__ = ["register_hook_sampling_callbacks"]
