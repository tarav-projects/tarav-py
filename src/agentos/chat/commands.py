from __future__ import annotations

import argparse
import json
import re
import select
import sys
import time
from pathlib import Path
from typing import TextIO

from agentos._core.errors import CliError
from agentos._core.path_validation import validate_string_for_path
from agentos.chat.accounts import (
    chat_account_stats,
    format_chat_account_stats_markdown,
    format_chat_account_stats_usage,
    supported_account_provider_families,
)
from agentos.chat.core import (
    chat_session_resolved_stats,
    chat_session_stats,
    find_chat_session,
    format_chat_session_resolved_stats_markdown,
    format_chat_session_stats_markdown,
    list_chat_sessions,
    supported_provider_families,
)
from agentos.chat.extractors.claude_code import extract_dialog_from_claude_code_session
from agentos.chat.extractors.common import DialogTurn
from agentos.chat.extractors.codex import extract_dialog_from_codex_rollout
from agentos.chat.extractors.copilot_cli import (
    extract_dialog_from_copilot_cli_session,
    infer_copilot_cli_session_id_from_path,
    load_copilot_cli_events,
)
from agentos.chat.extractors.gemini_cli import (
    extract_dialog_from_gemini_cli_session,
    load_gemini_cli_session_data,
)
from agentos.chat.extractors.opencode import (
    extract_dialog_from_opencode_session,
    resolve_opencode_db_path,
)
from agentos.chat.extractors.openclaw import (
    extract_dialog_from_openclaw_session,
    infer_openclaw_session_id_from_path,
    load_openclaw_session_records,
)
from agentos.chat.extractors import extract_chat_session
from agentos.chat.sessions import coerce_timestamp


_CHAT_PROVIDER_CHOICES = tuple(provider_family.family for provider_family in supported_provider_families())
_CHAT_ACCOUNTS_PROVIDER_CHOICES = tuple(
    provider_family.family for provider_family in supported_account_provider_families()
)
_DURATION_RE = re.compile(r"^(?P<value>\d+)(?P<unit>[smhdw]?)$")
_CHAT_ACCOUNTS_LOOP_INTERVAL_SEC = 60.0
_CHAT_ACCOUNTS_LOOP_REFRESHING_MESSAGE = "[loop] refreshing..."


def _normalize_session_limit(limit: int | None) -> int | None:
    if limit is None:
        return None
    if limit < 1:
        raise CliError("session limit must be greater than 0")
    return limit


def _normalize_updated_since(value: str | None) -> float | None:
    if value is None:
        return None

    normalized = value.strip().lower()
    match = _DURATION_RE.fullmatch(normalized)
    if match is None:
        raise CliError("updated-since must be an integer with optional unit s|m|h|d|w, e.g. 72h or 3d")

    amount = int(match.group("value"))
    if amount < 1:
        raise CliError("updated-since must be greater than 0")

    unit = match.group("unit") or "s"
    multiplier = {
        "s": 1,
        "m": 60,
        "h": 60 * 60,
        "d": 24 * 60 * 60,
        "w": 7 * 24 * 60 * 60,
    }[unit]
    return time.time() - (amount * multiplier)


def _normalize_session_query(query: str) -> str:
    normalized = query.strip()
    if normalized.startswith("agentos://chat-session/"):
        if not normalized[len("agentos://chat-session/"):]:
            raise CliError("session query must not be empty")
        return normalized
    return validate_string_for_path(normalized, field_name="session query")


def _cmd_chat_session_list(args: argparse.Namespace) -> int:
    user_contain = args.user_contain
    limit = _normalize_session_limit(args.limit)
    payload = list_chat_sessions(
        sort=args.sort,
        full_output=args.full_output,
        limit=None if user_contain is not None else limit,
        providers=tuple(args.providers) if args.providers else None,
        extractable_only=args.extractable,
        updated_after=_normalize_updated_since(args.updated_since),
    )
    if user_contain is not None:
        payload = _filter_payload_by_user_contain(payload, query=user_contain, limit=limit)
    if args.output_format == "card":
        print(_format_chat_session_list_card(payload, now=time.time()))
        return 0
    print(json.dumps(payload, indent=2))
    return 0


def _cmd_chat_session_find(args: argparse.Namespace) -> int:
    query = _normalize_session_query(args.query)
    payload = find_chat_session(
        query,
        include_artifacts=args.artifacts,
        include_grep=args.grep,
        full_output=args.full_output,
    )
    print(json.dumps(payload, indent=2))
    return 0


