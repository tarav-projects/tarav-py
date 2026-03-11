from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class DialogTurn:
    role: str
    timestamp: str
    text: str


def format_unix_ms_timestamp(value: int | float | None) -> str:
    if value is None:
        return ""

    timestamp = float(value)
    if timestamp > 1_000_000_000_000:
        timestamp /= 1000.0

    return (
        datetime.fromtimestamp(timestamp, tz=timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def format_turns_jsonl(turns: list[DialogTurn]) -> str:
    lines: list[str] = []
    for turn in turns:
        lines.append(
            json.dumps(
                {
                    "role": turn.role,
                    "timestamp": turn.timestamp,
                    "text": turn.text,
                },
                ensure_ascii=False,
            )
        )
    return "\n".join(lines)


def format_turns_markdown(turns: list[DialogTurn]) -> str:
    parts: list[str] = []
    for turn in turns:
        label = turn.role.upper()
        fence = _markdown_fence(turn.text)
        parts.append(f"### {label} [{turn.timestamp}]\n")
        parts.append(f"{fence}markdown")
        parts.append(turn.text)
        parts.append(fence)
        parts.append("")
    return "\n".join(parts)


def _markdown_fence(text: str) -> str:
    longest_run = 0
    for match in re.finditer(r"`+", text):
        longest_run = max(longest_run, len(match.group(0)))
    return "`" * max(3, longest_run + 1)
