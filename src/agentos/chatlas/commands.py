# $kw: ^chatlas-command-composition --from Agent.Navigable.Codebase --note [CT] the public Chatlas registrar owns parser composition while command behavior lives in a separate cohesive surface --supp ^c20260811-62u
from __future__ import annotations

import argparse
from pathlib import Path

from agentos.agent.providers import canonical_provider_families
from agentos.chatlas.anchory_batch import ANCHOR_BATCH_SCHEMA
from agentos.chatlas.chat_index_plan import MODES
from agentos.chatlas.gc import DEFAULT_OLDER_THAN
from agentos.chatlas.output import add_chatlas_output_arguments_to_leaves

from ._command_support import (
    _CHATLAS_PROVIDER_CHOICES,
    _positive_int,
    _cmd_chatlas_update,
    _cmd_chatlas_index_update,
    _cmd_chatlas_index_reset,
    _cmd_chatlas_index_redo,
    _cmd_chatlas_gc,
    _cmd_chatlas_index_query,
    _cmd_chatlas_events_index,
    _cmd_chatlas_events_query,
    _cmd_chatlas_turns_query,
    _cmd_chatlas_file_edition_pois,
    _cmd_chatlas_index_doctor,
    _cmd_chatlas_stats,
    _cmd_chatlas_local_sync,
    _cmd_chatlas_local_status,
    _add_update_flag,
    _cmd_chatlas_query,
    _cmd_chatlas_utils_tagger,
    _cmd_chatlas_annotations_add,
    _cmd_chatlas_annotations_remove,
    _cmd_chatlas_annotations_list,
    _cmd_chatlas_recents,
    _cmd_chatlas_ping,
    _cmd_chatlas_provider_query,
    _cmd_chatlas_anchory_preview,
    _cmd_chatlas_anchory_register,
    _cmd_chatlas_anchory_batch_preview,
    _cmd_chatlas_anchory_batch_register,
    _cmd_chatlas_anchory_resolve,
    _cmd_chatlas_anchory_reattach,
    _cmd_chatlas_anchory_enrich,
    _cmd_chatlas_anchory_sessions,
    _cmd_chatlas_anchory_stats,
    _cmd_chatlas_views_get,
    _cmd_chatlas_raw_path,
    _cmd_chatlas_raw_export,
    _cmd_chatlas_views_list,
    _cmd_chatlas_products_list,
    _cmd_chatlas_chat_index_status,
    _cmd_chatlas_chat_index_show,
    _cmd_chatlas_chat_index_path,
    _cmd_chatlas_chat_index_files,
    _cmd_chatlas_chat_index_deltas,
    _cmd_chatlas_chat_index_head,
    _cmd_chatlas_chat_index_home,
    _cmd_chatlas_chat_index_source,
    _cmd_chatlas_chat_index_tail,
    _cmd_chatlas_chat_index_audit,
    _cmd_chatlas_chat_index_scaffold,
    _cmd_chatlas_chat_index_validate,
    _cmd_chatlas_chat_index_apply,
    _cmd_chatlas_project_index_audit,
    _cmd_chatlas_project_index_reconcile,
    _cmd_chatlas_products_get,
    _cmd_chatlas_products_status,
    _cmd_chatlas_products_path,
    _cmd_chatlas_products_stage,
    _cmd_chatlas_products_commit,
    _cmd_chatlas_products_check,
    _cmd_chatlas_products_scaffold,
    _cmd_chatlas_products_produce,
    _cmd_chatlas_products_run_produce,
    _add_chatlas_provider_argument,
    _add_chatlas_index_selector_arguments,
    _add_chatlas_progress_arguments,
    _add_chatlas_index_update_arguments,
    _add_chatlas_query_selector_arguments,
    _chatlas_query_selector_kwargs,
    _add_chatlas_view_argument,
    _add_chatlas_product_consumer_arguments,
    _add_chatlas_local_project_argument,
)