def _cmd_chat_session_stats(args: argparse.Namespace) -> int:
    providers = tuple(args.providers) if args.providers else None
    if args.session_query is not None:
        payload = chat_session_resolved_stats(
            _normalize_session_query(args.session_query),
            providers=providers,
        )
        if args.output_format == "markdown":
            print(format_chat_session_resolved_stats_markdown(payload))
            return 0
        print(json.dumps(payload, indent=2))
        return 0

    payload = chat_session_stats(
        full_output=args.full_output,
        providers=providers,
    )
    if args.output_format == "markdown":
        print(format_chat_session_stats_markdown(payload))
        return 0
    print(json.dumps(payload, indent=2))
    return 0


def _normalize_optional_session_query(
    session_query: str | None,
    *,
    file_path: str | None,
) -> str | None:
    if session_query is None:
        if file_path is not None:
            return None
        raise CliError("session query is required unless --file is provided")

    return _normalize_session_query(session_query)


def _cmd_chat_session_extract(args: argparse.Namespace) -> int:
    session_query = _normalize_optional_session_query(args.session_query, file_path=args.file_path)
    output = extract_chat_session(
        session_query=session_query,
        file_path=args.file_path,
        output_format=args.output_format,
        raw=args.raw,
    )
    print(output)
    return 0


def _cmd_chat_accounts_stats(args: argparse.Namespace) -> int:
    if args.loop:
        return _loop_chat_accounts_stats(args)

    print(_render_chat_accounts_stats_output(args))
    return 0


def _render_chat_accounts_stats_output(args: argparse.Namespace) -> str:
    payload = chat_account_stats(
        instance_ids=tuple(args.instance_ids) if args.instance_ids else None,
        providers=tuple(args.providers) if args.providers else None,
        refresh_usage=args.refresh_usage,
        full_output=args.full_output,
    )
    if args.output_format == "markdown":
        return format_chat_account_stats_markdown(payload)
    if args.output_format == "usage":
        return format_chat_account_stats_usage(payload)
    return json.dumps(payload, indent=2)


def _loop_chat_accounts_stats(
    args: argparse.Namespace,
    *,
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
    interval_sec: float = _CHAT_ACCOUNTS_LOOP_INTERVAL_SEC,
    wait_for_trigger: Callable[[float, TextIO], None] | None = None,
) -> int:
    input_stream = input_stream or sys.stdin
    output_stream = output_stream or sys.stdout
    wait_for_trigger = wait_for_trigger or _wait_for_chat_accounts_loop_trigger

    first_iteration = True
    while True:
        rendered_output = _render_chat_accounts_stats_output(args)

        if _stream_is_tty(output_stream):
            _clear_terminal_screen(output_stream)
        elif not first_iteration:
            output_stream.write("\n")

        output_stream.write(rendered_output)
        output_stream.write(
            f"\n\n[loop] refreshes every {int(interval_sec)}s; press Enter to refresh now; Ctrl-C to stop\n"
        )
        output_stream.flush()
        first_iteration = False

        try:
            wait_for_trigger(interval_sec, input_stream)
        except KeyboardInterrupt:
            return 0

        output_stream.write(_CHAT_ACCOUNTS_LOOP_REFRESHING_MESSAGE + "\n")
        output_stream.flush()


def _wait_for_chat_accounts_loop_trigger(interval_sec: float, input_stream: TextIO) -> None:
    if interval_sec <= 0:
        return

    if not _stream_is_tty(input_stream):
        time.sleep(interval_sec)
        return

    ready, _, _ = select.select([input_stream], [], [], interval_sec)
    if not ready:
        return

    input_stream.readline()


def _stream_is_tty(stream: TextIO) -> bool:
    isatty = getattr(stream, "isatty", None)
    if isatty is None:
        return False
    try:
        return bool(isatty())
    except OSError:
        return False


def _clear_terminal_screen(output_stream: TextIO) -> None:
    output_stream.write("\033[2J\033[H")
    output_stream.flush()


def _filter_payload_by_user_contain(
    payload: dict[str, object],
    *,
    query: str,
    limit: int | None = None,
) -> dict[str, object]:
    raw_sessions = payload.get("sessions")
    if not isinstance(raw_sessions, list):
        return payload

    query_lower = query.lower()
    filtered: list[dict[str, object]] = []
    for session in raw_sessions:
        if not isinstance(session, dict):
            continue
        if _session_user_messages_contain(session, query_lower):
            filtered.append(session)
            if limit is not None and len(filtered) >= limit:
                break

    selection = payload.get("selection")
    normalized_selection = dict(selection) if isinstance(selection, dict) else {}
    filters = normalized_selection.get("filters")
    normalized_filters = dict(filters) if isinstance(filters, dict) else {}
    normalized_filters["user_contain"] = query
    normalized_filters["limit"] = limit
    normalized_selection["filters"] = normalized_filters

    return {
        **payload,
        "selection": normalized_selection,
        "sessions": filtered,
        "session_count": len(filtered),
    }


