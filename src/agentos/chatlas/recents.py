from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from agentos._core.errors import CliError

from agentos.chatlas._duration import parse_duration_seconds
from agentos.chatlas.normalization.session_model.messages import content_text
from agentos.chatlas.normalization.session_model.events import normal_turn_kind
from agentos.chatlas.query import chatlas_query
from agentos.chatlas.time_interface import format_local_timestamp
from agentos.chatlas.time_interface import normalize_cli_timestamp
from agentos.chatlas.time_interface import parse_interface_timestamp
from agentos.chatlas.views import load_chatlas_session_model

_DEFAULT_SINCE = "3d"
_DEFAULT_LAST_TURNS = 3
_DEFAULT_TRUNCATE_LENGTH = 200

def parse_since_duration(value: str) -> timedelta:
    """Parse the recents duration language: 30s, 10m, 4h, 3d, 2w."""
    return timedelta(seconds=parse_duration_seconds(value, field_name="--since"))


def parse_since_date(value: str) -> datetime:
    """Parse an absolute --since-date: a date or an ISO datetime, naive values local."""
    normalized = normalize_cli_timestamp(value, field="--since-date")
    parsed = parse_interface_timestamp(normalized)
    if parsed is None:
        raise CliError(
            f"invalid --since-date value: {value} "
            "(expected forms like 2026-07-30 or 2026-07-30T14:00)"
        )
    return parsed.astimezone(timezone.utc)


def since_window_seconds(since: str, since_date: str | None) -> int:
    """Resolve either since form into a look-back window in seconds from now."""
    if since_date is None:
        return int(parse_since_duration(since).total_seconds())
    elapsed = datetime.now(timezone.utc) - parse_since_date(since_date)
    return max(int(elapsed.total_seconds()), 0)


def chatlas_recents(
    *,
    since: str = _DEFAULT_SINCE,
    since_date: str | None = None,
    last_turns: int = _DEFAULT_LAST_TURNS,
    truncate_length: int | None = _DEFAULT_TRUNCATE_LENGTH,
    uri: str | None = None,
    identity_hash: str | None = None,
    project: str | Path | None = None,
    project_base: str | None = None,
    providers: tuple[str, ...] | None = None,
    instances: tuple[str, ...] | None = None,
    provider_instance_fingerprint: str | None = None,
    session_id: str | None = None,
    display_name: str | None = None,
    extractable_only: bool = False,
    min_user_turns: int | None = None,
    limit: int | None = None,
    chatlas_root: Path | None = None,
) -> dict[str, object]:
    now = datetime.now(timezone.utc)
    cutoff = parse_since_date(since_date) if since_date is not None else now - parse_since_duration(since)
    active_after = cutoff.strftime("%Y-%m-%dT%H:%M:%S+00:00")

    query_result = chatlas_query(
        uri=uri,
        identity_hash=identity_hash,
        project=project,
        project_base=project_base,
        providers=providers,
        instances=instances,
        provider_instance_fingerprint=provider_instance_fingerprint,
        session_id=session_id,
        display_name=display_name,
        extractable_only=extractable_only,
        active_after=active_after,
        sort="newest",
        limit=limit,
        min_user_turns=min_user_turns,
        chatlas_root=chatlas_root,
        row_shape="full",
    )

    entries: list[dict[str, object]] = []
    for row in query_result.get("rows", []):
        if not isinstance(row, dict):
            continue
        last_user_turns = _extract_last_user_turns(row, last_turns=last_turns)
        if truncate_length is not None:
            last_user_turns = [
                {**turn, "text": _truncate(str(turn.get("text", "")), truncate_length)}
                for turn in last_user_turns
            ]
        summary = row.get("summary")
        summary = summary if isinstance(summary, dict) else {}
        entries.append({
            "last_activity_at": row.get("last_activity_at"),
            "created_at": row.get("created_at"),
            "provider": row.get("provider"),
            "instance": row.get("instance"),
            "project_path": row.get("project_path"),
            "identity_hash": row.get("identity_hash"),
            "session_id": row.get("session_id"),
            "uri": row.get("uri"),
            "chat_index": row.get("chat_index"),
            "user_turn_count": summary.get("visible_user_turn_count"),
            "last_user_turns": last_user_turns,
        })

    return {
        "status": "ok",
        "command": "chatlas recents",
        "since": None if since_date is not None else since,
        "since_date": since_date,
        "active_after": active_after,
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
        "last_turns": last_turns,
        "truncate_length": truncate_length,
        "entry_count": len(entries),
        "entries": entries,
    }


