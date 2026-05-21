from __future__ import annotations

import json
from pathlib import Path

from agentos._core.errors import CliError
from agentos.agent.extractors.common import (
    DialogTurn,
    format_turns_output,
)

_CLAUDE_USER_NOISE_PREFIXES = (
    "Base directory for this skill:",
)

_CLAUDE_USER_NOISE_TEXTS = {
    "[Request interrupted by user]",
}


def extract_claude_code_chat_session_from_path(
    *,
    path: Path,
    session_id: str | None = None,
    output_format: str = "jsonl",
    raw: bool = False,
) -> str:
    _validate_claude_code_session_path(path)
    turns = extract_dialog_from_claude_code_session(path, raw=raw)

    return format_turns_output(turns, output_format)


def extract_dialog_from_claude_code_session(
    path: Path,
    *,
    raw: bool = False,
) -> list[DialogTurn]:
    turns: list[DialogTurn] = []

    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            if raw:
                turns.extend(_extract_raw_turns(obj))
            else:
                turns.extend(_extract_clean_turns(obj))

    return turns


def is_claude_code_session_path(path: Path) -> bool:
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

                if _looks_like_claude_code_message_record(obj):
                    return True
    except OSError:
        return False

    return False


def _validate_claude_code_session_path(path: Path) -> None:
    if not is_claude_code_session_path(path):
        raise CliError(f"not a Claude Code session artifact: {path}")


def _looks_like_claude_code_message_record(obj: object) -> bool:
    if not isinstance(obj, dict):
        return False

    if not isinstance(obj.get("sessionId"), str):
        return False
    if not isinstance(obj.get("version"), str):
        return False

    message = obj.get("message")
    if not isinstance(message, dict):
        return False

    return message.get("role") in {"user", "assistant"}


def _extract_clean_turns(obj: dict[str, object]) -> list[DialogTurn]:
    if obj.get("isMeta") is True:
        return []

    timestamp = str(obj.get("timestamp") or "")
    message = obj.get("message")
    if not isinstance(message, dict):
        return []

    role = message.get("role")
    if role == "user":
        text = _extract_clean_user_text(message.get("content"))
        if text is None:
            return []
        return [DialogTurn(role="user", timestamp=timestamp, text=text)]

    if role == "assistant":
        text = _extract_clean_assistant_text(message.get("content"))
        if text is None:
            return []
        return [DialogTurn(role="assistant", timestamp=timestamp, text=text)]

    return []


def _extract_clean_user_text(content: object) -> str | None:
    if isinstance(content, str):
        if _is_claude_user_noise(content):
            return None
        return content

    if not isinstance(content, list):
        return None

    texts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "text":
            continue
        text = item.get("text")
        if not isinstance(text, str) or _is_claude_user_noise(text):
            continue
        texts.append(text)

    if not texts:
        return None
    return "\n\n".join(texts)


def _extract_clean_assistant_text(content: object) -> str | None:
    if not isinstance(content, list):
        return None

    texts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "text":
            continue
        text = item.get("text")
        if not isinstance(text, str) or not text:
            continue
        texts.append(text)

    if not texts:
        return None
    return "\n\n".join(texts)


def _extract_raw_turns(obj: dict[str, object]) -> list[DialogTurn]:
    timestamp = str(obj.get("timestamp") or "")
    message = obj.get("message")
    if not isinstance(message, dict):
        return []

    role = message.get("role")
    if role not in {"user", "assistant"}:
        return []

    content = message.get("content")
    if isinstance(content, str):
        return [DialogTurn(role=role, timestamp=timestamp, text=content)]

    if not isinstance(content, list):
        return []

    turns: list[DialogTurn] = []
    for item in content:
        text = _stringify_claude_content_item(item)
        if text is None:
            continue
        turns.append(DialogTurn(role=role, timestamp=timestamp, text=text))
    return turns


def _stringify_claude_content_item(item: object) -> str | None:
    if not isinstance(item, dict):
        return json.dumps(item, ensure_ascii=False)

    item_type = item.get("type")
    text = item.get("text")
    if isinstance(text, str):
        return text

    if item_type == "tool_result":
        content = item.get("content")
        if isinstance(content, str):
            return content

    thinking = item.get("thinking")
    if isinstance(thinking, str) and thinking:
        return thinking

    return json.dumps(item, ensure_ascii=False)


def _is_claude_user_noise(text: str) -> bool:
    if text in _CLAUDE_USER_NOISE_TEXTS:
        return True
    return any(text.startswith(prefix) for prefix in _CLAUDE_USER_NOISE_PREFIXES)
