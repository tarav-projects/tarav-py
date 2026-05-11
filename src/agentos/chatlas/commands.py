from __future__ import annotations

import argparse
import sys

from agentos.agent._cli_common import format_json_output, normalize_updated_since, optional_string_tuple
from agentos.chatlas.core import (
    chatlas_query,
    chatlas_raw_export,
    chatlas_raw_paths,
    chatlas_stats,
    chatlas_update,
    format_chatlas_stats_markdown,
)
from agentos.chatlas.session_model import chatlas_export_session_model
from agentos.chatlas.raw import supported_chatlas_provider_families

_CHATLAS_PROVIDER_CHOICES = tuple(
    provider_family.family for provider_family in supported_chatlas_provider_families()
)
_CHATLAS_UPDATE_VERBOSE_MODES = ("progress", "quiet")
_CHATLAS_UPDATE_OUTPUT_MODES = ("none", "json")


def _chatlas_update_progress_handler(verbose_mode: str):
    if verbose_mode == "quiet":
        return None
    return lambda message: print(message, file=sys.stderr, flush=True)


def _emit_chatlas_update_output(*, payload: dict[str, object], output_mode: str) -> None:
    if output_mode == "none":
        return
    if output_mode == "json":
        print(format_json_output(payload))
        return
    raise AssertionError(f"unsupported chatlas update output mode: {output_mode}")


def _cmd_chatlas_update(args: argparse.Namespace) -> int:
    disable_cache = args.disable_cache
    payload = chatlas_update(
        providers=optional_string_tuple(args.providers),
        scan_cache_enabled=not disable_cache and args.scan_cache == "true",
        session_index_cache_enabled=not disable_cache and args.session_index_cache == "true",
        progress=_chatlas_update_progress_handler(args.verbose_mode),
    )
    _emit_chatlas_update_output(payload=payload, output_mode=args.output_mode)
    return 0


def _cmd_chatlas_stats(args: argparse.Namespace) -> int:
    payload = chatlas_stats(
        providers=optional_string_tuple(args.providers),
        full_output=args.full_output,
    )
    if args.output_format == "markdown":
        print(format_chatlas_stats_markdown(payload))
        return 0
    print(format_json_output(payload))
    return 0


def _cmd_chatlas_query(args: argparse.Namespace) -> int:
    payload = chatlas_query(
        query=args.query,
        providers=optional_string_tuple(args.providers),
        instances=optional_string_tuple(args.instances),
        sort=args.sort,
        limit=args.limit,
        extractable_only=args.extractable,
        updated_after=normalize_updated_since(args.updated_since),
        include_match=args.include_match,
        include_artifacts=args.include_artifacts,
        include_provider_stats=args.include_provider_stats,
        compact=args.compact,
    )
    print(format_json_output(payload))
    return 0


def _cmd_chatlas_export(args: argparse.Namespace) -> int:
    payload = chatlas_export_session_model(
        query=args.query,
        providers=optional_string_tuple(args.providers),
        output_format=args.output_format,
        view=args.view,
    )
    print(format_json_output(payload))
    return 0


def _cmd_chatlas_raw_path(args: argparse.Namespace) -> int:
    payload = chatlas_raw_paths(
        query=args.query,
        providers=optional_string_tuple(args.providers),
    )
    if args.output_format == "json":
        print(format_json_output(payload))
        return 0
    for path in payload["paths"]:
        print(path)
    return 0


def _cmd_chatlas_raw_export(args: argparse.Namespace) -> int:
    payload = chatlas_raw_export(
        query=args.query,
        providers=optional_string_tuple(args.providers),
    )
    print(format_json_output(payload))
    return 0