def register_chatlas_commands(subparsers: argparse._SubParsersAction) -> None:
    chatlas_parser = subparsers.add_parser(
        "chatlas",
        help="Git-backed chat dataset service.",
    )
    chatlas_subparsers = chatlas_parser.add_subparsers(
        dest="chatlas_command", required=True
    )

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
    index_subparsers = index_parser.add_subparsers(
        dest="chatlas_index_command", required=True
    )

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

    gc_parser = chatlas_subparsers.add_parser(
        "gc",
        help="Move already-captured provider-home originals into Chatlas GC storage.",
    )
    _add_chatlas_provider_argument(
        gc_parser,
        help_text="Restrict GC to a provider family. Repeat to include multiple providers.",
    )
    gc_parser.add_argument(
        "--instance",
        action="append",
        dest="instances",
        help="Restrict GC to a configured provider instance. Repeat to include multiple.",
    )
    gc_parser.add_argument(
        "--session-id",
        action="append",
        dest="session_ids",
        help="Restrict GC to a native provider session id. Repeat to include multiple.",
    )
    gc_parser.add_argument(
        "--older-than",
        default=DEFAULT_OLDER_THAN,
        help=f"Move only provider-home originals older than this duration (default: {DEFAULT_OLDER_THAN}). Supports d, h, m, and s.",
    )
    gc_parser.add_argument(
        "--apply",
        action="store_true",
        help="Move eligible provider-home originals into Chatlas GC storage.",
    )
    _add_chatlas_progress_arguments(gc_parser)
    gc_parser.set_defaults(handler=_cmd_chatlas_gc)

    index_query_parser = index_subparsers.add_parser(
        "query",
        help="Query Chatlas session index rows.",
    )
    _add_chatlas_index_selector_arguments(index_query_parser)
    index_query_parser.set_defaults(handler=_cmd_chatlas_index_query)

    index_doctor_parser = index_subparsers.add_parser(
        "doctor",
        help="Check Chatlas session index consistency.",
    )
    index_doctor_parser.add_argument(
        "--null-fields",
        choices=("policy", "ignore", "warn", "error"),
        default="policy",
        help=(
            "Null-field inspection mode: policy reports unexpected nulls only, "
            "ignore disables null checks, warn/error run a full scan (default: policy)."
        ),
    )
    index_doctor_parser.set_defaults(handler=_cmd_chatlas_index_doctor)

    events_parser = chatlas_subparsers.add_parser(
        "events",
        help="Query relational Event.Patterns over Chatlas session models.",
    )
    events_subparsers = events_parser.add_subparsers(
        dest="chatlas_events_command",
        required=True,
    )
    events_index_parser = events_subparsers.add_parser(
        "index",
        help="Rebuild the disposable SQLite Event.Pattern candidate index.",
    )
    events_index_parser.set_defaults(handler=_cmd_chatlas_events_index)

    events_query_parser = events_subparsers.add_parser(
        "query",
        help="Evaluate a structured Event.Pattern.",
    )
    events_query_parser.add_argument(
        "--pattern-json",
        required=True,
        help=(
            "Structured Event.Pattern JSON; naive timestamp predicates are local, "
            "while Z or an offset is explicit; raw SQL is not accepted."
        ),
    )
    events_query_parser.add_argument(
        "--backend",
        choices=("auto", "scan", "sqlite"),
        default="auto",
        help="Candidate discovery backend (default: auto).",
    )
    _add_chatlas_index_selector_arguments(events_query_parser)
    events_query_parser.set_defaults(handler=_cmd_chatlas_events_query)

    turns_parser = chatlas_subparsers.add_parser(
        "turns",
        help="Query authoritative Normal.Turn groupings.",
    )
    turns_subparsers = turns_parser.add_subparsers(
        dest="chatlas_turns_command",
        required=True,
    )
    turns_query_parser = turns_subparsers.add_parser(
        "query",
        help="Find turns through an ergonomic Event.Pattern query.",
    )
    text_group = turns_query_parser.add_mutually_exclusive_group()
    text_group.add_argument(
        "--exact",
        dest="text_exact",
        help="Match message text exactly.",
    )
    text_group.add_argument(
        "--contains",
        dest="text_contains",
        help="Match a case-insensitive message-text substring.",
    )
    text_group.add_argument(
        "--regex",
        dest="text_regex",
        help="Match message text with a Python regular expression.",
    )
    text_group.add_argument(
        "--verbatim",
        help=(
            "Match the alphanumeric material of an Index line, ignoring case, "
            "punctuation, whitespace, line markers, and trailing anchors."
        ),
    )
    turns_query_parser.add_argument(
        "--role",
        help="Match the message payload role exactly.",
    )
    turns_query_parser.add_argument(
        "--turn-kind",
        choices=("user", "assistant"),
        help="Match normalized User.Turn or Assistant.Turn semantics.",
    )
    turns_query_parser.add_argument(
        "--producer-type",
        help="Match the event producer type exactly.",
    )
    turns_query_parser.add_argument(
        "--after",
        help="Keep turns at or after this timestamp (naive ISO 8601 values are local; use Z or an offset for UTC).",
    )
    turns_query_parser.add_argument(
        "--before",
        help="Keep turns at or before this timestamp (naive ISO 8601 values are local; use Z or an offset for UTC).",
    )
    turns_query_parser.add_argument(
        "--sort",
        choices=("oldest", "newest"),
        default="oldest",
        help="Turn ordering (default: oldest).",
    )
    turns_query_parser.add_argument(
        "--limit",
        type=_positive_int,
        default=50,
        help="Maximum matching turns to return (default: 50).",
    )
    turns_query_parser.add_argument(
        "--backend",
        choices=("auto", "scan", "sqlite"),
        default="auto",
        help="Candidate discovery backend (default: auto).",
    )
    turns_query_parser.add_argument(
        "--detail",
        choices=("summary", "turn"),
        default="summary",
        help="Result detail: compact matched-event summary or full turn (default: summary).",
    )
    _add_chatlas_index_selector_arguments(
        turns_query_parser,
        include_active_after=False,
        include_sort_limit=False,
    )
    turns_query_parser.set_defaults(handler=_cmd_chatlas_turns_query)

    file_edition_pois_parser = chatlas_subparsers.add_parser(
        "file-edition-pois",
        help="Find normalized chat events that may evidence file editions.",
    )
    file_edition_pois_parser.add_argument(
        "--session",
        required=True,
        help="Native provider session id.",
    )
    file_edition_pois_parser.add_argument(
        "--file",
        help="Restrict POIs to a matching observed file path.",
    )
    file_edition_pois_parser.add_argument(
        "--limit",
        type=_positive_int,
        help="Return at most this many POIs after filtering and stable sorting.",
    )
    file_edition_pois_parser.set_defaults(handler=_cmd_chatlas_file_edition_pois)

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
    _add_update_flag(stats_parser)
    stats_parser.set_defaults(handler=_cmd_chatlas_stats)

    local_parser = chatlas_subparsers.add_parser(
        "local",
        help="Export project-attributed Chatlas sessions into a project-local chatlas folder.",
    )
    _add_chatlas_local_project_argument(local_parser, default=None)
    local_parser.set_defaults(handler=_cmd_chatlas_local_status)
    local_subparsers = local_parser.add_subparsers(
        dest="chatlas_local_command", required=False
    )

    local_sync_parser = local_subparsers.add_parser(
        "sync",
        help="Write attributed turns-filtered session models under <project>/chatlas/.",
    )
    _add_chatlas_local_project_argument(local_sync_parser)
    local_sync_parser.set_defaults(handler=_cmd_chatlas_local_sync)

    local_status_parser = local_subparsers.add_parser(
        "status",
        help="Compare attributed Chatlas sessions with the project-local chatlas folder.",
    )
    _add_chatlas_local_project_argument(local_status_parser)
    local_status_parser.set_defaults(handler=_cmd_chatlas_local_status)

    query_parser = chatlas_subparsers.add_parser(
        "query",
        help="Query Chatlas sessions with layered index, raw, and standard-model filters.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  agentos chatlas query --min-user-turns 4 --field session_id\n"
            "  agentos chatlas query --min-user-turns 4 | jq -r '.rows[].session_id'"
        ),
    )
    _add_chatlas_query_selector_arguments(query_parser)
    _add_update_flag(query_parser)
    query_parser.set_defaults(handler=_cmd_chatlas_query)

    annotations_parser = chatlas_subparsers.add_parser(
        "annotations",
        help="Manage per-session annotations (free-form metadata).",
    )
    annotations_subparsers = annotations_parser.add_subparsers(
        dest="chatlas_annotations_command",
        required=True,
    )

    annotations_add_parser = annotations_subparsers.add_parser(
        "add",
        help="Add a tag annotation to a session.",
    )
    annotations_add_parser.add_argument(
        "--identity-hash",
        required=True,
        help="Identity hash of the session to annotate.",
    )
    annotations_add_parser.add_argument(
        "--tag",
        required=True,
        help="Tag to add (no-op if already present).",
    )
    annotations_add_parser.set_defaults(handler=_cmd_chatlas_annotations_add)

    annotations_remove_parser = annotations_subparsers.add_parser(
        "remove",
        help="Remove a tag annotation from a session.",
    )
    annotations_remove_parser.add_argument(
        "--identity-hash",
        required=True,
        help="Identity hash of the session.",
    )
    annotations_remove_parser.add_argument(
        "--tag",
        required=True,
        help="Tag to remove (no-op if absent).",
    )
    annotations_remove_parser.set_defaults(handler=_cmd_chatlas_annotations_remove)

    annotations_list_parser = annotations_subparsers.add_parser(
        "list",
        help="List all distinct tags across sessions with a count per tag.",
    )
    annotations_list_parser.set_defaults(handler=_cmd_chatlas_annotations_list)

    utils_parser = chatlas_subparsers.add_parser(
        "utils",
        help="General-purpose Chatlas utilities.",
    )
    utils_subparsers = utils_parser.add_subparsers(
        dest="chatlas_utils_command",
        required=True,
    )

    utils_tagger_parser = utils_subparsers.add_parser(
        "tagger",
        help="Interactive session-by-session tagger driven by a profile.",
    )
    utils_tagger_parser.add_argument(
        "--profile",
        required=True,
        help="Tagger profile name; resolved under chatlas.taggers.<profile> in the global agentos config.",
    )
    _add_chatlas_provider_argument(
        utils_tagger_parser,
        help_text="Restrict tagger queue to a provider family. Repeat to include multiple providers.",
    )
    utils_tagger_parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Stop after this many decisions (default: unbounded).",
    )
    utils_tagger_parser.add_argument(
        "--auto-test-rate",
        type=float,
        default=None,
        dest="auto_test_rate",
        help="Probability [0.0, 1.0] of bypassing the silent auto-tag for blind validation. Overrides the profile setting.",
    )
    utils_tagger_parser.add_argument(
        "--random-seed",
        type=int,
        default=None,
        dest="random_seed",
        help="Seed the auto-test sampling for reproducible runs (default: non-deterministic).",
    )
    utils_tagger_parser.set_defaults(handler=_cmd_chatlas_utils_tagger)

    recents_parser = chatlas_subparsers.add_parser(
        "recents",
        help="Print a chronological summary of recently updated sessions with the last user turn(s).",
    )
    recents_window = recents_parser.add_mutually_exclusive_group()
    recents_window.add_argument(
        "--since",
        default="3d",
        help="Look-back window as a duration: 30s, 10m, 4h, 3d, 2w (default: 3d).",
    )
    recents_window.add_argument(
        "--since-date",
        default=None,
        help="Look back from an absolute date or datetime (2026-07-30, 2026-07-30T14:00). Naive values are local time.",
    )
    recents_parser.add_argument(
        "--last-turns",
        type=int,
        default=3,
        help="Number of trailing user turns to show per session (default: 3).",
    )
    recents_parser.add_argument(
        "--full",
        action="store_true",
        help="Show full user turn text without truncation.",
    )
    recents_parser.add_argument(
        "--uri",
        default=None,
        help="Match the indexed session URI exactly.",
    )
    recents_parser.add_argument(
        "--identity-hash",
        default=None,
        help="Match sessions whose indexed identity hash starts with this value (prefix or full hash).",
    )
    recents_parser.add_argument(
        "--project",
        type=Path,
        nargs="?",
        const=Path("."),
        default=None,
        help="Match the indexed project_path to this resolved project path exactly. Bare --project uses the current directory.",
    )
    recents_parser.add_argument(
        "--project-base",
        default=None,
        help="Match the basename of the indexed project_path exactly.",
    )
    _add_chatlas_provider_argument(
        recents_parser,
        help_text="Restrict to a provider family. Repeat to include multiple providers.",
    )
    recents_parser.add_argument(
        "--instance",
        action="append",
        dest="instances",
        help="Restrict selection to an indexed provider instance. Repeat to include multiple instances.",
    )
    recents_parser.add_argument(
        "--provider-instance-fingerprint",
        default=None,
        help="Match the indexed provider instance fingerprint exactly.",
    )
    recents_parser.add_argument(
        "--session-id",
        default=None,
        help="Match the indexed provider session id exactly.",
    )
    recents_parser.add_argument(
        "--display-name",
        default=None,
        help="Match indexed display names by case-insensitive substring.",
    )
    recents_parser.add_argument(
        "--extractable",
        action="store_true",
        help="Keep only sessions with an extractable primary artifact.",
    )
    recents_parser.add_argument(
        "--min-user-turns",
        type=int,
        default=None,
        help="Keep only sessions with at least this many visible user turns.",
    )
    recents_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum number of sessions to show (default: 10).",
    )
    _add_update_flag(recents_parser)
    recents_parser.set_defaults(handler=_cmd_chatlas_recents)

    ping_parser = chatlas_subparsers.add_parser(
        "ping",
        help=(
            "Measure transcript round-trip latency: emit unique marker lines to stdout, "
            "then update and search Chatlas for them over several rounds. Unresolved "
            "markers persist so a later ping resolves them with cross-call latency."
        ),
    )
    ping_parser.add_argument(
        "--lines",
        type=int,
        default=5,
        help="Marker lines emitted per round (default: 5).",
    )
    ping_parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Seconds between emitted marker lines (default: 1.0).",
    )
    ping_parser.add_argument(
        "--rounds",
        type=int,
        default=4,
        help="Emit-update-check rounds (default: 4).",
    )
    ping_parser.add_argument(
        "--window-seconds",
        type=int,
        default=300,
        help="Recent-window update scope in seconds (default: 300).",
    )
    _add_chatlas_provider_argument(
        ping_parser,
        help_text="Restrict update and search to a provider family. Repeatable.",
    )
    ping_parser.set_defaults(handler=_cmd_chatlas_ping)

    provider_parser = chatlas_subparsers.add_parser(
        "provider",
        help="Read-only query into provider source archives (pre-index).",
    )
    provider_subparsers = provider_parser.add_subparsers(
        dest="chatlas_provider_command",
        required=True,
    )
    provider_query_parser = provider_subparsers.add_parser(
        "query",
        help="Point-lookup native sessions in a provider archive by session id.",
    )
    provider_query_parser.add_argument(
        "--provider",
        required=True,
        choices=_CHATLAS_PROVIDER_CHOICES,
        help="Provider family to query (required).",
    )
    provider_query_parser.add_argument(
        "--instance",
        action="append",
        dest="instances",
        help="Restrict the query to a configured provider instance. Repeat to include multiple.",
    )
    provider_query_parser.add_argument(
        "--session-id",
        action="append",
        dest="session_ids",
        help="Native session id to look up. Repeat for multiple. Required.",
    )
    provider_query_parser.set_defaults(handler=_cmd_chatlas_provider_query)

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
    raw_path_parser.set_defaults(handler=_cmd_chatlas_raw_path)

    raw_export_parser = raw_subparsers.add_parser(
        "export",
        help="Export backing raw artifact contents for one Chatlas session.",
    )
    _add_chatlas_index_selector_arguments(raw_export_parser)
    raw_export_parser.set_defaults(handler=_cmd_chatlas_raw_export)

    anchory_parser = chatlas_subparsers.add_parser(
        "anchory",
        help="Chatlas application of the Anchory subsystem.",
    )
    anchory_subparsers = anchory_parser.add_subparsers(dest="anchory_command")
    anchory_preview_parser = anchory_subparsers.add_parser(
        "preview",
        help="Validate and preview a generic support set or Index-line dossier.",
    )
    anchory_preview_parser.add_argument(
        "--member",
        action="append",
        dest="members",
        required=True,
        help="Support member as <session-identity>:<turn-id>; repeat in relevance order.",
    )
    anchory_preview_parser.add_argument(
        "--hint",
        default=None,
        help="Required only for a generic support set; never stored in a line dossier.",
    )
    anchory_preview_parser.add_argument(
        "--line-content",
        default=None,
        help="Index line whose allocated anchor triplet the dossier asserts.",
    )
    anchory_preview_parser.add_argument(
        "--issue",
        action="append",
        dest="issues",
        default=[],
        help="Issue.I#### edition context for the line; repeatable.",
    )
    anchory_preview_parser.add_argument(
        "--gates",
        dest="gates",
        default=None,
        help="Dossier gates JSON with semantic_approval and tokenized_verbatim_approval lists.",
    )
    anchory_preview_parser.add_argument(
        "--detail",
        choices=("summary", "turn", "context"),
        default="summary",
        help="Preview detail level (default: summary).",
    )
    anchory_preview_parser.add_argument(
        "--radius",
        type=int,
        default=4,
        help="Visible turns around each member when --detail context is used.",
    )
    anchory_preview_parser.set_defaults(handler=_cmd_chatlas_anchory_preview)

    anchory_register_parser = anchory_subparsers.add_parser(
        "register",
        help="Mint a validated generic support-set or Index-line dossier anchor.",
    )
    anchory_register_parser.add_argument(
        "--member",
        action="append",
        dest="members",
        required=True,
        help="Support member as <session-identity>:<turn-id>; repeat in relevance order.",
    )
    anchory_register_parser.add_argument(
        "--hint",
        default=None,
        help="Required only for a generic support set; never stored in a line dossier.",
    )
    anchory_register_parser.add_argument(
        "--line-content",
        default=None,
        help="Index line whose allocated anchor triplet the dossier asserts.",
    )
    anchory_register_parser.add_argument(
        "--issue",
        action="append",
        dest="issues",
        default=[],
        help="Issue.I#### edition context for the line; repeatable.",
    )
    anchory_register_parser.add_argument(
        "--gates",
        dest="gates",
        default=None,
        help=(
            "Dossier gates JSON with semantic_approval and tokenized_verbatim_approval lists; "
            "each gate owns its proposal_turn and approval_turn references."
        ),
    )
    anchory_register_parser.add_argument(
        "--detail",
        choices=("summary", "turn", "context"),
        default="summary",
        help="Result detail level (default: summary).",
    )
    anchory_register_parser.add_argument(
        "--radius",
        type=int,
        default=4,
        help="Visible turns around each member when --detail context is used.",
    )
    anchory_register_parser.set_defaults(handler=_cmd_chatlas_anchory_register)

    anchory_batch_parser = anchory_subparsers.add_parser(
        "batch",
        help="Preview or ensure many Chatlas.Line.Anchor.Dossier records at once.",
    )
    anchory_batch_subparsers = anchory_batch_parser.add_subparsers(
        dest="anchory_batch_command",
        required=True,
    )
    anchory_batch_preview_parser = anchory_batch_subparsers.add_parser(
        "preview",
        help="Validate an ordered anchor batch and report both equivalence classes.",
    )
    anchory_batch_preview_parser.add_argument(
        "--input",
        required=True,
        help=f"Path to a {ANCHOR_BATCH_SCHEMA} JSON document.",
    )
    anchory_batch_preview_parser.set_defaults(
        handler=_cmd_chatlas_anchory_batch_preview
    )

    anchory_batch_register_parser = anchory_batch_subparsers.add_parser(
        "register",
        help="Idempotently ensure exact line-bound anchors for an ordered batch.",
    )
    anchory_batch_register_parser.add_argument(
        "--input",
        required=True,
        help=f"Path to a {ANCHOR_BATCH_SCHEMA} JSON document.",
    )
    anchory_batch_register_parser.set_defaults(
        handler=_cmd_chatlas_anchory_batch_register
    )

    anchory_resolve_parser = anchory_subparsers.add_parser(
        "resolve",
        help="Resolve an anchor to its ordered support-member neighborhoods.",
    )
    anchory_resolve_parser.add_argument("anchor", help="Chatlas anchor key.")
    anchory_resolve_parser.add_argument(
        "--radius",
        type=int,
        default=4,
        help="Number of visible turns before and after each support member (default: 4).",
    )
    anchory_resolve_parser.add_argument(
        "--detail",
        choices=("summary", "turn", "context"),
        default="summary",
        help="Resolution detail level (default: summary).",
    )
    anchory_resolve_parser.set_defaults(handler=_cmd_chatlas_anchory_resolve)

    anchory_reattach_parser = anchory_subparsers.add_parser(
        "reattach",
        help="Refresh a line dossier's triplet assertion without changing relationships.",
    )
    anchory_reattach_parser.add_argument(
        "--depot",
        required=True,
        help="Index depot parsed to resolve the anchor's current line triplet.",
    )
    anchory_reattach_parser.add_argument(
        "--anchor",
        required=True,
        help="Chatlas line anchor key to resolve from the parsed depot.",
    )
    anchory_reattach_parser.set_defaults(handler=_cmd_chatlas_anchory_reattach)

    anchory_enrich_parser = anchory_subparsers.add_parser(
        "enrich",
        help="Add Issue edition context to a line dossier's provenance relationships.",
    )
    anchory_enrich_parser.add_argument("anchor", help="Chatlas line anchor key.")
    anchory_enrich_parser.add_argument(
        "--issue",
        action="append",
        dest="issues",
        default=[],
        help="Issue.I#### edition context; repeatable.",
    )
    anchory_enrich_parser.set_defaults(handler=_cmd_chatlas_anchory_enrich)

    anchory_sessions_parser = anchory_subparsers.add_parser(
        "sessions",
        help="Extract anchors from source files and list their support sessions.",
    )
    anchory_sessions_parser.add_argument(
        "--source",
        action="append",
        dest="sources",
        required=True,
        help="Source file or recursively scanned directory; repeat as needed.",
    )
    anchory_sessions_parser.add_argument(
        "--regex",
        required=True,
        help="Python regex that extracts anchors using the generic Anchory contract.",
    )
    anchory_sessions_parser.add_argument(
        "--glob",
        default="*.md",
        help="Recursive directory glob (default: *.md).",
    )
    anchory_sessions_parser.set_defaults(handler=_cmd_chatlas_anchory_sessions)

    anchory_stats_parser = anchory_subparsers.add_parser(
        "stats",
        help="Summarize support-turn cardinality across Chatlas anchors.",
    )
    anchory_stats_parser.set_defaults(handler=_cmd_chatlas_anchory_stats)

    views_parser = chatlas_subparsers.add_parser(
        "views",
        help="Apply named disposable projections to one Chatlas session model.",
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
        help="Print one named Chatlas standard-model view.",
    )
    _add_chatlas_index_selector_arguments(views_get_parser)
    _add_chatlas_view_argument(views_get_parser)
    views_get_parser.add_argument(
        "--range",
        dest="range_spec",
        help="View-specific Python-style half-open range.",
    )
    views_get_parser.add_argument(
        "--contains",
        help="Select events whose payload text contains this string (case-insensitive).",
    )
    views_get_parser.add_argument(
        "--role",
        help="Select message events with this role (e.g. user, assistant).",
    )
    views_get_parser.add_argument(
        "--around",
        help=(
            "Select events around this timestamp; naive ISO 8601 values are local, "
            "while Z or an offset is explicit; output stays chronological."
        ),
    )
    views_get_parser.add_argument(
        "--radius",
        type=int,
        help=(
            "With --around: keep only the nearest 2*RADIUS+1 events. "
            "With --filter, radius counts filter-surviving events (e.g. turns)."
        ),
    )
    views_get_parser.add_argument(
        "--filter",
        action="append",
        dest="filters",
        help=(
            "Named Chatlas filter, repeatable and ordered (slim, messages, turns); "
            "applied before --contains/--role/--around selection, after otherwise."
        ),
    )
    views_get_parser.add_argument(
        "--file-read",
        dest="inline_file_read",
        help="Keep only events of reading tool invocations whose path contains this text.",
    )
    views_get_parser.add_argument(
        "--file-write",
        dest="inline_file_write",
        help="Keep only events of mutating tool invocations whose path contains this text.",
    )
    views_get_parser.add_argument(
        "--file-touched",
        dest="inline_file_touched",
        help="Keep only events of tool invocations (read or write) whose path contains this text.",
    )
    views_get_parser.add_argument(
        "--tool-contains",
        dest="inline_tool_contains",
        help="Keep only events of tool invocations whose name/input/output contains this text.",
    )
    views_get_parser.add_argument(
        "--tool-name",
        dest="inline_tool_name",
        help="Restrict --tool-contains to this tool; alone, keep only that tool's invocation events.",
    )
    _add_update_flag(views_get_parser)
    views_get_parser.set_defaults(handler=_cmd_chatlas_views_get)

    project_index_parser = chatlas_subparsers.add_parser(
        "project-index",
        help="Audit and incrementally reconcile a Project.Index with support chats.",
    )
    project_index_subparsers = project_index_parser.add_subparsers(
        dest="chatlas_project_index_command",
        required=True,
    )
    project_index_audit_parser = project_index_subparsers.add_parser(
        "audit",
        help="Read-only bulk Project.Index to support Chat.Index coverage audit.",
    )
    project_index_audit_parser.add_argument(
        "--depot", required=True, help="Project.Index depot root."
    )
    project_index_audit_parser.add_argument(
        "--cursor-root", help="Override the project-scoped reconciliation state root."
    )
    project_index_audit_parser.set_defaults(handler=_cmd_chatlas_project_index_audit)

    project_index_reconcile_parser = project_index_subparsers.add_parser(
        "reconcile",
        help="Audit and advance per-support-chat reconciliation cursors.",
    )
    project_index_reconcile_parser.add_argument(
        "--depot", required=True, help="Project.Index depot root."
    )
    project_index_reconcile_parser.add_argument(
        "--cursor-root", help="Override the project-scoped reconciliation state root."
    )
    project_index_reconcile_parser.add_argument(
        "--reset", action="store_true", help="Discard prior cursors before this pass."
    )
    project_index_reconcile_parser.set_defaults(
        handler=_cmd_chatlas_project_index_reconcile
    )

    chat_index_parser = chatlas_subparsers.add_parser(
        "chat-index",
        help="Inspect a retained materialized Chat.Index stable surface.",
    )
    chat_index_subparsers = chat_index_parser.add_subparsers(
        dest="chatlas_chat_index_command",
        required=True,
    )

    chat_index_status_parser = chat_index_subparsers.add_parser(
        "status",
        help="Report whether one materialized Chat.Index is current or stale.",
    )
    _add_chatlas_index_selector_arguments(
        chat_index_status_parser,
        include_active_after=False,
        include_sort_limit=False,
    )
    chat_index_status_parser.set_defaults(handler=_cmd_chatlas_chat_index_status)

    chat_index_show_parser = chat_index_subparsers.add_parser(
        "show",
        help="Show one materialized Chat.Index descriptor and current status.",
    )
    _add_chatlas_index_selector_arguments(
        chat_index_show_parser,
        include_active_after=False,
        include_sort_limit=False,
    )
    chat_index_show_parser.set_defaults(handler=_cmd_chatlas_chat_index_show)

    chat_index_path_parser = chat_index_subparsers.add_parser(
        "path",
        help="Print the deterministic path for one session's Chat.Index.",
    )
    _add_chatlas_index_selector_arguments(
        chat_index_path_parser,
        include_active_after=False,
        include_sort_limit=False,
    )
    chat_index_path_parser.set_defaults(handler=_cmd_chatlas_chat_index_path)

    chat_index_files_parser = chat_index_subparsers.add_parser(
        "files",
        help="List the files managed by one materialized Chat.Index descriptor.",
    )
    _add_chatlas_index_selector_arguments(
        chat_index_files_parser,
        include_active_after=False,
        include_sort_limit=False,
    )
    chat_index_files_parser.set_defaults(handler=_cmd_chatlas_chat_index_files)

    chat_index_deltas_parser = chat_index_subparsers.add_parser(
        "deltas",
        help="List v2 Chat.Index.Deltas in authoritative tape order.",
    )
    _add_chatlas_index_selector_arguments(
        chat_index_deltas_parser,
        include_active_after=False,
        include_sort_limit=False,
    )
    chat_index_deltas_parser.set_defaults(handler=_cmd_chatlas_chat_index_deltas)

    chat_index_head_parser = chat_index_subparsers.add_parser(
        "head",
        help="Show the v2 Chat.Index.HEAD materialization.",
    )
    _add_chatlas_index_selector_arguments(
        chat_index_head_parser,
        include_active_after=False,
        include_sort_limit=False,
    )
    chat_index_head_parser.set_defaults(handler=_cmd_chatlas_chat_index_head)

    chat_index_home_parser = chat_index_subparsers.add_parser(
        "home",
        help="Find the oldest Delta containing exact Index.Line content.",
    )
    _add_chatlas_index_selector_arguments(
        chat_index_home_parser,
        include_active_after=False,
        include_sort_limit=False,
    )
    chat_index_home_parser.add_argument(
        "--line-content",
        required=True,
        help="Exact typed Index.Line content, with or without trailing anchors.",
    )
    chat_index_home_parser.set_defaults(handler=_cmd_chatlas_chat_index_home)

    chat_index_source_parser = chat_index_subparsers.add_parser(
        "source",
        help="Show the v2 tape-ordered source descriptor used during capture.",
    )
    _add_chatlas_index_selector_arguments(
        chat_index_source_parser,
        include_active_after=False,
        include_sort_limit=False,
    )
    chat_index_source_parser.set_defaults(handler=_cmd_chatlas_chat_index_source)

    chat_index_tail_parser = chat_index_subparsers.add_parser(
        "tail",
        help="Show source evidence pending Chat.Index maintenance.",
    )
    _add_chatlas_index_selector_arguments(
        chat_index_tail_parser,
        include_active_after=False,
        include_sort_limit=False,
    )
    chat_index_tail_parser.add_argument(
        "--detail",
        choices=("refs", "chat", "turn"),
        default="refs",
        help=(
            "Return compact pending refs, transcript-visible chat messages, or "
            "complete pending Normal.Turn groupings."
        ),
    )
    chat_index_tail_parser.set_defaults(handler=_cmd_chatlas_chat_index_tail)

    chat_index_audit_parser = chat_index_subparsers.add_parser(
        "audit",
        help="Audit one Chat.Index surface in a single read-only pass.",
    )
    _add_chatlas_index_selector_arguments(
        chat_index_audit_parser,
        include_active_after=False,
        include_sort_limit=False,
    )
    chat_index_audit_parser.add_argument(
        "--surface",
        default=None,
        help=(
            "Audit this staged directory instead of the live surface, still "
            "resolving source and support against the selected session."
        ),
    )
    chat_index_audit_parser.set_defaults(handler=_cmd_chatlas_chat_index_audit)

    chat_index_scaffold_parser = chat_index_subparsers.add_parser(
        "scaffold",
        help="Write transient Capture.Plan working input for one session.",
    )
    _add_chatlas_index_selector_arguments(
        chat_index_scaffold_parser,
        include_active_after=False,
        include_sort_limit=False,
    )
    chat_index_scaffold_parser.add_argument(
        "--stage",
        required=True,
        help="Empty directory receiving plan.json and evidence.json.",
    )
    chat_index_scaffold_parser.add_argument(
        "--mode",
        choices=MODES,
        default=None,
        help=(
            "Operation mode; detected from the existing surface unless legacy "
            "replacement is being requested explicitly."
        ),
    )
    chat_index_scaffold_parser.set_defaults(handler=_cmd_chatlas_chat_index_scaffold)

    chat_index_validate_parser = chat_index_subparsers.add_parser(
        "validate",
        help="Prove a Capture.Plan renders, without writing anchors or surfaces.",
    )
    chat_index_validate_parser.add_argument(
        "--plan",
        required=True,
        help="Path to the authored plan.json.",
    )
    chat_index_validate_parser.set_defaults(handler=_cmd_chatlas_chat_index_validate)

    chat_index_apply_parser = chat_index_subparsers.add_parser(
        "apply",
        help="Ground, render, audit, and install one Capture.Plan.",
    )
    chat_index_apply_parser.add_argument(
        "--plan",
        required=True,
        help="Path to the authored plan.json.",
    )
    chat_index_apply_parser.set_defaults(handler=_cmd_chatlas_chat_index_apply)

    products_parser = chatlas_subparsers.add_parser(
        "products",
        help="Produce and consume retained artifacts derived from named views.",
    )
    products_subparsers = products_parser.add_subparsers(
        dest="chatlas_products_command",
        required=True,
    )

    products_list_parser = products_subparsers.add_parser(
        "list", help="List registered Chatlas products."
    )
    products_list_parser.set_defaults(handler=_cmd_chatlas_products_list)

    products_get_parser = products_subparsers.add_parser(
        "get", help="Get retained product state and artifact metadata."
    )
    _add_chatlas_product_consumer_arguments(products_get_parser)
    products_get_parser.set_defaults(handler=_cmd_chatlas_products_get)

    products_status_parser = products_subparsers.add_parser(
        "status", help="Report retained product freshness without producing it."
    )
    _add_chatlas_product_consumer_arguments(products_status_parser)
    products_status_parser.set_defaults(handler=_cmd_chatlas_products_status)

    products_path_parser = products_subparsers.add_parser(
        "path", help="Print a retained product artifact path."
    )
    _add_chatlas_product_consumer_arguments(products_path_parser)
    products_path_parser.set_defaults(handler=_cmd_chatlas_products_path)

    products_stage_parser = products_subparsers.add_parser(
        "stage", help="Create a product stage containing its current input view."
    )
    products_stage_parser.add_argument(
        "--product", required=True, help="Registered Chatlas product name."
    )
    _add_chatlas_index_selector_arguments(products_stage_parser)
    products_stage_parser.set_defaults(handler=_cmd_chatlas_products_stage)

    products_commit_parser = products_subparsers.add_parser(
        "commit", help="Validate and commit a staged Chatlas product."
    )
    products_commit_parser.add_argument(
        "--stage-id",
        required=True,
        help="Stage id returned by `agentos chatlas products stage`.",
    )
    products_commit_parser.add_argument(
        "--allow-low-compression",
        action="store_true",
        help=(
            "Commit even when the artifact retains too much of the source "
            "assistant text. Use only when the session genuinely cannot be "
            "compressed further; never to pass the floor by truncating text."
        ),
    )
    products_commit_parser.add_argument(
        "--allow-aggressive-compression",
        action="store_true",
        help=(
            "Commit even when assistant turns or whole regions were reduced to "
            "almost nothing. Use only when that content was genuinely "
            "disposable; never to pass the gate by padding text."
        ),
    )
    products_commit_parser.set_defaults(handler=_cmd_chatlas_products_commit)

    products_check_parser = products_subparsers.add_parser(
        "check",
        help="Run the product commit linter against a staged artifact without committing.",
    )
    products_check_parser.add_argument(
        "--stage-id",
        required=True,
        help="Stage id returned by `agentos chatlas products stage`.",
    )
    products_check_parser.add_argument(
        "--allow-low-compression",
        action="store_true",
        help="Skip the compression floor, matching the same flag on commit.",
    )
    products_check_parser.add_argument(
        "--allow-aggressive-compression",
        action="store_true",
        help="Skip the collapse gates, matching the same flag on commit.",
    )
    products_check_parser.set_defaults(handler=_cmd_chatlas_products_check)

    products_scaffold_parser = products_subparsers.add_parser(
        "scaffold",
        help="Write a staged artifact skeleton with user turns copied and assistant text empty.",
    )
    products_scaffold_parser.add_argument(
        "--stage-id",
        required=True,
        help="Stage id returned by `agentos chatlas products stage`.",
    )
    products_scaffold_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an artifact that already exists in the stage.",
    )
    products_scaffold_parser.set_defaults(handler=_cmd_chatlas_products_scaffold)

    products_produce_parser = products_subparsers.add_parser(
        "produce", help="Stage a missing or stale product and print its agent prompt."
    )
    products_produce_parser.add_argument(
        "--product", required=True, help="Registered Chatlas product name."
    )
    _add_chatlas_index_selector_arguments(products_produce_parser)
    products_produce_parser.set_defaults(handler=_cmd_chatlas_products_produce)

    run_produce_parser = products_subparsers.add_parser(
        "run-produce", help="Run an agent for each missing or stale product."
    )
    run_produce_parser.add_argument(
        "--product", required=True, help="Registered Chatlas product name."
    )
    run_produce_parser.add_argument(
        "--agent-provider",
        choices=tuple(p.family for p in canonical_provider_families()),
        default=None,
        dest="run_produce_provider",
        help="Agent provider to use for production. Falls back to chatlas config default.",
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
    run_produce_parser.add_argument(
        "--force",
        action="store_true",
        help="Run the agent even if the product is already fresh.",
    )
    run_produce_parser.add_argument(
        "--concurrency",
        type=_positive_int,
        default=1,
        help="Sessions to produce in parallel (default: 1). Each session owns its own stage and depot lock.",
    )
    _add_chatlas_query_selector_arguments(run_produce_parser)
    run_produce_parser.set_defaults(handler=_cmd_chatlas_products_run_produce)

    add_chatlas_output_arguments_to_leaves(chatlas_parser)


__all__ = ["_chatlas_query_selector_kwargs", "register_chatlas_commands"]
