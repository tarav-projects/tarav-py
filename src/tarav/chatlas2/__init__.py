# $kw: ^chatlas2-package --from Normalization.Pipeline::Chatlas.Session.Model --from Dependency.Profile.Split --from Event.Ref --note [CT] Chatlas2 is an isolated experimental namespace that may reuse current Chatlas without creating a reverse dependency --supp ^c20260814-12u ^c20260814-13u ^c20260814-14u ^c20260815-39u
from __future__ import annotations

from .commands import register_chatlas2_commands
from .anchory import (
    CHATLAS2_ANCHOR_BATCH_SCHEMA,
    CHATLAS2_LINE_ANCHOR_DOSSIER_SCHEMA,
    CHATLAS2_NAMESPACE,
    chatlas2_anchory_batch_preview,
    chatlas2_anchory_batch_register,
    chatlas2_anchory_preview,
    chatlas2_anchory_register,
    chatlas2_anchory_resolve,
    format_support_member_ref,
)
from .claude import (
    CLAUDE_LEGACY_RAW_MODEL_VERSION,
    CLAUDE_PROMPT_SOURCE_RAW_MODEL_VERSION,
    ClaudeLegacyRawNormalizer,
    ClaudePromptSourceRawNormalizer,
    ClaudeRawModelVersioner,
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
from .messages import (
    chat_message_at,
    chat_message_neighborhood,
    chat_message_support_member,
    find_chat_messages,
    list_chat_messages,
)

__all__ = [
    "build_normal_model",
    "build_normal_model_from_row",
    "CHATLAS2_ANCHOR_BATCH_SCHEMA",
    "CHATLAS2_LINE_ANCHOR_DOSSIER_SCHEMA",
    "CHATLAS2_NAMESPACE",
    "CLAUDE_LEGACY_RAW_MODEL_VERSION",
    "CLAUDE_PROMPT_SOURCE_RAW_MODEL_VERSION",
    "ClaudeLegacyRawNormalizer",
    "ClaudePromptSourceRawNormalizer",
    "ClaudeRawModelVersioner",
    "chat_message_ref",
    "chat_message_at",
    "chat_message_neighborhood",
    "chat_message_support_member",
    "chatlas2_anchory_batch_preview",
    "chatlas2_anchory_batch_register",
    "chatlas2_anchory_preview",
    "chatlas2_anchory_register",
    "chatlas2_anchory_resolve",
    "compute_chat_message_address",
    "compute_chat_message_hash",
    "compute_event_address",
    "compute_event_hash",
    "event_ref",
    "find_chat_messages",
    "format_support_member_ref",
    "list_chat_messages",
    "register_chatlas2_commands",
    "resolve_chat_message_ref",
    "resolve_event_ref",
]
