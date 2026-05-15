from __future__ import annotations

import argparse
import sys

from agentos.agent._cli_common import format_json_output, optional_string_tuple
from agentos.providers import canonical_provider_families
from agentos.chatlas.core import (
    chatlas_index_doctor,
    chatlas_index_query,
    chatlas_index_redo,
    chatlas_index_reset,
    chatlas_index_update,
    chatlas_query,
    chatlas_raw_export,
    chatlas_raw_paths,
    chatlas_stats,
    chatlas_update,
    format_chatlas_doctor_markdown,
    format_chatlas_stats_markdown,
)
from agentos.chatlas.session_model import chatlas_export_session_model
from agentos.chatlas.raw import supported_chatlas_provider_families
from agentos.chatlas.views import (
    chatlas_produce,
    chatlas_run_produce,
    chatlas_views_commit,
    chatlas_views_get,
    chatlas_views_list,
    chatlas_views_path,
    chatlas_views_stage,
    chatlas_views_status,
)

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


def _cmd_chatlas_index_update(args: argparse.Namespace) -> int:
    disable_cache = args.disable_cache
    payload = chatlas_index_update(
        providers=optional_string_tuple(args.providers),
        scan_cache_enabled=not disable_cache and args.scan_cache == "true",
        session_index_cache_enabled=not disable_cache and args.session_index_cache == "true",
        progress=_chatlas_update_progress_handler(args.verbose_mode),
    )
    _emit_chatlas_update_output(payload=payload, output_mode=args.output_mode)
    return 0


def _cmd_chatlas_index_reset(args: argparse.Namespace) -> int:
    payload = chatlas_index_reset(
        progress=_chatlas_update_progress_handler(args.verbose_mode),
    )
    _emit_chatlas_update_output(payload=payload, output_mode=args.output_mode)
    return 0


def _cmd_chatlas_index_redo(args: argparse.Namespace) -> int:
    payload = chatlas_index_redo(
        providers=optional_string_tuple(args.providers),
        progress=_chatlas_update_progress_handler(args.verbose_mode),
    )
    _emit_chatlas_update_output(payload=payload, output_mode=args.output_mode)
    return 0


def _cmd_chatlas_index_query(args: argparse.Namespace) -> int:
    payload = chatlas_index_query(**_chatlas_index_selector_kwargs(args))
    print(format_json_output(payload))
    return 0


def _cmd_chatlas_index_doctor(args: argparse.Namespace) -> int:
    payload = chatlas_index_doctor()
    if args.output_format == "markdown":
        print(format_chatlas_doctor_markdown(payload))
    else:
        print(format_json_output(payload))
    return 0 if payload.get("status") == "ok" else 1


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
        uri=args.uri,
        identity_hash=args.identity_hash,
        providers=optional_string_tuple(args.providers),
        session_id=args.session_id,
        display_name=args.display_name,
        sort=args.sort,
        limit=args.limit,
        scan_limit=args.scan_limit,
        extractable_only=args.extractable,
        updated_after=args.updated_after,
        raw_contains=optional_string_tuple(args.raw_contains),
        user_contains=optional_string_tuple(args.user_contains),
        assistant_contains=optional_string_tuple(args.assistant_contains),
        message_contains=optional_string_tuple(args.message_contains),
    )
    print(format_json_output(payload))
    return 0


def _cmd_chatlas_export(args: argparse.Namespace) -> int:
    payload = chatlas_export_session_model(
        **_chatlas_index_selector_kwargs(args),
        output_format=args.output_format,
        view=args.view,
    )
    print(format_json_output(payload))
    return 0


def _cmd_chatlas_raw_path(args: argparse.Namespace) -> int:
    payload = chatlas_raw_paths(**_chatlas_index_selector_kwargs(args))
    if args.output_format == "json":
        print(format_json_output(payload))
        return 0
    for path in payload["paths"]:
        print(path)
    return 0


