# $kw: --from Agentos.Hook --from Chatlas.Update --from Chat.Index.Delta --note [IMPL] agent.turn.stop defers targeted refresh and semantic Chat.Index maintenance to the Agentos daemon --supp ^c20260811-50u ^c20260811-54u
from __future__ import annotations

from pathlib import Path

from agentos.hooks import HookError, HookInvocation, HookRegistry

from agentos.chatlas.core import chatlas_update
from agentos.chatlas.chat_index_producer import maintain_chat_index_with_agent
from agentos.chatlas.index_query import select_one_chatlas_index_row
from agentos.chatlas.providers import supported_chatlas_provider_families
from agentos.chatlas.session_cache import load_chatlas_session_model


TURN_STOP_HOOK = "agent.turn.stop"
CHATLAS_TURN_STOP_CALLBACK_ID = "agentos_chatlas.chat-index-maintenance"


def register_chatlas_hook_callbacks(registry: HookRegistry) -> None:
    registry.register(
        TURN_STOP_HOOK,
        maintain_chat_index_from_turn_stop,
        callback_id=CHATLAS_TURN_STOP_CALLBACK_ID,
        execution="daemon",
    )


def maintain_chat_index_from_turn_stop(invocation: HookInvocation) -> None:
    provider = invocation.ctx_type
    if provider not in {
        family.family for family in supported_chatlas_provider_families()
    }:
        return

    session_id = invocation.ctx.get("session_id")
    if not isinstance(session_id, str) or not session_id.strip():
        raise HookError("Chatlas turn-stop refresh requires ctx.session_id")

    start_path = _existing_start_path(invocation.ctx.get("cwd"))
    chatlas_update(
        providers=(provider,),
        session_ids=(session_id,),
        start_path=start_path,
        progress=None,
    )
    session = select_one_chatlas_index_row(
        command="agent.turn.stop Chatlas refresh",
        providers=(provider,),
        session_id=session_id,
    )
    load_chatlas_session_model(session)
    identity_hash = session.get("identity_hash")
    if not isinstance(identity_hash, str) or not identity_hash:
        raise HookError("Chatlas turn-stop refresh resolved no session identity_hash")
    maintain_chat_index_with_agent(identity_hash=identity_hash)


def _existing_start_path(value: object) -> Path:
    if isinstance(value, str) and value:
        path = Path(value)
        if path.is_dir():
            return path
    return Path.cwd()


__all__ = [
    "CHATLAS_TURN_STOP_CALLBACK_ID",
    "TURN_STOP_HOOK",
    "maintain_chat_index_from_turn_stop",
    "register_chatlas_hook_callbacks",
]
