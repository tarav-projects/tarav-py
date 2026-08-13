# $kw: --from Agentos.Hook --from Chatlas.Update.Pipeline --note [IMPL] agent.turn.stop defers the canonical targeted Chatlas update to the Agentos daemon --supp ^c20260811-50u ^c20260811-54u
from __future__ import annotations

from pathlib import Path

from agentos.hooks import HookError, HookInvocation, HookRegistry

from agentos.chatlas.core import chatlas_update
from agentos.chatlas.normalization.session_model.delta import set_trust_tier
from agentos.chatlas.providers import supported_chatlas_provider_families


TURN_STOP_HOOK = "agent.turn.stop"
CHATLAS_TURN_STOP_CALLBACK_ID = "agentos_chatlas.session-update"


def register_chatlas_hook_callbacks(registry: HookRegistry) -> None:
    registry.register(
        TURN_STOP_HOOK,
        update_chatlas_session_from_turn_stop,
        callback_id=CHATLAS_TURN_STOP_CALLBACK_ID,
    )


def update_chatlas_session_from_turn_stop(invocation: HookInvocation) -> None:
    provider = invocation.ctx_type
    if provider not in {
        family.family for family in supported_chatlas_provider_families()
    }:
        return

    session_id = invocation.ctx.get("session_id")
    if not isinstance(session_id, str) or not session_id.strip():
        raise HookError("Chatlas turn-stop refresh requires ctx.session_id")

    start_path = _existing_start_path(invocation.ctx.get("cwd"))
    set_trust_tier("append")
    chatlas_update(
        providers=(provider,),
        session_ids=(session_id,),
        start_path=start_path,
        progress=None,
    )


def _existing_start_path(value: object) -> Path:
    if isinstance(value, str) and value:
        path = Path(value)
        if path.is_dir():
            return path
    return Path.cwd()


__all__ = [
    "CHATLAS_TURN_STOP_CALLBACK_ID",
    "TURN_STOP_HOOK",
    "register_chatlas_hook_callbacks",
    "update_chatlas_session_from_turn_stop",
]
