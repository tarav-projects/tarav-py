# $kw: --from Chat.Message.Ref --from Index.Line.Anchor --note [IMPL] Hugentic grounding resolves consumer-owned relationships against current Chatlas2 message refs without extending the Normal Model --supp ^c20260816-27u
from __future__ import annotations

from collections.abc import Callable
import re
import unicodedata
from pathlib import Path

from tarav._core.errors import CliError
from tarav.index_model import canonical_index_line_body

from .anchory import (
    CHATLAS2_LINE_ANCHOR_DOSSIER_SCHEMA,
    CHATLAS2_LINE_ANCHOR_DOSSIER_SCHEMA_V1,
    CHATLAS2_MESSAGE_SUPPORT_SCHEMA,
    chatlas2_anchory_depot,
    parse_line_anchor_dossier,
    parse_message_support_record,
)
from .message_ref import resolve_chat_message_ref
from .messages import chat_message_at, list_chat_messages
from .model import JsonObject
from .normal_model import provide_normal_model


ModelLoader = Callable[[str], JsonObject]


def _loader(
    *, chatlas_root: Path | None, model_loader: ModelLoader | None
) -> ModelLoader:
    return model_loader or (
        lambda identity: provide_normal_model(
            identity_hash=identity, chatlas_root=chatlas_root
        )
    )


def parse_grounding_record(record: object) -> JsonObject:
    if isinstance(record, dict) and record.get("schema") == CHATLAS2_MESSAGE_SUPPORT_SCHEMA:
        return parse_message_support_record(record)
    return parse_line_anchor_dossier(record)


def resolve_message_member(
    member: object,
    *,
    loader: ModelLoader,
) -> JsonObject:
    if not isinstance(member, dict):
        raise CliError("Chatlas2 grounding member must be an object")
    session = member.get("session")
    if not isinstance(session, str) or not session:
        raise CliError("Chatlas2 grounding member has no session")
    model = loader(session)
    messages = list_chat_messages(model)
    resolution = resolve_chat_message_ref(
        messages,
        {
            "message_address": member.get("message_address"),
            "message_hash": member.get("message_hash"),
        },
    )
    message = resolution.get("message")
    position = None
    if isinstance(message, dict):
        address = message.get("message_address")
        position = next(
            (
                index
                for index, candidate in enumerate(messages)
                if candidate.get("message_address") == address
            ),
            None,
        )
    current_at = chat_message_at(model, message) if isinstance(message, dict) else None
    return {
        "standing": resolution["standing"],
        "message": message,
        "side": message.get("side") if isinstance(message, dict) else None,
        "text": message.get("text") if isinstance(message, dict) else None,
        "position": position,
        "current_at": current_at,
        "at_matches": current_at == member.get("at") if current_at else None,
    }


def support_record_resolves(
    record: object,
    *,
    loader: ModelLoader,
) -> bool:
    parsed = parse_grounding_record(record)
    for member in parsed["relationships"]["support"]["members"]:
        resolved = resolve_message_member(member, loader=loader)
        if resolved["standing"] != "MATCHED" or resolved["side"] != "user":
            return False
    return True


def chatlas2_support_reference_resolver(
    chatlas_root: Path | None = None,
    *,
    model_loader: ModelLoader | None = None,
) -> Callable[[str], bool]:
    depot = chatlas2_anchory_depot(chatlas_root)
    load = _loader(chatlas_root=chatlas_root, model_loader=model_loader)
    cached: dict[str, bool] = {}

    def resolves(anchor: str) -> bool:
        if anchor in cached:
            return cached[anchor]
        resolution = depot.resolve(anchor)
        record = resolution.record if resolution is not None else None
        try:
            result = (
                isinstance(record, dict)
                and record.get("app") == "chatlas2"
                and is_chatlas2_line_record(record)
                and support_record_resolves(record, loader=load)
            )
        except (CliError, OSError):
            result = False
        cached[anchor] = result
        return result

    return resolves