def _session_user_messages_contain(session: dict[str, object], query_lower: str) -> bool:
    turns = _load_session_user_turns(session)
    for turn in turns:
        if query_lower in turn.text.lower():
            return True
    return False


def _load_session_user_turns(session: dict[str, object]) -> list[DialogTurn]:
    path = _primary_artifact_path(session)
    if path is None or not path.is_file():
        return []

    provider = _string_or_none(session.get("provider"))
    session_id = _string_or_none(session.get("session_id")) or ""

    try:
        turns = _load_session_turns(provider=provider, path=path, session_id=session_id)
    except (CliError, OSError, json.JSONDecodeError):
        return []

    return [turn for turn in turns if turn.role == "user"]


def _load_session_turns(
    *,
    provider: str | None,
    path: Path,
    session_id: str,
) -> list[DialogTurn]:
    if provider == "claude-code":
        if path.suffix == ".jsonl":
            return extract_dialog_from_claude_code_session(path, raw=False)
        return []

    if provider == "codex":
        return extract_dialog_from_codex_rollout(path, raw=False)

    if provider == "copilot-cli":
        events = load_copilot_cli_events(path)
        return extract_dialog_from_copilot_cli_session(
            events=events,
            session_id=infer_copilot_cli_session_id_from_path(path) or session_id,
            raw=False,
        )

    if provider == "gemini-cli":
        session_data = load_gemini_cli_session_data(path)
        return extract_dialog_from_gemini_cli_session(
            session_data=session_data,
            session_id=str(session_data.get("sessionId") or session_id),
            raw=False,
        )

    if provider == "openclaw":
        records = load_openclaw_session_records(path)
        return extract_dialog_from_openclaw_session(
            records=records,
            session_id=infer_openclaw_session_id_from_path(path) or session_id,
            raw=False,
        )

    if provider == "opencode":
        db_path = resolve_opencode_db_path(path)
        return extract_dialog_from_opencode_session(
            db_path=db_path,
            session_id=session_id,
            raw=False,
        )

    return []


def _format_chat_session_list_card(payload: dict[str, object], *, now: float) -> str:
    raw_sessions = payload.get("sessions")
    sessions = raw_sessions if isinstance(raw_sessions, list) else []
    separator = "────────────────────────────────────────"
    cards: list[str] = []

    for raw_session in sessions:
        if not isinstance(raw_session, dict):
            continue
        created_at, preview = _summarize_session_for_card_output(raw_session)
        updated_at = coerce_timestamp(raw_session.get("updated_at"))
        provider = _string_or_none(raw_session.get("provider")) or "-"
        session_id = _string_or_none(raw_session.get("session_id")) or "-"
        card_lines = [
            separator,
            provider,
            session_id,
            "",
            f"created {_format_relative_age(created_at, now=now)}",
            f"updated {_format_relative_age(updated_at, now=now)}",
            "",
            preview,
        ]
        cards.append("\n".join(card_lines))

    if not cards:
        return "(no sessions)"
    return "\n\n".join(cards)


def _summarize_session_for_card_output(session: dict[str, object]) -> tuple[float | None, str]:
    path = _primary_artifact_path(session)
    display_name = _string_or_none(session.get("display_name"))
    session_id = _string_or_none(session.get("session_id")) or "-"

    preview: str | None = None
    created_at = coerce_timestamp(session.get("created_at"))
    if path is not None:
        loaded_created_at, preview = _load_card_session_context(
            provider=_string_or_none(session.get("provider")),
            path=path,
            session_id=session_id,
        )
        created_at = loaded_created_at or created_at

    if preview is None:
        preview = display_name or session_id
    return created_at, _truncate_preview(preview)