def format_chatlas_recents_text(payload: dict[str, object]) -> str:
    lines: list[str] = []
    entries = payload.get("entries", [])
    if not isinstance(entries, list):
        return ""
    reference = _parse_timestamp(payload.get("generated_at")) or datetime.now(timezone.utc)
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        timestamp = _format_timestamp(entry.get("last_activity_at"))
        age = _format_relative(entry.get("last_activity_at"), reference)
        agent = str(entry.get("provider") or "?")
        instance = entry.get("instance")
        if isinstance(instance, str) and instance:
            agent = f"{agent}/{instance}"
        project_path = entry.get("project_path")
        project_base = Path(project_path).name if isinstance(project_path, str) and project_path else "?"
        lines.append(f"{timestamp}  {age}  {agent}  {project_base}")

        session_line = f"  {entry.get('session_id') or '?'}"
        turn_count = entry.get("user_turn_count")
        if isinstance(turn_count, int):
            session_line += f"  ·  {turn_count} user turns"
        lines.append(session_line)
        if isinstance(project_path, str) and project_path:
            lines.append(f"  {project_path}")
        chat_index = entry.get("chat_index")
        if isinstance(chat_index, dict) and chat_index.get("materialized") is True:
            lines.append(f"  index at: {chat_index.get('path')}")

        turns = entry.get("last_user_turns", [])
        if isinstance(turns, list):
            rendered = [
                (_format_relative(turn.get("at"), reference), str(turn.get("text", "")))
                for turn in turns
                if isinstance(turn, dict)
            ]
            width = max((len(a) for a, _ in rendered), default=0)
            for turn_age, text in rendered:
                lines.append(f'  {turn_age.ljust(width)}  "{text}"')
        lines.append("")
    return "\n".join(lines)


def _extract_last_user_turns(
    row: dict[str, Any], *, last_turns: int
) -> list[dict[str, object]]:
    try:
        session_model = load_chatlas_session_model(row)
    except Exception:
        return []
    user_turns = _visible_user_turns(session_model)
    return user_turns[-last_turns:]


def _visible_user_turns(session_model: dict[str, Any]) -> list[dict[str, object]]:
    chat = session_model.get("chat")
    if not isinstance(chat, dict):
        return []
    events = chat.get("events")
    if not isinstance(events, list):
        return []
    turns: list[dict[str, object]] = []
    for event in events:
        if not isinstance(event, dict) or normal_turn_kind(event) != "user":
            continue
        surfaces = event.get("surfaces")
        if not isinstance(surfaces, dict) or surfaces.get("transcript") != "visible":
            continue
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        text = content_text(payload.get("content"))
        if not text:
            continue
        timestamp = event.get("timestamp")
        turns.append({
            "at": timestamp if isinstance(timestamp, str) else None,
            "text": _collapse_whitespace(text),
        })
    return turns


def _collapse_whitespace(text: str) -> str:
    return " ".join(text.split())


def _truncate(text: str, max_length: int) -> str:
    if len(text) <= max_length:
        return text
    return text[:max_length] + "\u2026"


def _parse_timestamp(value: object) -> datetime | None:
    return parse_interface_timestamp(value)


def _format_relative(value: object, reference: datetime) -> str:
    parsed = _parse_timestamp(value)
    if parsed is None:
        return "(?)"
    seconds = int((reference - parsed).total_seconds())
    if seconds < 0:
        return "(just now)"
    for unit_seconds, suffix in (
        (604800, "w"),
        (86400, "d"),
        (3600, "h"),
        (60, "m"),
    ):
        if seconds >= unit_seconds:
            return f"({seconds // unit_seconds}{suffix} ago)"
    return "(just now)"


def _format_timestamp(value: object) -> str:
    parsed = _parse_timestamp(value)
    if parsed is None:
        return "?"
    return format_local_timestamp(value, display_format="%Y-%m-%d %H:%M")


__all__ = [
    "chatlas_recents",
    "format_chatlas_recents_text",
    "parse_since_date",
    "parse_since_duration",
    "since_window_seconds",
]