def _canonical_review_content(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return "".join(character for character in normalized if not character.isspace())


def tokenized_gate_failure(
    gate: object,
    line_text: str,
    *,
    loader: ModelLoader,
) -> str | None:
    if not isinstance(gate, dict):
        return "token"
    token = gate.get("token")
    proposal_member = gate.get("proposal")
    approval_member = gate.get("approval")
    if not isinstance(token, str) or not token:
        return "token"
    try:
        proposal = resolve_message_member(proposal_member, loader=loader)
        approval = resolve_message_member(approval_member, loader=loader)
    except (CliError, OSError):
        return "role"
    if (
        proposal["standing"] != "MATCHED"
        or proposal["side"] != "agent"
        or approval["standing"] != "MATCHED"
        or approval["side"] != "user"
    ):
        return "role"
    if not isinstance(proposal_member, dict) or not isinstance(approval_member, dict):
        return "role"
    if proposal_member.get("session") != approval_member.get("session"):
        return "order"
    if not isinstance(proposal["position"], int) or not isinstance(
        approval["position"], int
    ) or proposal["position"] >= approval["position"]:
        return "order"
    proposal_text = proposal["text"]
    approval_text = approval["text"]
    if not isinstance(proposal_text, str) or token not in proposal_text:
        return "proposal"
    if not isinstance(approval_text, str) or re.search(
        rf"(?m)^\s*::approve\s+{re.escape(token)}\s*$", approval_text
    ) is None:
        return "token"
    canonical_line = canonical_index_line_body(line_text)
    if _canonical_review_content(canonical_line) not in _canonical_review_content(
        proposal_text
    ):
        return "proposal"
    return None


def chatlas2_review_reference_resolver(
    chatlas_root: Path | None = None,
    *,
    model_loader: ModelLoader | None = None,
) -> Callable[[str, str], bool]:
    depot = chatlas2_anchory_depot(chatlas_root)
    load = _loader(chatlas_root=chatlas_root, model_loader=model_loader)
    cached: dict[tuple[str, str], bool] = {}

    def resolves(anchor: str, line_text: str) -> bool:
        key = (anchor, canonical_index_line_body(line_text))
        if key in cached:
            return cached[key]
        resolution = depot.resolve(anchor)
        record = resolution.record if resolution is not None else None
        reviewed = False
        try:
            if isinstance(record, dict) and record.get("app") == "chatlas2":
                dossier = parse_line_anchor_dossier(record)
                reviewed = any(
                    tokenized_gate_failure(gate, line_text, loader=load) is None
                    for gate in dossier["relationships"]["gates"][
                        "tokenized_verbatim_approval"
                    ]
                )
        except (CliError, OSError):
            reviewed = False
        cached[key] = reviewed
        return reviewed

    return resolves


def grounding_support_reference_resolver(
    chatlas_root: Path | None = None,
) -> Callable[[str], bool]:
    from tarav.chatlas.index_checks import chatlas_support_reference_resolver

    old = chatlas_support_reference_resolver(chatlas_root)
    new = chatlas2_support_reference_resolver(chatlas_root)

    def resolves(anchor: str) -> bool:
        return new(anchor) if anchor.startswith("d") else old(anchor)

    return resolves


def grounding_review_reference_resolver(
    chatlas_root: Path | None = None,
) -> Callable[[str, str], bool]:
    from tarav.chatlas.index_checks import chatlas_review_reference_resolver

    old = chatlas_review_reference_resolver(chatlas_root)
    new = chatlas2_review_reference_resolver(chatlas_root)

    def resolves(anchor: str, line_text: str) -> bool:
        return new(anchor, line_text) if anchor.startswith("d") else old(
            anchor, line_text
        )

    return resolves


def is_chatlas2_line_record(record: object) -> bool:
    return isinstance(record, dict) and record.get("schema") in {
        CHATLAS2_LINE_ANCHOR_DOSSIER_SCHEMA_V1,
        CHATLAS2_LINE_ANCHOR_DOSSIER_SCHEMA,
    }


__all__ = [
    "chatlas2_review_reference_resolver",
    "chatlas2_support_reference_resolver",
    "grounding_review_reference_resolver",
    "grounding_support_reference_resolver",
    "is_chatlas2_line_record",
    "parse_grounding_record",
    "resolve_message_member",
    "support_record_resolves",
    "tokenized_gate_failure",
]
