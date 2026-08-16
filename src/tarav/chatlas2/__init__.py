# $kw: ^chatlas2-package --from Normalization.Pipeline::Chatlas.Session.Model --from Dependency.Profile.Split --from Event.Ref --note [CT] Chatlas2 is an isolated experimental namespace that may reuse current Chatlas without creating a reverse dependency --supp ^c20260814-12u ^c20260814-13u ^c20260814-14u ^c20260815-39u
from __future__ import annotations

from .commands import register_chatlas2_commands
from .claude import (
    CLAUDE_RAW_MODEL_VERSION,
    ClaudeRawModelVersioner,
    ClaudeRawNormalizer,
)
from .event_ref import (
    compute_event_address,
    compute_event_hash,
    event_ref,
    resolve_event_ref,
)
from .message_ref import (
    chat_message_ref,
    compute_chat_message_address,
    compute_chat_message_hash,
    resolve_chat_message_ref,
)
from .pipeline import build_normal_model, build_normal_model_from_row

__all__ = [
    "build_normal_model",
    "build_normal_model_from_row",
    "CLAUDE_RAW_MODEL_VERSION",
    "ClaudeRawModelVersioner",
    "ClaudeRawNormalizer",
    "chat_message_ref",
    "compute_chat_message_address",
    "compute_chat_message_hash",
    "compute_event_address",
    "compute_event_hash",
    "event_ref",
    "register_chatlas2_commands",
    "resolve_chat_message_ref",
    "resolve_event_ref",
]