def register_chatlas_commands(subparsers: argparse._SubParsersAction) -> None:
    chatlas_parser = subparsers.add_parser(
        "chatlas",
        help="Git-backed chat dataset service.",
    )
    chatlas_subparsers = chatlas_parser.add_subparsers(dest="chatlas_command", required=True)

    update_parser = chatlas_subparsers.add_parser(
        "update",
        help="Refresh the Chatlas raw dataset layer from configured provider home.",
    )
    update_parser.add_argument(
        "--provider",
        choices=_CHATLAS_PROVIDER_CHOICES,
        action="append",
        dest="providers",
        help="Restrict the update run to a provider family. Repeat to include multiple providers.",
    )
    update_parser.add_argument(
        "--verbose-mode",
        choices=_CHATLAS_UPDATE_VERBOSE_MODES,
        default="progress",
        help="Progress feedback mode: `progress` prints live update messages to stderr; `quiet` disables them (default: progress).",
    )
    update_parser.add_argument(
        "--output-mode",
        choices=_CHATLAS_UPDATE_OUTPUT_MODES,
        default="none",
        help="Final command output mode: `none` prints nothing after the update; `json` prints the update payload (default: none).",
    )
    update_parser.add_argument(
        "--disable-cache",
        action="store_true",
        help="Disable all Chatlas update caches. Overrides `--scan-cache` and `--session-index-cache`.",
    )
    update_parser.add_argument(
        "--scan-cache",
        choices=("true", "false"),
        default="true",
        help="Use the local raw-scan cache during archive scans (default: true).",
    )
    update_parser.add_argument(
        "--session-index-cache",
        choices=("true", "false"),
        default="true",
        help="Use the local session index cache during session index materialization (default: true).",
    )
    update_parser.set_defaults(handler=_cmd_chatlas_update)

    stats_parser = chatlas_subparsers.add_parser(
        "stats",
        help="Summarize the Chatlas session index.",
    )
    stats_parser.add_argument(
        "--provider",
        choices=_CHATLAS_PROVIDER_CHOICES,
        action="append",
        dest="providers",
        help="Restrict stats to a provider family. Repeat to include multiple providers.",
    )
    stats_parser.add_argument(
        "--full-output",
        action="store_true",
        help="Keep zero-session providers in stats.by_provider.",
    )
    stats_parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        dest="output_format",
        help="Output format (default: markdown).",
    )
    stats_parser.set_defaults(handler=_cmd_chatlas_stats)

    query_parser = chatlas_subparsers.add_parser(
        "query",
        help="Query Chatlas sessions by session index metadata.",
    )
    query_parser.add_argument(
        "query",
        nargs="?",
        help="Exact query value matched against URI, identity hash, instance, session id, display name, fingerprint, and native fields.",
    )
    query_parser.add_argument(
        "--provider",
        choices=_CHATLAS_PROVIDER_CHOICES,
        action="append",
        dest="providers",
        help="Restrict query to a provider family. Repeat to include multiple providers.",
    )
    query_parser.add_argument(
        "--profile",
        action="append",
        dest="instances",
        help="Restrict query to a resolved Chatlas instance name. Repeat to include multiple instances.",
    )
    query_parser.add_argument(
        "--sort",
        choices=("lexical", "newest", "oldest"),
        default="lexical",
        help="Sort order for returned sessions (default: lexical).",
    )
    query_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of sessions to return.",
    )
    query_parser.add_argument(
        "--extractable",
        action="store_true",
        help="Keep only sessions with an extractable primary artifact.",
    )
    query_parser.add_argument(
        "--updated-since",
        default=None,
        help="Keep only sessions updated within the given lookback, e.g. 72h or 3d.",
    )
    query_parser.add_argument(
        "--compact",
        action="store_true",
        help="Return compact identifier-oriented session rows instead of the full session index payload.",
    )
    query_parser.add_argument(
        "--include-match",
        action="store_true",
        help="Include exact-match details for identity queries.",
    )
    query_parser.add_argument(
        "--include-artifacts",
        action="store_true",
        help="Include full backing_artifacts rows in session output.",
    )
    query_parser.add_argument(
        "--include-provider-stats",
        action="store_true",
        help="Include provider-specific stats for each matched session.",
    )
    query_parser.set_defaults(handler=_cmd_chatlas_query)

    export_parser = chatlas_subparsers.add_parser(
        "export",
        help="Export one Chatlas session as the standard session model JSON object.",
    )
    export_parser.add_argument(
        "query",
        help="Exact query value matched against URI, identity hash, session id, display name, fingerprint, and native fields.",
    )
    export_parser.add_argument(
        "--provider",
        choices=_CHATLAS_PROVIDER_CHOICES,
        action="append",
        dest="providers",
        help="Restrict export to a provider family. Repeat to include multiple providers.",
    )
    export_parser.add_argument(
        "--format",
        choices=("json",),
        default="json",
        dest="output_format",
        help="Output format. Chatlas export supports json only.",
    )
    export_parser.add_argument(
        "--view",
        choices=("full", "transcript", "user", "replay", "events", "zip-transcript"),
        default="full",
        help="Export view projection (default: full).",
    )
    export_parser.set_defaults(handler=_cmd_chatlas_export)

    raw_parser = chatlas_subparsers.add_parser(
        "raw",
        help="Inspect archived provider-native raw artifacts.",
    )
    raw_subparsers = raw_parser.add_subparsers(
        dest="chatlas_raw_command",
        required=True,
    )

    raw_path_parser = raw_subparsers.add_parser(
        "path",
        help="Print backing raw artifact paths for one Chatlas session.",
    )
    raw_path_parser.add_argument(
        "query",
        help="Exact query value matched against URI, identity hash, session id, display name, fingerprint, and native fields.",
    )
    raw_path_parser.add_argument(
        "--provider",
        choices=_CHATLAS_PROVIDER_CHOICES,
        action="append",
        dest="providers",
        help="Restrict lookup to a provider family. Repeat to include multiple providers.",
    )
    raw_path_parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        dest="output_format",
        help="Output format (default: text).",
    )
    raw_path_parser.set_defaults(handler=_cmd_chatlas_raw_path)

    raw_export_parser = raw_subparsers.add_parser(
        "export",
        help="Export backing raw artifact contents for one Chatlas session.",
    )
    raw_export_parser.add_argument(
        "query",
        help="Exact query value matched against URI, identity hash, session id, display name, fingerprint, and native fields.",
    )
    raw_export_parser.add_argument(
        "--provider",
        choices=_CHATLAS_PROVIDER_CHOICES,
        action="append",
        dest="providers",
        help="Restrict lookup to a provider family. Repeat to include multiple providers.",
    )
    raw_export_parser.add_argument(
        "--format",
        choices=("json",),
        default="json",
        dest="output_format",
        help="Output format. Raw export supports json only.",
    )
    raw_export_parser.set_defaults(handler=_cmd_chatlas_raw_export)