def _cmd_chatlas_raw_export(args: argparse.Namespace) -> int:
    payload = chatlas_raw_export(
        **_chatlas_index_selector_kwargs(args),
    )
    print(format_json_output(payload))
    return 0


def _cmd_chatlas_views_list(args: argparse.Namespace) -> int:
    payload = chatlas_views_list()
    print(format_json_output(payload))
    return 0


def _cmd_chatlas_views_get(args: argparse.Namespace) -> int:
    payload = chatlas_views_get(
        view=args.view,
        explain=args.explain,
        **_chatlas_index_selector_kwargs(args),
    )
    print(format_json_output(payload))
    return 0


def _cmd_chatlas_views_status(args: argparse.Namespace) -> int:
    payload = chatlas_views_status(
        view=args.view,
        explain=args.explain,
        **_chatlas_index_selector_kwargs(args),
    )
    print(format_json_output(payload))
    return 0


def _cmd_chatlas_views_path(args: argparse.Namespace) -> int:
    payload = chatlas_views_path(
        view=args.view,
        explain=args.explain,
        **_chatlas_index_selector_kwargs(args),
    )
    if args.output_format == "json":
        print(format_json_output(payload))
        return 0
    path = payload.get("path")
    if isinstance(path, str):
        print(path)
    return 0


def _cmd_chatlas_views_stage(args: argparse.Namespace) -> int:
    payload = chatlas_views_stage(
        view=args.view,
        **_chatlas_index_selector_kwargs(args),
    )
    print(format_json_output(payload))
    return 0


def _cmd_chatlas_views_commit(args: argparse.Namespace) -> int:
    payload = chatlas_views_commit(stage_id=args.stage_id)
    print(format_json_output(payload))
    return 0


def _cmd_chatlas_produce(args: argparse.Namespace) -> int:
    payload = chatlas_produce(
        view=args.view,
        explain=args.explain,
        **_chatlas_index_selector_kwargs(args),
    )
    print(format_json_output(payload))
    return 0


def _cmd_chatlas_run_produce(args: argparse.Namespace) -> int:
    from pathlib import Path

    query_payload = chatlas_index_query(**_chatlas_index_selector_kwargs(args))
    rows = query_payload.get("rows", [])
    if not rows:
        print(format_json_output({
            "status": "ok",
            "command": "chatlas run-produce",
            "run_count": 0,
            "message": "no sessions matched the selector",
        }))
        return 0
    payload = chatlas_run_produce(
        view=args.view,
        provider=args.run_produce_provider,
        profile=args.profile,
        model=args.model,
        dry_run=args.dry_run,
        cwd=Path.cwd().resolve(),
        rows=rows,
    )
    print(format_json_output(payload))
    return 1 if payload.get("failed_count", 0) else 0


def _add_chatlas_provider_argument(parser: argparse.ArgumentParser, *, help_text: str) -> None:
    parser.add_argument(
        "--provider",
        choices=_CHATLAS_PROVIDER_CHOICES,
        action="append",
        dest="providers",
        help=help_text,
    )


def _add_chatlas_index_selector_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--uri",
        default=None,
        help="Match the indexed session URI exactly.",
    )
    parser.add_argument(
        "--identity-hash",
        default=None,
        help="Match the indexed identity hash exactly.",
    )
    _add_chatlas_provider_argument(
        parser,
        help_text="Restrict selection to a provider family. Repeat to include multiple providers.",
    )
    parser.add_argument(
        "--instance",
        action="append",
        dest="instances",
        help="Restrict selection to an indexed provider instance. Repeat to include multiple instances.",
    )
    parser.add_argument(
        "--provider-instance-fingerprint",
        default=None,
        help="Match the indexed provider instance fingerprint exactly.",
    )
    parser.add_argument(
        "--session-id",
        default=None,
        help="Match the indexed provider session id exactly.",
    )
    parser.add_argument(
        "--display-name",
        default=None,
        help="Match indexed display names by case-insensitive substring.",
    )
    parser.add_argument(
        "--extractable",
        action="store_true",
        help="Keep only sessions with an extractable primary artifact.",
    )
    parser.add_argument(
        "--updated-after",
        default=None,
        help="Keep only sessions whose indexed updated_at is at or after this ISO 8601 timestamp.",
    )
    parser.add_argument(
        "--sort",
        choices=("lexical", "newest", "oldest"),
        default="lexical",
        help="Sort order for selected sessions (default: lexical).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of selected index rows to return.",
    )


