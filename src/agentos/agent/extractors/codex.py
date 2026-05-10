from __future__ import annotations

import json
from pathlib import Path

from agentos._core.errors import CliError
from agentos.agent.extractors.common import (
    DialogTurn,
    format_turns_jsonl,
    format_turns_markdown,
)

_CODEX_SESSION_META_ORIGINATORS = {
    "codex_cli_rs",
    "codex-tui",
}

# Content prefixes injected by the Codex platform into user-role messages.
# These are never human-authored text.
_CODEX_NOISE_PREFIXES = (
    "<INSTRUCTIONS>",
    "<environment_context>",
    "# AGENTS.md",
    "<skill>",
    "<turn_aborted>",
    "<collaboration_mode>",
    "<permissions",
)


def extract_codex_chat_session_from_path(
    *,
    path: Path,
    session_id: str | None = None,
    output_format: str = "jsonl",
    raw: bool = False,
) -> str:
    _validate_codex_rollout_path(path)
    turns = extract_dialog_from_codex_rollout(path, raw=raw)

    if output_format == "markdown":
        return format_turns_markdown(turns)
    return format_turns_jsonl(turns)


def extract_dialog_from_codex_rollout(
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

            payload = obj.get("payload", {})
            role = payload.get("role", "")
            timestamp = obj.get("timestamp", "")
            content = payload.get("content") or []

            if role == "developer" and not raw:
                continue

            for item in content:
                item_type = item.get("type", "")
                text = item.get("text", "")
                if not text:
                    continue

                if role == "user":
                    if raw:
                        turns.append(DialogTurn(role="user", timestamp=timestamp, text=text))
                        continue
                    if _is_noise_block(text):
                        continue
                    text = _strip_system_reminder(text)
                    if text:
                        turns.append(DialogTurn(role="user", timestamp=timestamp, text=text))

                elif role == "assistant":
                    if raw:
                        turns.append(DialogTurn(role="assistant", timestamp=timestamp, text=text))
                        continue
                    if item_type != "output_text":
                        continue
                    turns.append(DialogTurn(role="assistant", timestamp=timestamp, text=text))

                elif role == "developer" and raw:
                    turns.append(DialogTurn(role="developer", timestamp=timestamp, text=text))

    return turns


def is_codex_rollout_path(path: Path) -> bool:
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
                if _is_codex_session_meta(obj):
                    return True
                break
    except OSError:
        return False

    return False


def _validate_codex_rollout_path(path: Path) -> None:
    if not is_codex_rollout_path(path):
        raise CliError(f"not a Codex rollout JSONL: {path}")


def _is_codex_session_meta(obj: object) -> bool:
    if not isinstance(obj, dict):
        return False
    if obj.get("type") != "session_meta":
        return False

    payload = obj.get("payload")
    if not isinstance(payload, dict):
        return False

    originator = payload.get("originator")
    if not isinstance(originator, str):
        return False

    if originator in _CODEX_SESSION_META_ORIGINATORS:
        return True

    return originator.startswith("codex")


def _strip_system_reminder(text: str) -> str:
    idx = text.find("<system-reminder>")
    if idx == -1:
        return text
    return text[:idx].rstrip()


def _is_noise_block(text: str) -> bool:
    for prefix in _CODEX_NOISE_PREFIXES:
        if text.startswith(prefix):
            return True
    return False
