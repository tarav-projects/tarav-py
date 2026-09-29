# $kw: --from Agent.Normal.Model --from Provider.Instance
"""gemini-cli transcript extraction."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tarav.l0._core.errors import CliError
from tarav.l1.agent.providers.extractor_common import (
    DialogTurn,
    _string_or_empty,
    format_turns_output,
)

_GEMINI_REFERENCED_CONTENT_MARKER = "--- Content from referenced files ---"
_GEMINI_REFERENCED_FILE_PREFIX = "Content from @"
_GEMINI_REFERENCED_CONTENT_END = "--- End of content ---"


def extract_gemini_cli_chat_session_from_path(
    *,
    path: Path,
    session_id: str | None = None,
    output_format: str = "jsonl",
    raw: bool = False,
) -> str:
    session_data = load_gemini_cli_session_data(path)
    resolved_session_id = _resolve_gemini_session_id(
        path,
        session_data=session_data,
        session_id=session_id,
    )
    turns = extract_dialog_from_gemini_cli_session(
        session_data=session_data,
        session_id=resolved_session_id,
        raw=raw,
    )

    return format_turns_output(turns, output_format)


def extract_dialog_from_gemini_cli_session(
    *,
    session_data: dict[str, Any],
    session_id: str,
    raw: bool = False,
) -> list[DialogTurn]:
    if session_data.get("sessionId") != session_id:
        raise CliError(
            f"session id {session_id} does not match Gemini session artifact"
        )

    messages = session_data.get("messages")
    if not isinstance(messages, list):
        raise CliError(f"Gemini session has no messages array for session {session_id}")

    turns: list[DialogTurn] = []
    for message in messages:
        if not isinstance(message, dict):
            continue

        message_type = message.get("type")
        timestamp = _string_or_empty(message.get("timestamp"))

        if raw:
            turns.extend(_extract_raw_turns(message_type=message_type, timestamp=timestamp, message=message))
            continue

        clean_turn = _extract_clean_turn(message_type=message_type, timestamp=timestamp, message=message)
        if clean_turn is not None:
            turns.append(clean_turn)

    return turns


def is_gemini_cli_session_path(path: Path) -> bool:
    try:
        session_data = load_gemini_cli_session_data(path)
    except CliError:
        return False
    return _extract_embedded_session_id(session_data) is not None


def infer_gemini_cli_session_id_from_path(path: Path) -> str | None:
    try:
        session_data = load_gemini_cli_session_data(path)
    except CliError:
        return None
    return _extract_embedded_session_id(session_data)


def load_gemini_cli_session_data(path: Path) -> dict[str, Any]:
    try:
        raw_text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        raise CliError(f"unable to read Gemini session artifact {path}: {exc}") from exc

    try:
        obj = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise CliError(f"not a Gemini CLI session artifact: {path}") from exc

    if not isinstance(obj, dict):
        raise CliError(f"not a Gemini CLI session artifact: {path}")

    if _extract_embedded_session_id(obj) is None:
        raise CliError(f"not a Gemini CLI session artifact: {path}")

    return obj


def _resolve_gemini_session_id(
    path: Path,
    *,
    session_data: dict[str, Any],
    session_id: str | None,
) -> str:
    embedded_session_id = _extract_embedded_session_id(session_data)
    if embedded_session_id is None:
        raise CliError(f"not a Gemini CLI session artifact: {path}")

    if session_id is not None and session_id != embedded_session_id:
        raise CliError(
            f"session id {session_id} does not match Gemini artifact provenance: {path}"
        )

    return embedded_session_id


def _extract_embedded_session_id(session_data: dict[str, Any]) -> str | None:
    session_id = session_data.get("sessionId")
    messages = session_data.get("messages")
    if not isinstance(session_id, str) or not session_id:
        return None
    if not isinstance(messages, list):
        return None
    return session_id


def _extract_clean_turn(
    *,
    message_type: object,
    timestamp: str,
    message: dict[str, Any],
) -> DialogTurn | None:
    if message_type == "user":
        text = _extract_clean_user_text(message.get("content"))
        if text is None:
            return None
        return DialogTurn(role="user", timestamp=timestamp, text=text)

    if message_type == "gemini":
        text = _extract_clean_assistant_text(message.get("content"))
        if text is None:
            return None
        return DialogTurn(role="assistant", timestamp=timestamp, text=text)

    return None


def _extract_clean_user_text(content: object) -> str | None:
    if isinstance(content, str):
        cleaned = _strip_referenced_content(content)
        return cleaned or None

    if not isinstance(content, list):
        return None

    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if not isinstance(text, str):
            continue
        cleaned = _strip_referenced_content(text)
        if cleaned is None:
            break
        if cleaned:
            parts.append(cleaned)

    if not parts:
        return None
    return "\n\n".join(parts)


def _extract_clean_assistant_text(content: object) -> str | None:
    if isinstance(content, str):
        return content or None

    if not isinstance(content, list):
        return None

    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if isinstance(text, str) and text:
            parts.append(text)

    if not parts:
        return None
    return "\n\n".join(parts)


def _extract_raw_turns(
    *,
    message_type: object,
    timestamp: str,
    message: dict[str, Any],
) -> list[DialogTurn]:
    role = _map_gemini_role(message_type)
    turns: list[DialogTurn] = []

    for text in _raw_content_blocks(message.get("content")):
        turns.append(DialogTurn(role=role, timestamp=timestamp, text=text))

    thoughts = message.get("thoughts")
    if isinstance(thoughts, list):
        for thought in thoughts:
            text = _stringify_gemini_thought(thought)
            if text is None:
                continue
            turns.append(DialogTurn(role=role, timestamp=_thought_timestamp(thought, default=timestamp), text=text))

    tool_calls = message.get("toolCalls")
    if isinstance(tool_calls, list):
        for tool_call in tool_calls:
            turns.append(
                DialogTurn(
                    role=role,
                    timestamp=_tool_call_timestamp(tool_call, default=timestamp),
                    text=json.dumps(tool_call, ensure_ascii=False),
                )
            )

    return turns


def _raw_content_blocks(content: object) -> list[str]:
    if isinstance(content, str):
        return [content] if content else []

    if not isinstance(content, list):
        return []

    blocks: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            blocks.append(json.dumps(item, ensure_ascii=False))
            continue
        text = item.get("text")
        if isinstance(text, str):
            blocks.append(text)
            continue
        blocks.append(json.dumps(item, ensure_ascii=False))
    return blocks


def _stringify_gemini_thought(thought: object) -> str | None:
    if isinstance(thought, dict):
        description = thought.get("description")
        if isinstance(description, str) and description:
            return description
        return json.dumps(thought, ensure_ascii=False)

    if thought is None:
        return None
    return json.dumps(thought, ensure_ascii=False)


def _thought_timestamp(thought: object, *, default: str) -> str:
    if isinstance(thought, dict):
        timestamp = thought.get("timestamp")
        if isinstance(timestamp, str):
            return timestamp
    return default


def _tool_call_timestamp(tool_call: object, *, default: str) -> str:
    if isinstance(tool_call, dict):
        timestamp = tool_call.get("timestamp")
        if isinstance(timestamp, str):
            return timestamp
    return default


def _map_gemini_role(message_type: object) -> str:
    if message_type == "gemini":
        return "assistant"
    if message_type == "user":
        return "user"
    if isinstance(message_type, str) and message_type:
        return message_type
    return "unknown"


def _strip_referenced_content(text: str) -> str | None:
    marker_index = text.find(_GEMINI_REFERENCED_CONTENT_MARKER)
    if marker_index != -1:
        text = text[:marker_index]

    stripped = text.strip()
    if not stripped:
        return ""
    if stripped == _GEMINI_REFERENCED_CONTENT_MARKER:
        return None
    if stripped == _GEMINI_REFERENCED_CONTENT_END:
        return None
    if stripped.startswith(_GEMINI_REFERENCED_FILE_PREFIX):
        return None
    return text.strip()