def _chatlas_index_selector_kwargs(args: argparse.Namespace) -> dict[str, object]:
    return {
        "uri": args.uri,
        "identity_hash": args.identity_hash,
        "providers": optional_string_tuple(args.providers),
        "instances": optional_string_tuple(args.instances),
        "provider_instance_fingerprint": args.provider_instance_fingerprint,
        "session_id": args.session_id,
        "display_name": args.display_name,
        "extractable_only": args.extractable,
        "updated_after": args.updated_after,
        "sort": args.sort,
        "limit": args.limit,
    }


def _add_chatlas_progress_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--verbose-mode",
        choices=_CHATLAS_UPDATE_VERBOSE_MODES,
        default="progress",
        help="Progress feedback mode: `progress` prints live update messages to stderr; `quiet` disables them (default: progress).",
    )
    parser.add_argument(
        "--output-mode",
        choices=_CHATLAS_UPDATE_OUTPUT_MODES,
        default="none",
        help="Final command output mode: `none` prints nothing after the update; `json` prints the update payload (default: none).",
    )


def _add_chatlas_index_update_arguments(parser: argparse.ArgumentParser) -> None:
    _add_chatlas_provider_argument(
        parser,
        help_text="Restrict the update run to a provider family. Repeat to include multiple providers.",
    )
    _add_chatlas_progress_arguments(parser)
    parser.add_argument(
        "--disable-cache",
        action="store_true",
        help="Disable all Chatlas update caches. Overrides `--scan-cache` and `--session-index-cache`.",
    )
    parser.add_argument(
        "--scan-cache",
        choices=("true", "false"),
        default="true",
        help="Use the local raw-scan cache during archive scans (default: true).",
    )
    parser.add_argument(
        "--session-index-cache",
        choices=("true", "false"),
        default="true",
        help="Use the local session index cache during session index materialization (default: true).",
    )


def _add_chatlas_view_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--view",
        required=True,
        help="Registered Chatlas view name.",
    )


def _add_chatlas_view_consumer_arguments(parser: argparse.ArgumentParser) -> None:
    _add_chatlas_view_argument(parser)
    _add_chatlas_index_selector_arguments(parser)
    parser.add_argument(
        "--explain",
        action="store_true",
        help="Include recursive freshness diagnostics.",
    )


