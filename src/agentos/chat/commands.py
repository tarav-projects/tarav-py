from __future__ import annotations

import argparse
import json
import re
import time

from agentos._core.errors import CliError
from agentos._core.path_validation import validate_string_for_path
from agentos.chat.core import (
    chat_session_resolved_stats,
    chat_session_stats,
    find_chat_session,
    format_chat_session_resolved_stats_markdown,
    format_chat_session_stats_markdown,
    list_chat_sessions,
    supported_provider_families,
)
from agentos.chat.extractors import extract_chat_session


_CHAT_PROVIDER_CHOICES = tuple(provider_family.family for provider_family in supported_provider_families())
_DURATION_RE = re.compile(r"^(?P<value>\d+)(?P<unit>[smhdw]?)$")


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


def _cmd_chat_session_list(args: argparse.Namespace) -> int:
    payload = list_chat_sessions(
        sort=args.sort,
        full_output=args.full_output,
        limit=_normalize_session_limit(args.limit),
        providers=tuple(args.providers) if args.providers else None,
        extractable_only=args.extractable,
        updated_after=_normalize_updated_since(args.updated_since),
    )
    print(json.dumps(payload, indent=2))
    return 0


def _cmd_chat_session_find(args: argparse.Namespace) -> int:
    query = validate_string_for_path(args.query, field_name="session query")
    payload = find_chat_session(
        query,
        include_grep=args.grep,
        full_output=args.full_output,
    )
    print(json.dumps(payload, indent=2))
    return 0


def _cmd_chat_session_stats(args: argparse.Namespace) -> int:
    providers = tuple(args.providers) if args.providers else None
    if args.session_query is not None:
        payload = chat_session_resolved_stats(
            validate_string_for_path(args.session_query, field_name="session query"),
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

    return validate_string_for_path(session_query, field_name="session query")


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
        help="Sort order for session ids within each provider (default: lexical).",
    )
    list_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of session ids to return per provider.",
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
        help="Keep zero-session providers in the providers array.",
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
        help="Keep zero-session providers in the providers array.",
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
        "--grep",
        action="store_true",
        help="Include grep-based reference matches in addition to canonical direct artifacts.",
    )
    find_parser.add_argument(
        "--full-output",
        action="store_true",
        help="Keep zero-finding providers in the providers array.",
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