def _load_card_session_context(
    *,
    provider: str | None,
    path: Path,
    session_id: str,
) -> tuple[float | None, str | None]:
    try:
        if provider == "codex":
            turns = extract_dialog_from_codex_rollout(path, raw=False)
            return _created_and_preview_from_turns(turns)

        if provider == "claude-code":
            if path.suffix == ".jsonl":
                turns = extract_dialog_from_claude_code_session(path, raw=False)
                return _created_and_preview_from_turns(turns)
            if path.suffix == ".json":
                obj = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
                if isinstance(obj, dict):
                    created_at = coerce_timestamp(obj.get("createdAt")) or coerce_timestamp(obj.get("lastActivityAt"))
                    preview = _string_or_none(obj.get("title"))
                    return created_at, preview

        if provider == "copilot-cli":
            events = load_copilot_cli_events(path)
            turns = extract_dialog_from_copilot_cli_session(
                events=events,
                session_id=infer_copilot_cli_session_id_from_path(path) or session_id,
                raw=False,
            )
            return _created_and_preview_from_turns(turns)

        if provider == "gemini-cli":
            session_data = load_gemini_cli_session_data(path)
            turns = extract_dialog_from_gemini_cli_session(
                session_data=session_data,
                session_id=str(session_data.get("sessionId") or session_id),
                raw=False,
            )
            created_at, preview = _created_and_preview_from_turns(turns)
            return created_at or coerce_timestamp(session_data.get("startTime")), preview

        if provider == "openclaw":
            records = load_openclaw_session_records(path)
            turns = extract_dialog_from_openclaw_session(
                records=records,
                session_id=infer_openclaw_session_id_from_path(path) or session_id,
                raw=False,
            )
            return _created_and_preview_from_turns(turns)
    except (CliError, OSError, json.JSONDecodeError):
        return None, None

    return None, None


def _created_and_preview_from_turns(turns: list[object]) -> tuple[float | None, str | None]:
    created_at: float | None = None
    preview: str | None = None

    for turn in turns:
        timestamp = coerce_timestamp(getattr(turn, "timestamp", None))
        if timestamp is not None and created_at is None:
            created_at = timestamp

        role = getattr(turn, "role", None)
        text = _string_or_none(getattr(turn, "text", None))
        if not text:
            continue
        if preview is None:
            preview = text
        if role == "user":
            preview = text
            break

    return created_at, preview


def _primary_artifact_path(session: dict[str, object]) -> Path | None:
    raw_artifact = session.get("primary_backing_artifact")
    if not isinstance(raw_artifact, dict):
        return None
    path_text = _string_or_none(raw_artifact.get("path"))
    if path_text is None:
        return None
    return Path(path_text)


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped:
            return stripped
    return None


def _truncate_preview(text: str, *, max_length: int = 120) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= max_length:
        return normalized
    return normalized[: max_length - 3].rstrip() + "..."


def _format_relative_age(timestamp: float | None, *, now: float) -> str:
    if timestamp is None:
        return "-"

    delta_seconds = max(0, int(now - timestamp))
    if delta_seconds < 60:
        return "just now"

    units = (
        ("year", 365 * 24 * 60 * 60),
        ("month", 30 * 24 * 60 * 60),
        ("week", 7 * 24 * 60 * 60),
        ("day", 24 * 60 * 60),
        ("hour", 60 * 60),
        ("minute", 60),
    )
    for unit_name, unit_seconds in units:
        if delta_seconds >= unit_seconds:
            value = delta_seconds // unit_seconds
            suffix = "" if value == 1 else "s"
            return f"{value} {unit_name}{suffix} ago"
    return "just now"