def register_chatlas_commands(subparsers: argparse._SubParsersAction) -> None:
    chatlas_parser = subparsers.add_parser(
        "chatlas",
        help="Git-backed chat dataset service.",
    )
    chatlas_subparsers = chatlas_parser.add_subparsers(dest="chatlas_command", required=True)

    update_parser = chatlas_subparsers.add_parser(
        "update",
        help="Run the full Chatlas update routine.",
    )
    _add_chatlas_index_update_arguments(update_parser)
    update_parser.set_defaults(handler=_cmd_chatlas_update)

    index_parser = chatlas_subparsers.add_parser(
        "index",
        help="Maintain the Chatlas session index.",
    )
    index_subparsers = index_parser.add_subparsers(dest="chatlas_index_command", required=True)

    index_update_parser = index_subparsers.add_parser(
        "update",
        help="Copy native deltas and update the Chatlas session index.",
    )
    _add_chatlas_index_update_arguments(index_update_parser)
    index_update_parser.set_defaults(handler=_cmd_chatlas_index_update)

    index_reset_parser = index_subparsers.add_parser(
        "reset",
        help="Delete Chatlas session index and derivation cache files.",
    )
    _add_chatlas_progress_arguments(index_reset_parser)
    index_reset_parser.set_defaults(handler=_cmd_chatlas_index_reset)

    index_redo_parser = index_subparsers.add_parser(
        "redo",
        help="Recompute the Chatlas session index from all copied raw artifacts.",
    )
    _add_chatlas_provider_argument(
        index_redo_parser,
        help_text="Restrict the redo run to a provider family. Repeat to include multiple providers.",
    )
    _add_chatlas_progress_arguments(index_redo_parser)
    index_redo_parser.set_defaults(handler=_cmd_chatlas_index_redo)

    index_query_parser = index_subparsers.add_parser(
        "query",
        help="Query Chatlas session index rows.",
    )
    _add_chatlas_index_selector_arguments(index_query_parser)
    index_query_parser.add_argument(
        "--format",
        choices=("json",),
        default="json",
        dest="output_format",
        help="Output format. Chatlas index query supports json only.",
    )
    index_query_parser.set_defaults(handler=_cmd_chatlas_index_query)

    index_doctor_parser = index_subparsers.add_parser(
        "doctor",
        help="Check Chatlas session index consistency.",
    )
    index_doctor_parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        dest="output_format",
        help="Output format (default: markdown).",
    )
    index_doctor_parser.set_defaults(handler=_cmd_chatlas_index_doctor)

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
        help="Query Chatlas sessions with layered index, raw, and standard-model filters.",
    )
    query_parser.add_argument(
        "--uri",
        default=None,
        help="Match the indexed session URI exactly.",
    )
    query_parser.add_argument(
        "--identity-hash",
        default=None,
        help="Match the indexed identity hash exactly.",
    )
    query_parser.add_argument(
        "--provider",
        choices=_CHATLAS_PROVIDER_CHOICES,
        action="append",
        dest="providers",
        help="Restrict query to a provider family. Repeat to include multiple providers.",
    )
    query_parser.add_argument(
        "--session-id",
        default=None,
        help="Match the indexed provider session id exactly.",
    )
    query_parser.add_argument(
        "--display-name",
        default=None,
        help="Match indexed display names by case-insensitive substring.",
    )
    query_parser.add_argument(
        "--extractable",
        action="store_true",
        help="Keep only sessions with an extractable primary artifact.",
    )
    query_parser.add_argument(
        "--updated-after",
        default=None,
        help="Keep only sessions whose indexed updated_at is at or after this ISO 8601 timestamp.",
    )
    query_parser.add_argument(
        "--sort",
        choices=("lexical", "newest", "oldest"),
        default="lexical",
        help="Sort order for returned sessions (default: lexical).",
    )
    query_parser.add_argument(
        "--scan-limit",
        type=int,
        default=None,
        help="Maximum number of index candidates to scan before raw and standard-model filters.",
    )
    query_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of sessions to return.",
    )
    query_parser.add_argument(
        "--raw-contains",
        action="append",
        default=None,
        help="Keep only sessions whose backing artifacts contain this literal text. Repeat for AND matching.",
    )
    query_parser.add_argument(
        "--user-contains",
        action="append",
        default=None,
        help="Keep only sessions whose visible user message text contains this literal text. Repeat for AND matching.",
    )
    query_parser.add_argument(
        "--assistant-contains",
        action="append",
        default=None,
        help="Keep only sessions whose visible assistant message text contains this literal text. Repeat for AND matching.",
    )
    query_parser.add_argument(
        "--message-contains",
        action="append",
        default=None,
        help="Keep only sessions whose visible user or assistant message text contains this literal text. Repeat for AND matching.",
    )
    query_parser.set_defaults(handler=_cmd_chatlas_query)

    export_parser = chatlas_subparsers.add_parser(
        "export",
        help="Export one Chatlas session as the standard session model JSON object.",
    )
    _add_chatlas_index_selector_arguments(export_parser)
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
    _add_chatlas_index_selector_arguments(raw_path_parser)
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
    _add_chatlas_index_selector_arguments(raw_export_parser)
    raw_export_parser.add_argument(
        "--format",
        choices=("json",),
        default="json",
        dest="output_format",
        help="Output format. Raw export supports json only.",
    )
    raw_export_parser.set_defaults(handler=_cmd_chatlas_raw_export)

    views_parser = chatlas_subparsers.add_parser(
        "views",
        help="Materialize and consume cached Chatlas views.",
    )
    views_subparsers = views_parser.add_subparsers(
        dest="chatlas_views_command",
        required=True,
    )

    views_list_parser = views_subparsers.add_parser(
        "list",
        help="List registered Chatlas views.",
    )
    views_list_parser.set_defaults(handler=_cmd_chatlas_views_list)

    views_get_parser = views_subparsers.add_parser(
        "get",
        help="Get a materialized Chatlas view artifact result.",
    )
    _add_chatlas_view_consumer_arguments(views_get_parser)
    views_get_parser.set_defaults(handler=_cmd_chatlas_views_get)

    views_status_parser = views_subparsers.add_parser(
        "status",
        help="Report materialized Chatlas view freshness.",
    )
    _add_chatlas_view_consumer_arguments(views_status_parser)
    views_status_parser.set_defaults(handler=_cmd_chatlas_views_status)

    views_path_parser = views_subparsers.add_parser(
        "path",
        help="Print a materialized Chatlas view primary artifact path.",
    )
    _add_chatlas_view_consumer_arguments(views_path_parser)
    views_path_parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        dest="output_format",
        help="Output format (default: text).",
    )
    views_path_parser.set_defaults(handler=_cmd_chatlas_views_path)

    views_stage_parser = views_subparsers.add_parser(
        "stage",
        help="Create a staging directory for an externally produced Chatlas view.",
    )
    _add_chatlas_view_argument(views_stage_parser)
    _add_chatlas_index_selector_arguments(views_stage_parser)
    views_stage_parser.set_defaults(handler=_cmd_chatlas_views_stage)

    views_commit_parser = views_subparsers.add_parser(
        "commit",
        help="Commit a staged externally produced Chatlas view.",
    )
    views_commit_parser.add_argument(
        "--stage-id",
        required=True,
        help="Stage id returned by `agentos chatlas views stage`.",
    )
    views_commit_parser.set_defaults(handler=_cmd_chatlas_views_commit)

    produce_parser = chatlas_subparsers.add_parser(
        "produce",
        help="Produce a Chatlas view. Internal views produce programmatically; external views output the production prompt.",
    )
    _add_chatlas_view_consumer_arguments(produce_parser)
    produce_parser.set_defaults(handler=_cmd_chatlas_produce)

    run_produce_parser = chatlas_subparsers.add_parser(
        "run-produce",
        help="Run an agent to produce a Chatlas view for each session matching the selector.",
    )
    _add_chatlas_view_argument(run_produce_parser)
    run_produce_parser.add_argument(
        "--agent-provider",
        choices=tuple(p.family for p in canonical_provider_families()),
        required=True,
        dest="run_produce_provider",
        help="Agent provider to use for production.",
    )
    run_produce_parser.add_argument(
        "--profile",
        default=None,
        help="Agent profile (instance id) when multiple are configured for the provider.",
    )
    run_produce_parser.add_argument(
        "--model",
        default=None,
        help="Override the agent default model.",
    )
    run_produce_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show prompts and agent commands without executing.",
    )
    _add_chatlas_index_selector_arguments(run_produce_parser)
    run_produce_parser.set_defaults(handler=_cmd_chatlas_run_produce)
