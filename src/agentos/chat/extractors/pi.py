from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agentos._core.errors import CliError
from agentos.chat.extractors.common import (
    DialogTurn,
    format_turns_jsonl,
    format_turns_markdown,
)


def extract_pi_chat_session_from_path(
    *,
    path: Path,
    session_id: str | None = None,
    output_format: str = "jsonl",
    raw: bool = False,
) -> str:
    records = load_pi_session_records(path)
    resolved_session_id = _resolve_pi_session_id(
        path,
        records=records,
        session_id=session_id,
    )
    turns = extract_dialog_from_pi_session(
        records=records,
        session_id=resolved_session_id,
        raw=raw,
    )

    if output_format == "markdown":
        return format_turns_markdown(turns)
    return format_turns_jsonl(turns)


def extract_dialog_from_pi_session(
    *,
    records: list[dict[str, Any]],
    session_id: str,
    raw: bool = False,
) -> list[DialogTurn]:
    embedded_session_id = _extract_embedded_session_id(records)
    if embedded_session_id is not None and embedded_session_id != session_id:
        raise CliError(f"session id {session_id} does not match pi session artifact")

    turns: list[DialogTurn] = []
    for record in records:
        record_type = _string_or_empty(record.get("type"))
        timestamp = _string_or_empty(record.get("timestamp"))

        if raw:
            turns.extend(_extract_raw_turns(record_type=record_type, timestamp=timestamp, record=record))
            continue

        clean_turn = _extract_clean_turn(record_type=record_type, timestamp=timestamp, record=record)
        if clean_turn is not None:
            turns.append(clean_turn)

    return turns


def is_pi_session_path(path: Path) -> bool:
    try:
        records = load_pi_session_records(path)
    except CliError:
        return False
    return _extract_embedded_session_id(records) is not None


def infer_pi_session_id_from_path(path: Path) -> str | None:
    try:
        records = load_pi_session_records(path)
    except CliError:
        return _infer_pi_session_id_from_path_hint(path)
    return _extract_embedded_session_id(records) or _infer_pi_session_id_from_path_hint(path)


def load_pi_session_records(path: Path) -> list[dict[str, Any]]:
    if path.suffix != ".jsonl":
        raise CliError(f"not a pi session artifact: {path}")

    records: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    records.append(obj)
    except OSError as exc:
        raise CliError(f"unable to read pi session artifact {path}: {exc}") from exc

    if not records or not _is_pi_session_records(records):
        raise CliError(f"not a pi session artifact: {path}")

    return records


def has_pi_session_signature(records: list[dict[str, Any]]) -> bool:
    for record in records:
        record_type = record.get("type")
        if record_type == "model_change":
            provider = record.get("provider")
            model_id = record.get("modelId")
            if isinstance(provider, str) and provider and isinstance(model_id, str) and model_id:
                return True
            continue

        if record_type == "thinking_level_change":
            thinking_level = record.get("thinkingLevel")
            if isinstance(thinking_level, str) and thinking_level:
                return True
            continue

        if record_type == "custom_message":
            return True

        if record_type != "message":
            continue

        message = record.get("message")
        if not isinstance(message, dict):
            continue

        if message.get("role") == "toolResult":
            return True

        metadata = message.get("metadata")
        if isinstance(metadata, dict) and metadata:
            return True

        if _content_has_pi_specific_items(message.get("content")):
            return True

    return False


def _is_pi_session_records(records: list[dict[str, Any]]) -> bool:
    return _extract_embedded_session_id(records) is not None and has_pi_session_signature(records)


def _resolve_pi_session_id(
    path: Path,
    *,
    records: list[dict[str, Any]],
    session_id: str | None,
) -> str:
    embedded_session_id = _extract_embedded_session_id(records)
    inferred_session_id = embedded_session_id or _infer_pi_session_id_from_path_hint(path)

    if session_id is not None and inferred_session_id is not None and session_id != inferred_session_id:
        raise CliError(f"session id {session_id} does not match pi artifact provenance: {path}")

    if session_id is not None:
        return session_id
    if inferred_session_id is not None:
        return inferred_session_id
    raise CliError(f"unable to infer pi session id from artifact: {path}")