def register_chat_commands(subparsers: argparse._SubParsersAction) -> None:
    chat_parser = subparsers.add_parser(
        "chat",
        help="Provider-aware chat workflow utilities.",
    )
    chat_subparsers = chat_parser.add_subparsers(dest="chat_command", required=True)

    session_parser = chat_subparsers.add_parser(
        "session",
        help="List, find, and extract chat sessions across supported providers.",
    )
    session_subparsers = session_parser.add_subparsers(
        dest="chat_session_command",
        required=True,
    )

    list_parser = session_subparsers.add_parser(
        "list",
        help="List chat sessions with shared metadata across supported providers.",
    )
    list_parser.add_argument(
        "--sort",
        choices=("lexical", "newest", "oldest"),
        default="lexical",
        help="Sort order for returned sessions across all providers (default: lexical).",
    )
    list_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of sessions to return overall.",
    )
    list_parser.add_argument(
        "--provider",
        choices=_CHAT_PROVIDER_CHOICES,
        action="append",
        dest="providers",
        help="Restrict listing to a provider. Repeat to include multiple providers.",
    )
    list_parser.add_argument(
        "--full-output",
        action="store_true",
        help="Include provider diagnostics even for providers with no matching sessions.",
    )
    list_parser.add_argument(
        "--extractable",
        action="store_true",
        help="Keep only sessions with an extractable primary artifact.",
    )
    list_parser.add_argument(
        "--updated-since",
        default=None,
        help="Keep only sessions updated within the given lookback, e.g. 72h or 3d.",
    )
    list_parser.add_argument(
        "--user-contain",
        default=None,
        dest="user_contain",
        help="Keep only sessions where at least one user message contains the given text (case-insensitive).",
    )
    list_parser.add_argument(
        "--output",
        choices=("card", "json"),
        default="card",
        dest="output_format",
        help="Output format (default: card).",
    )
    list_parser.set_defaults(handler=_cmd_chat_session_list)

    stats_parser = session_subparsers.add_parser(
        "stats",
        help="Summarize session inventory, or one resolved session when given a query.",
    )
    stats_parser.add_argument(
        "session_query",
        nargs="?",
        help="Optional session query string. When provided, returns stats for one resolved session.",
    )
    stats_parser.add_argument(
        "--provider",
        choices=_CHAT_PROVIDER_CHOICES,
        action="append",
        dest="providers",
        help="Restrict stats to a provider. Repeat to include multiple providers.",
    )
    stats_parser.add_argument(
        "--output",
        choices=("json", "markdown"),
        default="json",
        dest="output_format",
        help="Output format (default: json).",
    )
    stats_parser.add_argument(
        "--full-output",
        action="store_true",
        help="Keep zero-session providers in stats.by_provider.",
    )
    stats_parser.set_defaults(handler=_cmd_chat_session_stats)

    find_parser = session_subparsers.add_parser(
        "find",
        help="Search supported provider homes using a provider-agnostic session query.",
    )
    find_parser.add_argument(
        "query",
        help="Session query string. Each provider tries all matching strategies it supports.",
    )
    find_parser.add_argument(
        "--artifacts",
        action="store_true",
        help="Expand matched sessions with their canonical backing artifacts.",
    )
    find_parser.add_argument(
        "--grep",
        action="store_true",
        help="Include grep-based search evidence as separate search_findings output.",
    )
    find_parser.add_argument(
        "--full-output",
        action="store_true",
        help="Include provider diagnostics even for providers with no matched sessions.",
    )
    find_parser.set_defaults(handler=_cmd_chat_session_find)

    extract_parser = session_subparsers.add_parser(
        "extract",
        help="Extract dialog from a session matched through the provider-agnostic query resolver.",
    )
    extract_parser.add_argument(
        "session_query",
        nargs="?",
        help="Session query string. Each provider tries all matching strategies it supports.",
    )
    extract_parser.add_argument(
        "--format",
        choices=("jsonl", "markdown"),
        default="jsonl",
        dest="output_format",
        help="Output format (default: jsonl).",
    )
    extract_parser.add_argument(
        "--file",
        default=None,
        dest="file_path",
        help="Session artifact path directly; extractor is inferred from file provenance.",
    )
    extract_parser.add_argument(
        "--raw",
        action="store_true",
        help="Skip all filtering; emit every content block verbatim.",
    )
    extract_parser.set_defaults(handler=_cmd_chat_session_extract)

    accounts_parser = chat_subparsers.add_parser(
        "accounts",
        help="Query configured account status across supported providers.",
    )
    accounts_subparsers = accounts_parser.add_subparsers(
        dest="chat_accounts_command",
        required=True,
    )

    accounts_stats_parser = accounts_subparsers.add_parser(
        "stats",
        help="Aggregate configured account status and usage checks across supported providers.",
    )
    accounts_stats_parser.add_argument(
        "instance_ids",
        nargs="*",
        help="Optional configured account instance ids to query. Defaults to all configured instances.",
    )
    accounts_stats_parser.add_argument(
        "--provider",
        choices=_CHAT_ACCOUNTS_PROVIDER_CHOICES,
        action="append",
        dest="providers",
        help="Restrict checks to a provider. Repeat to include multiple providers.",
    )
    accounts_stats_parser.add_argument(
        "--output",
        choices=("json", "markdown", "usage"),
        default="json",
        dest="output_format",
        help="Output format (default: json).",
    )
    accounts_stats_parser.add_argument(
        "--full-output",
        action="store_true",
        help="Keep zero-account provider diagnostics in the providers array.",
    )
    accounts_stats_parser.add_argument(
        "--refresh-usage",
        action="store_true",
        help=(
            "Allow provider adapters to issue live refresh requests for usage data when needed "
            "(for example Claude Code)."
        ),
    )
    accounts_stats_parser.add_argument(
        "--loop",
        action="store_true",
        help="Refresh forever every 60 seconds; press Enter to refresh immediately.",
    )
    accounts_stats_parser.set_defaults(handler=_cmd_chat_accounts_stats)
