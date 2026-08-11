# $kw: --from Chat.Touched.Index --note [IMPL] chat evidence stays a pure in-memory tape projection so semantic capture never consumes a retained Product --supp ^c20260804-60u
from __future__ import annotations

from typing import Any


def content_text(value: object) -> str:
    if not isinstance(value, list):
        return ""
    return "\n".join(
        text
        for block in value
        if isinstance(block, dict)
        and isinstance((text := block.get("text")), str)
    )


def transcript_visible_messages(events: object) -> list[dict[str, object]]:
    """Ordered transcript-visible chat messages carried by a tape event list.

    This is the pure chat evidence projection: it keeps only `message` events
    the transcript surface shows for the user and assistant roles, so reasoning,
    tool, usage, and model-run payloads never reach a semantic consumer. Each
    entry retains its tape `sequence` so the caller can trace it back.
    """
    if not isinstance(events, list):
        return []
    messages: list[dict[str, object]] = []
    for event in events:
        if not isinstance(event, dict) or event.get("kind") != "message":
            continue
        surfaces = event.get("surfaces")
        if not isinstance(surfaces, dict) or surfaces.get("transcript") != "visible":
            continue
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        role = payload.get("role")
        if role not in {"user", "assistant"}:
            continue
        sequence = event.get("sequence")
        if isinstance(sequence, bool) or not isinstance(sequence, int):
            continue
        messages.append(
            {
                "sequence": sequence,
                "role": role,
                "text": content_text(payload.get("content")),
            }
        )
    messages.sort(key=lambda message: message["sequence"])
    return messages


def visible_message_texts(
    session_model: dict[str, Any],
    *,
    producer_types: set[str] | None = None,
    normal_turn_kinds: set[str] | None = None,
) -> list[str]:
    chat = session_model.get("chat")
    if not isinstance(chat, dict):
        return []
    if normal_turn_kinds is not None:
        from .events import normal_turn_kind

        texts: list[str] = []
        events = chat.get("events")
        for event in events if isinstance(events, list) else []:
            if not isinstance(event, dict) or normal_turn_kind(event) not in normal_turn_kinds:
                continue
            surfaces = event.get("surfaces")
            if not isinstance(surfaces, dict) or surfaces.get("transcript") != "visible":
                continue
            payload = event.get("payload")
            text = content_text(payload.get("content")) if isinstance(payload, dict) else ""
            if text:
                texts.append(text)
        return texts
    messages = chat.get("messages")
    if not isinstance(messages, list):
        return []
    texts: list[str] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        producer = message.get("producer")
        if not isinstance(producer, dict):
            continue
        if producer_types is None or producer.get("type") not in producer_types:
            continue
        text = content_text(message.get("content"))
        if text:
            texts.append(text)
    return texts


def user_content_text_marker(
    content: list[dict[str, object]],
    *,
    prefix_to_name: tuple[tuple[str, str], ...],
) -> str | None:
    for block in content:
        if not isinstance(block, dict):
            continue
        text = block.get("text")
        if not isinstance(text, str):
            continue
        stripped = text.lstrip()
        for prefix, name in prefix_to_name:
            if stripped.startswith(prefix):
                return name
    return None


__all__ = [
    "content_text",
    "transcript_visible_messages",
    "user_content_text_marker",
    "visible_message_texts",
]