def _extract_embedded_session_id(records: list[dict[str, Any]]) -> str | None:
    for record in records:
        if record.get("type") != "session":
            continue
        session_id = record.get("id")
        if isinstance(session_id, str) and session_id:
            return session_id
    return None


def _infer_pi_session_id_from_path_hint(path: Path) -> str | None:
    if path.suffix != ".jsonl":
        return None
    stem = path.stem
    if "_" in stem:
        _, suffix = stem.rsplit("_", maxsplit=1)
        if suffix:
            return suffix
    return stem or None


def _extract_clean_turn(
    *,
    record_type: str,
    timestamp: str,
    record: dict[str, Any],
) -> DialogTurn | None:
    if record_type == "custom_message":
        if record.get("display") is not True:
            return None
        text = _string_or_none(record.get("content"))
        if text is None:
            return None
        return DialogTurn(role="user", timestamp=timestamp, text=text)

    if record_type != "message":
        return None

    message = record.get("message")
    if not isinstance(message, dict):
        return None

    role = _string_or_empty(message.get("role"))
    if role not in {"user", "assistant"}:
        return None

    text = _extract_clean_message_text(message.get("content"))
    if text is None:
        return None
    return DialogTurn(role=role, timestamp=timestamp, text=text)


def _extract_clean_message_text(content: object) -> str | None:
    if isinstance(content, str):
        return content or None

    if not isinstance(content, list):
        return None

    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "text":
            continue
        text = item.get("text")
        if isinstance(text, str) and text:
            parts.append(text)

    if not parts:
        return None
    return "\n\n".join(parts)


def _extract_raw_turns(
    *,
    record_type: str,
    timestamp: str,
    record: dict[str, Any],
) -> list[DialogTurn]:
    if record_type == "custom_message":
        content = _string_or_none(record.get("content"))
        if content is None:
            return [
                DialogTurn(
                    role="system",
                    timestamp=timestamp,
                    text=json.dumps(record, ensure_ascii=False),
                )
            ]
        role = "user" if record.get("display") is True else "system"
        return [DialogTurn(role=role, timestamp=timestamp, text=content)]

    if record_type == "message":
        message = record.get("message")
        if not isinstance(message, dict):
            return [
                DialogTurn(
                    role="system",
                    timestamp=timestamp,
                    text=json.dumps(record, ensure_ascii=False),
                )
            ]

        role = _map_raw_role(message.get("role"))
        blocks = _extract_raw_message_blocks(message.get("content"))
        if not blocks:
            return [
                DialogTurn(
                    role=role,
                    timestamp=timestamp,
                    text=json.dumps(record, ensure_ascii=False),
                )
            ]
        return [
            DialogTurn(role=role, timestamp=timestamp, text=block)
            for block in blocks
        ]

    return [
        DialogTurn(
            role="system",
            timestamp=timestamp,
            text=json.dumps(record, ensure_ascii=False),
        )
    ]


def _extract_raw_message_blocks(content: object) -> list[str]:
    if isinstance(content, str):
        return [content] if content else []

    if not isinstance(content, list):
        return []

    blocks: list[str] = []
    for item in content:
        if isinstance(item, str):
            if item:
                blocks.append(item)
            continue

        if not isinstance(item, dict):
            blocks.append(json.dumps(item, ensure_ascii=False))
            continue

        item_type = item.get("type")
        if item_type == "text":
            text = item.get("text")
            if isinstance(text, str) and text:
                blocks.append(text)
            continue

        if item_type == "thinking":
            thinking = item.get("thinking")
            if isinstance(thinking, str) and thinking:
                blocks.append(thinking)
            continue

        blocks.append(json.dumps(item, ensure_ascii=False))

    return blocks


def _content_has_pi_specific_items(content: object) -> bool:
    if not isinstance(content, list):
        return False

    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") in {"thinking", "toolCall"}:
            return True
    return False


def _map_raw_role(value: object) -> str:
    role = _string_or_empty(value)
    if role == "toolResult":
        return "tool"
    return role or "assistant"


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _string_or_empty(value: object) -> str:
    if isinstance(value, str):
        return value
    return ""


__all__ = [
    "extract_dialog_from_pi_session",
    "extract_pi_chat_session_from_path",
    "has_pi_session_signature",
    "infer_pi_session_id_from_path",
    "is_pi_session_path",
    "load_pi_session_records",
]
