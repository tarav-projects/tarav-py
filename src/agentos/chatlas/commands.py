from __future__ import annotations

import argparse
import json

from agentos.chat.archive import supported_archive_provider_families
from agentos.chatlas.core import chatlas_export, chatlas_query, chatlas_stats, chatlas_update

_CHATLAS_PROVIDER_CHOICES = tuple(
    provider_family.family for provider_family in supported_archive_provider_families()
)


def _cmd_chatlas_update(args: argparse.Namespace) -> int:
    payload = chatlas_update(
        providers=tuple(args.providers) if args.providers else None,
    )
    print(json.dumps(payload, indent=2))
    return 0


def _cmd_chatlas_stats(args: argparse.Namespace) -> int:
    payload = chatlas_stats(
        providers=tuple(args.providers) if args.providers else None,
    )
    print(json.dumps(payload, indent=2))
    return 0


def _cmd_chatlas_query(args: argparse.Namespace) -> int:
    payload = chatlas_query(
        query=args.query,
        text_contain=args.text_contain,
        user_contain=args.user_contain,
        providers=tuple(args.providers) if args.providers else None,
    )
    print(json.dumps(payload, indent=2))
    return 0


def _cmd_chatlas_export(args: argparse.Namespace) -> int:
    print(
        chatlas_export(
            query=args.query,
            providers=tuple(args.providers) if args.providers else None,
            output_format=args.output_format,
        )
    )
    return 0


def register_chatlas_commands(subparsers: argparse._SubParsersAction) -> None:
    chatlas_parser = subparsers.add_parser(
        "chatlas",
        help="Git-backed chat dataset service.",
    )
    chatlas_subparsers = chatlas_parser.add_subparsers(dest="chatlas_command", required=True)

    update_parser = chatlas_subparsers.add_parser(
        "update",
        help="Refresh the Chatlas raw dataset layer from configured provider homes.",
    )
    update_parser.add_argument(
        "--provider",
        choices=_CHATLAS_PROVIDER_CHOICES,
        action="append",
        dest="providers",
        help="Restrict the update run to a provider family. Repeat to include multiple providers.",
    )
    update_parser.set_defaults(handler=_cmd_chatlas_update)

    stats_parser = chatlas_subparsers.add_parser(
        "stats",
        help="Summarize the normalized Chatlas dataset.",
    )
    stats_parser.add_argument(
        "--provider",
        choices=_CHATLAS_PROVIDER_CHOICES,
        action="append",
        dest="providers",
        help="Restrict stats to a provider family. Repeat to include multiple providers.",
    )
    stats_parser.set_defaults(handler=_cmd_chatlas_stats)

    query_parser = chatlas_subparsers.add_parser(
        "query",
        help="Query normalized Chatlas sessions using identity fields and transcript-content filters.",
    )
    query_parser.add_argument(
        "query",
        nargs="?",
        help="Exact query value matched against URI, session id, display name, fingerprint, and native fields.",
    )
    query_parser.add_argument(
        "--text-contain",
        default=None,
        dest="text_contain",
        help="Case-insensitive substring that must appear in at least one derived transcript turn.",
    )
    query_parser.add_argument(
        "--user-contain",
        default=None,
        dest="user_contain",
        help="Case-insensitive substring that must appear in at least one user transcript turn.",
    )
    query_parser.add_argument(
        "--provider",
        choices=_CHATLAS_PROVIDER_CHOICES,
        action="append",
        dest="providers",
        help="Restrict query to a provider family. Repeat to include multiple providers.",
    )
    query_parser.set_defaults(handler=_cmd_chatlas_query)

    export_parser = chatlas_subparsers.add_parser(
        "export",
        help="Export one normalized Chatlas session as a derived transcript.",
    )
    export_parser.add_argument(
        "query",
        help="Exact query value matched against URI, session id, display name, fingerprint, and native fields.",
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
        choices=("jsonl", "markdown"),
        default="markdown",
        dest="output_format",
        help="Transcript output format (default: markdown).",
    )
    export_parser.set_defaults(handler=_cmd_chatlas_export)
