# $kw: ^event-pattern-commands --from Chatlas.Query.Surface --note [CT] public Event.Pattern commands expose structured patterns and backend choice, never raw SQL ^c20260725-38u --supp ^c20260726-3u --supp ergonomic turn query ^c20260731-12u --supp implementation authorized ^c20260731-14u
# $kw: ^chat-index-tail-command --from Chat.Index --note [IMPL] expose pending source evidence without giving the CLI semantic Delta or HEAD authorship --supp ^c20260804-50u
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agentos._core.errors import CliError
from agentos._core.project import require_agentos_project_root
from agentos.agent._cli_common import optional_string_tuple
from agentos.forum import forum_banner_line
from agentos.providers import canonical_provider_families
from agentos.chatlas.core import (
    chatlas_index_update,
    chatlas_raw_export,
    chatlas_raw_paths,
    chatlas_update,
)
from agentos.chatlas.chat_index_apply import chatlas_chat_index_apply
from agentos.chatlas.chat_index_audit import chatlas_chat_index_audit
from agentos.chatlas.chat_index_plan import MODES, chatlas_chat_index_scaffold
from agentos.chatlas.chat_index_render import chatlas_chat_index_validate
from agentos.chatlas.chat_index import (
    chatlas_chat_index_deltas,
    chatlas_chat_index_files,
    chatlas_chat_index_head,
    chatlas_chat_index_home,
    chatlas_chat_index_path,
    chatlas_chat_index_show,
    chatlas_chat_index_source,
    chatlas_chat_index_status,
    chatlas_chat_index_tail,
)
from agentos.chatlas.anchory_batch import ANCHOR_BATCH_SCHEMA
from agentos.chatlas.delta_scan import chatlas_index_redo, chatlas_index_reset
from agentos.chatlas.gc import DEFAULT_OLDER_THAN, chatlas_gc
from agentos.chatlas.event_pattern import EventPatternError
from agentos.chatlas.event_query import (
    chatlas_events_index,
    chatlas_events_query,
    chatlas_turns_query,
    format_chatlas_turns_query_text,
)
from agentos.chatlas.file_edition_pois import chatlas_file_edition_pois
from agentos.chatlas.index_doctor import (
    chatlas_index_doctor,
    format_chatlas_index_doctor_markdown,
)
from agentos.chatlas.index_query import chatlas_index_query
from agentos.chatlas.index_stats import (
    chatlas_index_stats,
    format_chatlas_index_stats_markdown,
)
from agentos.chatlas.local import chatlas_local_status, chatlas_local_sync
from agentos.chatlas.normalization.session_model.delta import set_trust_tier
from agentos.chatlas.ping import chatlas_ping
from agentos.chatlas.provider_query import chatlas_provider_query
from agentos.chatlas.query import chatlas_query, format_chatlas_query_text
from agentos.chatlas.recents import chatlas_recents
from agentos.chatlas.annotations import (
    add_session_tag,
    list_all_tags,
    remove_session_tag,
)
from agentos.chatlas._duration import parse_duration_seconds
from agentos.chatlas.tagger import run_tagger
from agentos.chatlas.recents import format_chatlas_recents_text
from agentos.chatlas.recents import since_window_seconds
from agentos.chatlas.time_interface import normalize_cli_event_pattern_timestamps
from agentos.chatlas.time_interface import normalize_cli_timestamp
from agentos.chatlas.paths import default_chatlas_root
from agentos.chatlas.output import (
    add_chatlas_output_arguments_to_leaves,
    print_chatlas_output,
)
from agentos.chatlas.project_index_reconciliation import (
    project_index_audit,
    project_index_reconcile,
)
from agentos.chatlas.products import (
    chatlas_products_commit,
    chatlas_products_get,
    chatlas_products_list,
    chatlas_products_path,
    chatlas_products_produce,
    chatlas_products_check,
    chatlas_products_run_produce,
    chatlas_products_scaffold,
    chatlas_products_stage,
    chatlas_products_status,
)
from agentos.chatlas.providers import supported_chatlas_provider_families
from agentos.chatlas.views import chatlas_views_get, chatlas_views_list
from agentos.chatlas.inline import format_chatlas_view_text


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


_CHATLAS_PROVIDER_CHOICES = tuple(
    provider_family.family for provider_family in supported_chatlas_provider_families()
)
_CHATLAS_UPDATE_VERBOSE_MODES = ("progress", "quiet")


def _chatlas_update_progress_handler(verbose_mode: str):
    if verbose_mode == "quiet":
        return None
    return lambda message: print(message, file=sys.stderr, flush=True)


def _emit_chatlas_update_output(
    *, payload: dict[str, object], args: argparse.Namespace
) -> None:
    if args.quiet:
        return
    print_chatlas_output(payload, output=args.output)


def _chatlas_update_kwargs(args: argparse.Namespace) -> dict[str, object]:
    disable_cache = args.disable_cache
    recent_window = getattr(args, "recent_window", None)
    window_seconds = (
        parse_duration_seconds(recent_window, field_name="--recent-window")
        if recent_window is not None
        else None
    )
    return {
        "providers": optional_string_tuple(args.providers),
        "instances": optional_string_tuple(getattr(args, "instances", None)),
        "session_ids": tuple(getattr(args, "session_ids", None) or ()),
        "scan_cache_enabled": not disable_cache and args.scan_cache == "true",
        "session_index_cache_enabled": not disable_cache
        and args.session_index_cache == "true",
        "full_scan": args.full_scan,
        "window_seconds": window_seconds,
        "progress": _chatlas_update_progress_handler(args.verbose_mode),
    }


def _apply_trust_tier(args: argparse.Namespace) -> None:
    """`Normalization.Trust.Tier` selection: explicit --trust wins; direct
    session refreshes default to the cheap append tier, everything else to
    verify."""
    tier = getattr(args, "trust", None)
    if tier is None:
        tier = "append" if getattr(args, "session_ids", None) else "verify"
    set_trust_tier(tier)


def _cmd_chatlas_update(args: argparse.Namespace) -> int:
    _apply_trust_tier(args)
    payload = chatlas_update(**_chatlas_update_kwargs(args))
    _emit_chatlas_update_output(payload=payload, args=args)
    if args.output != "json":
        line = forum_banner_line()
        if line is not None:
            print(line, file=sys.stderr)
    return 0


def _cmd_chatlas_index_update(args: argparse.Namespace) -> int:
    _apply_trust_tier(args)
    payload = chatlas_index_update(**_chatlas_update_kwargs(args))
    _emit_chatlas_update_output(payload=payload, args=args)
    return 0


def _cmd_chatlas_index_reset(args: argparse.Namespace) -> int:
    payload = chatlas_index_reset(
        progress=_chatlas_update_progress_handler(args.verbose_mode),
    )
    _emit_chatlas_update_output(payload=payload, args=args)
    return 0


def _cmd_chatlas_index_redo(args: argparse.Namespace) -> int:
    payload = chatlas_index_redo(
        providers=optional_string_tuple(args.providers),
        progress=_chatlas_update_progress_handler(args.verbose_mode),
    )
    _emit_chatlas_update_output(payload=payload, args=args)
    return 0


def _cmd_chatlas_gc(args: argparse.Namespace) -> int:
    payload = chatlas_gc(
        providers=optional_string_tuple(args.providers),
        instances=optional_string_tuple(args.instances),
        session_ids=tuple(args.session_ids or ()),
        older_than=args.older_than,
        apply=args.apply,
        progress=_chatlas_update_progress_handler(args.verbose_mode),
    )
    _emit_chatlas_update_output(payload=payload, args=args)
    return 0


def _cmd_chatlas_index_query(args: argparse.Namespace) -> int:
    payload = chatlas_index_query(**_chatlas_index_selector_kwargs(args))
    print_chatlas_output(payload, output=args.output)
    return 0


def _cmd_chatlas_events_index(args: argparse.Namespace) -> int:
    print_chatlas_output(chatlas_events_index(), output=args.output)
    return 0


def _cmd_chatlas_events_query(args: argparse.Namespace) -> int:
    try:
        pattern_payload = normalize_cli_event_pattern_timestamps(
            json.loads(args.pattern_json)
        )
        payload = chatlas_events_query(
            pattern_payload,
            backend=args.backend,
            **_chatlas_index_selector_kwargs(args),
        )
    except (json.JSONDecodeError, EventPatternError) as exc:
        raise CliError(f"invalid Event.Pattern: {exc}") from exc
    print_chatlas_output(payload, output=args.output)
    return 0


def _cmd_chatlas_turns_query(args: argparse.Namespace) -> int:
    try:
        payload = chatlas_turns_query(
            role=args.role,
            turn_kind=args.turn_kind,
            producer_type=args.producer_type,
            text_exact=args.text_exact,
            text_contains=args.text_contains,
            text_regex=args.text_regex,
            verbatim=args.verbatim,
            after=normalize_cli_timestamp(args.after, field="--after"),
            before=normalize_cli_timestamp(args.before, field="--before"),
            sort=args.sort,
            limit=args.limit,
            backend=args.backend,
            detail=args.detail,
            **_chatlas_index_selector_kwargs(
                args,
                include_active_after=False,
                include_sort_limit=False,
            ),
        )
    except (EventPatternError, ValueError) as exc:
        raise CliError(f"invalid turn query: {exc}") from exc
    print_chatlas_output(
        payload, output=args.output, text_renderer=format_chatlas_turns_query_text
    )
    return 0


def _cmd_chatlas_file_edition_pois(args: argparse.Namespace) -> int:
    print_chatlas_output(
        chatlas_file_edition_pois(
            session=args.session,
            file=args.file,
            limit=args.limit,
        ),
        output=args.output,
    )
    return 0


def _cmd_chatlas_index_doctor(args: argparse.Namespace) -> int:
    payload = chatlas_index_doctor(null_fields=args.null_fields)
    print_chatlas_output(
        payload,
        output=args.output,
        text_renderer=format_chatlas_index_doctor_markdown,
    )
    return 0 if payload.get("status") == "ok" else 1


def _cmd_chatlas_stats(args: argparse.Namespace) -> int:
    payload = run_read_with_update(
        args,
        read_fn=lambda namespace: chatlas_index_stats(
            providers=optional_string_tuple(namespace.providers),
            full_output=namespace.full_output,
        ),
        scope_fn=_chatlas_stats_scope,
        satisfied_fn=lambda _payload: True,
    )
    print_chatlas_output(
        payload,
        output=args.output,
        text_renderer=format_chatlas_index_stats_markdown,
    )
    return 0


def _cmd_chatlas_local_sync(args: argparse.Namespace) -> int:
    payload = chatlas_local_sync(project=_chatlas_local_project_root(args))
    print_chatlas_output(payload, output=args.output)
    return 0


def _cmd_chatlas_local_status(args: argparse.Namespace) -> int:
    payload = chatlas_local_status(project=_chatlas_local_project_root(args))
    print_chatlas_output(payload, output=args.output)
    return 0


def _chatlas_local_project_root(args: argparse.Namespace) -> Path:
    return require_agentos_project_root(
        project=getattr(args, "project", None),
        include_init_hint=False,
        extra_hint="pass --project <path> or run inside an Agentos project",
    )


_UPDATE_TIER_LADDER = ("direct", "index", "recent", "full")
_DEFAULT_RECENT_WINDOW_SECONDS = 3 * 24 * 60 * 60


@dataclass(frozen=True)
class UpdateScope:
    providers: tuple[str, ...] | None = None
    active_after: str | None = None
    exact_session_ids: tuple[str, ...] = ()
    uri: str | None = None
    identity_hash: str | None = None
    window_seconds: int | None = None


def _add_update_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--update",
        nargs="?",
        const="auto",
        default=None,
        help=(
            "Refresh Chatlas before reading. Bare --update escalates cheapest-first "
            "(direct -> index -> recent -> full) until the read is non-empty; "
            "--update=<tier> pins one tier."
        ),
    )


def _start_update_tier(scope: UpdateScope) -> str:
    if scope.exact_session_ids or scope.uri or scope.identity_hash:
        return "direct"
    if scope.active_after:
        return "index"
    return "recent"


def _scope_session_ids(scope: UpdateScope, *, structural: bool) -> tuple[str, ...]:
    result = chatlas_query(
        providers=scope.providers,
        active_after=scope.active_after if structural else None,
        uri=None if structural else scope.uri,
        identity_hash=None if structural else scope.identity_hash,
    )
    ids = [
        row.get("session_id")
        for row in result.get("rows", [])
        if isinstance(row, dict) and row.get("session_id")
    ]
    return tuple(dict.fromkeys(ids))


def _scope_window_seconds(scope: UpdateScope) -> int:
    if scope.window_seconds is not None:
        return scope.window_seconds
    if scope.active_after:
        try:
            parsed = datetime.fromisoformat(scope.active_after)
        except ValueError:
            return _DEFAULT_RECENT_WINDOW_SECONDS
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return max(1, int(time.time() - parsed.timestamp()))
    return _DEFAULT_RECENT_WINDOW_SECONDS


def _run_update_tier(tier: str, scope: UpdateScope) -> None:
    providers = scope.providers
    if tier == "direct":
        ids = scope.exact_session_ids
        if not ids and (scope.uri or scope.identity_hash):
            ids = _scope_session_ids(scope, structural=False)
        if ids:
            chatlas_update(session_ids=tuple(ids), providers=providers)
        return
    if tier == "index":
        ids = _scope_session_ids(scope, structural=True)
        if ids:
            chatlas_update(session_ids=ids, providers=providers)
        return
    if tier == "recent":
        chatlas_update(providers=providers, window_seconds=_scope_window_seconds(scope))
        return
    chatlas_update(providers=providers)


def _default_read_satisfied(payload: dict[str, object]) -> bool:
    return int(payload.get("returned_row_count", 0) or 0) > 0


def run_read_with_update(
    args: argparse.Namespace,
    *,
    read_fn,
    scope_fn,
    satisfied_fn=None,
) -> dict[str, object]:
    mode = getattr(args, "update", None)
    if mode is None:
        return read_fn(args)
    satisfied = satisfied_fn or _default_read_satisfied
    scope = scope_fn(args)
    if mode == "auto":
        start = _start_update_tier(scope)
        tiers = _UPDATE_TIER_LADDER[_UPDATE_TIER_LADDER.index(start) :]
    elif mode in _UPDATE_TIER_LADDER:
        tiers = (mode,)
    else:
        raise CliError(
            f"unsupported --update tier: {mode} (choose from {', '.join(_UPDATE_TIER_LADDER)})"
        )
    payload: dict[str, object] = {}
    for tier in tiers:
        _run_update_tier(tier, scope)
        payload = read_fn(args)
        if satisfied(payload):
            return payload
    return payload


def _chatlas_query_scope(args: argparse.Namespace) -> UpdateScope:
    return UpdateScope(
        providers=optional_string_tuple(args.providers),
        active_after=normalize_cli_timestamp(args.active_after, field="--active-after"),
        exact_session_ids=(args.session_id,) if args.session_id else (),
        uri=args.uri,
        identity_hash=args.identity_hash,
    )


def _chatlas_recents_scope(args: argparse.Namespace) -> UpdateScope:
    return UpdateScope(
        providers=optional_string_tuple(args.providers),
        window_seconds=since_window_seconds(args.since, args.since_date),
        exact_session_ids=(args.session_id,) if args.session_id else (),
        uri=args.uri,
        identity_hash=args.identity_hash,
    )


def _chatlas_stats_scope(args: argparse.Namespace) -> UpdateScope:
    return UpdateScope(providers=optional_string_tuple(args.providers))


def _chatlas_views_scope(args: argparse.Namespace) -> UpdateScope:
    return UpdateScope(
        providers=optional_string_tuple(args.providers),
        active_after=normalize_cli_timestamp(
            getattr(args, "active_after", None), field="--active-after"
        ),
        exact_session_ids=(args.session_id,)
        if getattr(args, "session_id", None)
        else (),
        uri=getattr(args, "uri", None),
        identity_hash=getattr(args, "identity_hash", None),
    )


def _cmd_chatlas_query(args: argparse.Namespace) -> int:
    payload = run_read_with_update(
        args,
        read_fn=lambda namespace: chatlas_query(
            **_chatlas_query_selector_kwargs(namespace)
        ),
        scope_fn=_chatlas_query_scope,
    )
    if args.field is not None:
        for row in payload.get("rows", []):
            value = row.get(args.field) if isinstance(row, dict) else None
            if value is not None:
                print(value)
        return 0
    print_chatlas_output(
        payload, output=args.output, text_renderer=format_chatlas_query_text
    )
    return 0


def _cmd_chatlas_utils_tagger(args: argparse.Namespace) -> int:
    return run_tagger(
        profile_name=args.profile,
        providers=optional_string_tuple(args.providers),
        limit=args.limit,
        auto_test_rate=args.auto_test_rate,
        random_seed=args.random_seed,
    )


def _cmd_chatlas_annotations_add(args: argparse.Namespace) -> int:
    tags, changed = add_session_tag(args.identity_hash, args.tag)
    print_chatlas_output(
        {
            "status": "ok",
            "command": "chatlas annotations add",
            "identity_hash": args.identity_hash,
            "tags": tags,
            "changed": changed,
        },
        output=args.output,
    )
    return 0


def _cmd_chatlas_annotations_remove(args: argparse.Namespace) -> int:
    tags, changed = remove_session_tag(args.identity_hash, args.tag)
    print_chatlas_output(
        {
            "status": "ok",
            "command": "chatlas annotations remove",
            "identity_hash": args.identity_hash,
            "tags": tags,
            "changed": changed,
        },
        output=args.output,
    )
    return 0


def _cmd_chatlas_annotations_list(args: argparse.Namespace) -> int:
    tags = list_all_tags()
    print_chatlas_output(
        {
            "status": "ok",
            "command": "chatlas annotations list",
            "tags": tags,
            "distinct_tags": len(tags),
            "total_tag_uses": sum(entry["count"] for entry in tags),
        },
        output=args.output,
    )
    return 0


def _cmd_chatlas_recents(args: argparse.Namespace) -> int:
    truncate_length = None if args.full else 200
    payload = run_read_with_update(
        args,
        read_fn=lambda namespace: chatlas_recents(
            since=namespace.since,
            since_date=namespace.since_date,
            last_turns=namespace.last_turns,
            truncate_length=truncate_length,
            uri=namespace.uri,
            identity_hash=namespace.identity_hash,
            project=namespace.project,
            project_base=namespace.project_base,
            providers=optional_string_tuple(namespace.providers),
            instances=optional_string_tuple(namespace.instances),
            provider_instance_fingerprint=namespace.provider_instance_fingerprint,
            session_id=namespace.session_id,
            display_name=namespace.display_name,
            extractable_only=namespace.extractable,
            min_user_turns=namespace.min_user_turns,
            limit=namespace.limit,
        ),
        scope_fn=_chatlas_recents_scope,
        satisfied_fn=lambda payload: int(payload.get("entry_count", 0) or 0) > 0,
    )
    print_chatlas_output(
        payload,
        output=args.output,
        text_renderer=lambda rendered: format_chatlas_recents_text(rendered).rstrip(
            "\n"
        ),
    )
    return 0


def _cmd_chatlas_ping(args: argparse.Namespace) -> int:
    payload = chatlas_ping(
        lines=args.lines,
        interval_seconds=args.interval,
        rounds=args.rounds,
        window_seconds=args.window_seconds,
        providers=optional_string_tuple(args.providers),
    )
    print_chatlas_output(payload, output=args.output)
    return 0


def _cmd_chatlas_provider_query(args: argparse.Namespace) -> int:
    payload = chatlas_provider_query(
        provider=args.provider,
        instances=optional_string_tuple(args.instances),
        session_ids=tuple(args.session_ids or ()),
    )
    print_chatlas_output(payload, output=args.output)
    return 0


def _chatlas_gates_arg(args: argparse.Namespace) -> dict[str, object] | None:
    import json

    from agentos._core.errors import CliError

    gates = None
    if args.gates:
        try:
            gates = json.loads(args.gates)
        except json.JSONDecodeError as exc:
            raise CliError(f"chatlas anchory --gates is not valid JSON: {exc}")
        if not isinstance(gates, dict):
            raise CliError(
                "chatlas anchory --gates must be a JSON object with the dossier gate namespaces"
            )
    return gates


def _cmd_chatlas_anchory_preview(args: argparse.Namespace) -> int:
    from agentos.chatlas.anchory import chatlas_anchory_preview

    payload = chatlas_anchory_preview(
        members=tuple(args.members),
        hint=args.hint,
        gates=_chatlas_gates_arg(args),
        line_content=args.line_content,
        issue_context=tuple(args.issues or ()),
        detail=args.detail,
        radius=args.radius,
    )
    print_chatlas_output(payload, output=args.output)
    return 0


def _cmd_chatlas_anchory_register(args: argparse.Namespace) -> int:
    from agentos.chatlas.anchory import chatlas_anchory_register

    payload = chatlas_anchory_register(
        members=tuple(args.members),
        hint=args.hint,
        gates=_chatlas_gates_arg(args),
        line_content=args.line_content,
        issue_context=tuple(args.issues or ()),
        detail=args.detail,
        radius=args.radius,
    )
    print_chatlas_output(payload, output=args.output)
    return 0


def _cmd_chatlas_anchory_batch_preview(args: argparse.Namespace) -> int:
    from agentos.chatlas.anchory_batch import (
        chatlas_anchory_batch_preview,
        load_anchor_batch,
    )

    payload = chatlas_anchory_batch_preview(items=load_anchor_batch(Path(args.input)))
    print_chatlas_output(payload, output=args.output)
    return 0


def _cmd_chatlas_anchory_batch_register(args: argparse.Namespace) -> int:
    from agentos.chatlas.anchory_batch import (
        chatlas_anchory_batch_register,
        load_anchor_batch,
    )

    payload = chatlas_anchory_batch_register(items=load_anchor_batch(Path(args.input)))
    print_chatlas_output(payload, output=args.output)
    return 0


def _cmd_chatlas_anchory_resolve(args: argparse.Namespace) -> int:
    from agentos.chatlas.anchory import chatlas_anchory_resolve

    payload = chatlas_anchory_resolve(
        args.anchor,
        radius=args.radius,
        detail=args.detail,
    )
    print_chatlas_output(payload, output=args.output)
    return 0


def _cmd_chatlas_anchory_reattach(args: argparse.Namespace) -> int:
    from agentos.chatlas.anchory import chatlas_line_anchor_reattach

    payload = chatlas_line_anchor_reattach(
        args.anchor,
        depot_root=args.depot,
    )
    print_chatlas_output(payload, output=args.output)
    return 0


def _cmd_chatlas_anchory_enrich(args: argparse.Namespace) -> int:
    from agentos.chatlas.anchory import chatlas_line_issue_enrich

    payload = chatlas_line_issue_enrich(
        args.anchor,
        issue_context=tuple(args.issues or ()),
    )
    print_chatlas_output(payload, output=args.output)
    return 0


def _cmd_chatlas_anchory_sessions(args: argparse.Namespace) -> int:
    from agentos.chatlas.anchory import chatlas_anchory_sessions

    print_chatlas_output(
        chatlas_anchory_sessions(
            sources=tuple(args.sources),
            regex=args.regex,
            glob=args.glob,
        ),
        output=args.output,
    )
    return 0


def _cmd_chatlas_anchory_stats(args: argparse.Namespace) -> int:
    from agentos.chatlas.anchory import (
        chatlas_anchory_stats,
        format_chatlas_anchory_stats_pretty,
    )

    print_chatlas_output(
        chatlas_anchory_stats(),
        output=args.output,
        text_renderer=format_chatlas_anchory_stats_pretty,
    )
    return 0


def _cmd_chatlas_views_get(args: argparse.Namespace) -> int:
    payload = run_read_with_update(
        args,
        read_fn=lambda namespace: chatlas_views_get(
            **_chatlas_index_selector_kwargs(namespace),
            view=namespace.view,
            range_spec=namespace.range_spec,
            contains=namespace.contains,
            role=namespace.role,
            around=normalize_cli_timestamp(namespace.around, field="--around"),
            radius=namespace.radius,
            file_read=namespace.inline_file_read,
            file_write=namespace.inline_file_write,
            file_touched=namespace.inline_file_touched,
            tool_contains=namespace.inline_tool_contains,
            tool_name=namespace.inline_tool_name,
            filters=tuple(namespace.filters or ()),
        ),
        scope_fn=_chatlas_views_scope,
        satisfied_fn=lambda _payload: True,
    )
    print_chatlas_output(
        payload, output=args.output, text_renderer=format_chatlas_view_text
    )
    return 0


def _cmd_chatlas_raw_path(args: argparse.Namespace) -> int:
    print_chatlas_output(
        chatlas_raw_paths(**_chatlas_index_selector_kwargs(args)),
        output=args.output,
        text_renderer=lambda payload: "\n".join(payload["paths"]),
    )
    return 0


def _cmd_chatlas_raw_export(args: argparse.Namespace) -> int:
    payload = chatlas_raw_export(
        **_chatlas_index_selector_kwargs(args),
    )
    print_chatlas_output(payload, output=args.output)
    return 0


def _cmd_chatlas_views_list(args: argparse.Namespace) -> int:
    payload = chatlas_views_list()
    print_chatlas_output(payload, output=args.output)
    return 0


def _cmd_chatlas_products_list(args: argparse.Namespace) -> int:
    print_chatlas_output(chatlas_products_list(), output=args.output)
    return 0


def _cmd_chatlas_chat_index_status(args: argparse.Namespace) -> int:
    payload = chatlas_chat_index_status(
        **_chatlas_index_selector_kwargs(
            args, include_active_after=False, include_sort_limit=False
        )
    )
    print_chatlas_output(payload, output=args.output)
    return 0


def _cmd_chatlas_chat_index_show(args: argparse.Namespace) -> int:
    payload = chatlas_chat_index_show(
        **_chatlas_index_selector_kwargs(
            args, include_active_after=False, include_sort_limit=False
        )
    )
    print_chatlas_output(payload, output=args.output)
    return 0


def _cmd_chatlas_chat_index_path(args: argparse.Namespace) -> int:
    payload = chatlas_chat_index_path(
        **_chatlas_index_selector_kwargs(
            args, include_active_after=False, include_sort_limit=False
        )
    )
    print_chatlas_output(
        payload,
        output=args.output,
        text_renderer=lambda rendered: str(rendered["path"]),
    )
    return 0


def _cmd_chatlas_chat_index_files(args: argparse.Namespace) -> int:
    payload = chatlas_chat_index_files(
        **_chatlas_index_selector_kwargs(
            args, include_active_after=False, include_sort_limit=False
        )
    )
    print_chatlas_output(payload, output=args.output)
    return 0


def _cmd_chatlas_chat_index_deltas(args: argparse.Namespace) -> int:
    payload = chatlas_chat_index_deltas(
        **_chatlas_index_selector_kwargs(
            args, include_active_after=False, include_sort_limit=False
        )
    )
    print_chatlas_output(payload, output=args.output)
    return 0


def _cmd_chatlas_chat_index_head(args: argparse.Namespace) -> int:
    payload = chatlas_chat_index_head(
        **_chatlas_index_selector_kwargs(
            args, include_active_after=False, include_sort_limit=False
        )
    )
    print_chatlas_output(payload, output=args.output)
    return 0


def _cmd_chatlas_chat_index_home(args: argparse.Namespace) -> int:
    payload = chatlas_chat_index_home(
        line_content=args.line_content,
        **_chatlas_index_selector_kwargs(
            args, include_active_after=False, include_sort_limit=False
        ),
    )
    print_chatlas_output(payload, output=args.output)
    return 0


def _cmd_chatlas_chat_index_source(args: argparse.Namespace) -> int:
    payload = chatlas_chat_index_source(
        **_chatlas_index_selector_kwargs(
            args, include_active_after=False, include_sort_limit=False
        )
    )
    print_chatlas_output(payload, output=args.output)
    return 0


def _cmd_chatlas_chat_index_tail(args: argparse.Namespace) -> int:
    payload = chatlas_chat_index_tail(
        detail=args.detail,
        **_chatlas_index_selector_kwargs(
            args, include_active_after=False, include_sort_limit=False
        ),
    )
    print_chatlas_output(payload, output=args.output)
    return 0


def _cmd_chatlas_chat_index_audit(args: argparse.Namespace) -> int:
    payload = chatlas_chat_index_audit(
        surface=args.surface,
        **_chatlas_index_selector_kwargs(
            args, include_active_after=False, include_sort_limit=False
        ),
    )
    print_chatlas_output(payload, output=args.output)
    # Blocking findings are a refusal, not a crash: the complete result is
    # always printed so a caller can act on it.
    return 1 if payload["blocking_finding_count"] else 0


def _cmd_chatlas_chat_index_scaffold(args: argparse.Namespace) -> int:
    payload = chatlas_chat_index_scaffold(
        stage=args.stage,
        mode=args.mode,
        **_chatlas_index_selector_kwargs(
            args, include_active_after=False, include_sort_limit=False
        ),
    )
    print_chatlas_output(payload, output=args.output)
    return 0


def _cmd_chatlas_chat_index_validate(args: argparse.Namespace) -> int:
    payload = chatlas_chat_index_validate(plan=args.plan)
    print_chatlas_output(payload, output=args.output)
    return 0


def _cmd_chatlas_chat_index_apply(args: argparse.Namespace) -> int:
    payload = chatlas_chat_index_apply(plan=args.plan)
    print_chatlas_output(payload, output=args.output)
    return 0 if payload["ok"] else 1


def _cmd_chatlas_project_index_audit(args: argparse.Namespace) -> int:
    payload = project_index_audit(
        args.depot,
        cursor_root=Path(args.cursor_root).expanduser().resolve()
        if args.cursor_root
        else None,
    )
    print_chatlas_output(payload, output=args.output)
    return 0


def _cmd_chatlas_project_index_reconcile(args: argparse.Namespace) -> int:
    payload = project_index_reconcile(
        args.depot,
        cursor_root=Path(args.cursor_root).expanduser().resolve()
        if args.cursor_root
        else None,
        reset=args.reset,
    )
    print_chatlas_output(payload, output=args.output)
    return 0


def _cmd_chatlas_products_get(args: argparse.Namespace) -> int:
    payload = chatlas_products_get(
        product=args.product,
        explain=args.explain,
        **_chatlas_index_selector_kwargs(args),
    )
    print_chatlas_output(payload, output=args.output)
    return 0


def _cmd_chatlas_products_status(args: argparse.Namespace) -> int:
    payload = chatlas_products_status(
        product=args.product,
        explain=args.explain,
        **_chatlas_index_selector_kwargs(args),
    )
    print_chatlas_output(payload, output=args.output)
    return 0


def _cmd_chatlas_products_path(args: argparse.Namespace) -> int:
    payload = chatlas_products_path(
        product=args.product,
        explain=args.explain,
        **_chatlas_index_selector_kwargs(args),
    )
    print_chatlas_output(
        payload,
        output=args.output,
        text_renderer=lambda rendered: str(rendered.get("path") or ""),
    )
    return 0


def _cmd_chatlas_products_stage(args: argparse.Namespace) -> int:
    payload = chatlas_products_stage(
        product=args.product,
        **_chatlas_index_selector_kwargs(args),
    )
    print_chatlas_output(payload, output=args.output)
    return 0


def _cmd_chatlas_products_commit(args: argparse.Namespace) -> int:
    payload = chatlas_products_commit(
        stage_id=args.stage_id,
        allow_low_compression=args.allow_low_compression,
        allow_aggressive_compression=args.allow_aggressive_compression,
    )
    print_chatlas_output(payload, output=args.output)
    return 0


def _cmd_chatlas_products_check(args: argparse.Namespace) -> int:
    payload = chatlas_products_check(
        stage_id=args.stage_id,
        allow_low_compression=args.allow_low_compression,
        allow_aggressive_compression=args.allow_aggressive_compression,
    )
    print_chatlas_output(payload, output=args.output)
    return 0 if payload.get("status") == "ok" else 1


def _cmd_chatlas_products_scaffold(args: argparse.Namespace) -> int:
    payload = chatlas_products_scaffold(stage_id=args.stage_id, force=args.force)
    print_chatlas_output(payload, output=args.output)
    return 0


def _cmd_chatlas_products_produce(args: argparse.Namespace) -> int:
    payload = chatlas_products_produce(
        product=args.product,
        **_chatlas_index_selector_kwargs(args),
    )
    print_chatlas_output(payload, output=args.output)
    return 0


def _cmd_chatlas_products_run_produce(args: argparse.Namespace) -> int:
    config = _chatlas_products_run_config()
    use_config = args.run_produce_provider is None
    provider = args.run_produce_provider or config.get("agent_provider")
    if not provider:
        print(
            "error: --agent-provider is required (no default in chatlas config)",
            file=sys.stderr,
        )
        return 1
    profile = (
        args.profile
        if args.profile is not None
        else (config.get("profile") if use_config else None)
    )
    model = (
        args.model
        if args.model is not None
        else (config.get("model") if use_config else None)
    )

    query_payload = chatlas_query(
        **_chatlas_query_selector_kwargs(args),
        row_shape="full",
    )
    rows = query_payload.get("rows", [])
    if not rows:
        print_chatlas_output(
            {
                "status": "ok",
                "command": "chatlas products run-produce",
                "run_count": 0,
                "message": "no sessions matched the selector",
            },
            output=args.output,
        )
        return 0
    payload = chatlas_products_run_produce(
        product=args.product,
        provider=provider,
        profile=profile,
        model=model,
        dry_run=args.dry_run,
        force=args.force,
        concurrency=args.concurrency,
        rows=rows,
    )
    print_chatlas_output(payload, output=args.output)
    return 1 if payload.get("failed_count", 0) else 0


def _chatlas_products_run_config() -> dict[str, object]:
    import json

    config_path = default_chatlas_root() / "config.json"
    if not config_path.is_file():
        return {}
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    chatlas_block = payload.get("chatlas", payload)
    if not isinstance(chatlas_block, dict):
        return {}
    run_produce = chatlas_block.get("run_produce", {})
    if not isinstance(run_produce, dict):
        return {}
    return run_produce


def _add_chatlas_provider_argument(
    parser: argparse.ArgumentParser, *, help_text: str
) -> None:
    parser.add_argument(
        "--provider",
        choices=_CHATLAS_PROVIDER_CHOICES,
        action="append",
        dest="providers",
        help=help_text,
    )


def _add_chatlas_index_selector_arguments(
    parser: argparse.ArgumentParser,
    *,
    include_active_after: bool = True,
    include_sort_limit: bool = True,
) -> None:
    parser.add_argument(
        "--uri",
        default=None,
        help="Match the indexed session URI exactly.",
    )
    parser.add_argument(
        "--identity-hash",
        default=None,
        help="Match sessions whose indexed identity hash starts with this value (prefix or full hash).",
    )
    parser.add_argument(
        "--project",
        type=Path,
        nargs="?",
        const=Path("."),
        default=None,
        help="Match the indexed project_path to this resolved project path exactly. Bare --project uses the current directory.",
    )
    parser.add_argument(
        "--project-base",
        default=None,
        help="Match the basename of the indexed project_path exactly.",
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
    if include_active_after:
        parser.add_argument(
            "--active-after",
            default=None,
            help="Keep sessions active at or after this ISO 8601 timestamp (naive values are local; use Z or an offset for UTC/explicit timezones).",
        )
    if include_sort_limit:
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


def _chatlas_index_selector_kwargs(
    args: argparse.Namespace,
    *,
    include_active_after: bool = True,
    include_sort_limit: bool = True,
) -> dict[str, object]:
    selectors: dict[str, object] = {
        "uri": args.uri,
        "identity_hash": args.identity_hash,
        "project": args.project,
        "project_base": args.project_base,
        "providers": optional_string_tuple(args.providers),
        "instances": optional_string_tuple(args.instances),
        "provider_instance_fingerprint": args.provider_instance_fingerprint,
        "session_id": args.session_id,
        "display_name": args.display_name,
        "extractable_only": args.extractable,
    }
    if include_active_after:
        selectors["active_after"] = normalize_cli_timestamp(
            args.active_after, field="--active-after"
        )
    if include_sort_limit:
        selectors["sort"] = args.sort
        selectors["limit"] = args.limit
    return selectors


def _add_chatlas_progress_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--verbose-mode",
        choices=_CHATLAS_UPDATE_VERBOSE_MODES,
        default="progress",
        help="Progress feedback mode: `progress` prints live update messages to stderr; `quiet` disables them (default: progress).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Print nothing after the run; progress still follows --verbose-mode.",
    )


def _add_chatlas_index_update_arguments(parser: argparse.ArgumentParser) -> None:
    _add_chatlas_provider_argument(
        parser,
        help_text="Restrict the update run to a provider family. Repeat to include multiple providers.",
    )
    parser.add_argument(
        "--session-id",
        action="append",
        dest="session_ids",
        help="Refresh only the named session(s). Uses the index as locator; on miss, walks every configured provider instance. Optionally scope with --provider.",
    )
    _add_chatlas_progress_arguments(parser)
    parser.add_argument(
        "--disable-cache",
        action="store_true",
        help="Disable all Chatlas update caches. Overrides `--scan-cache` and `--session-index-cache`.",
    )
    parser.add_argument(
        "--full-scan",
        action="store_true",
        help="Bypass cold-session cache shortcuts and compare all discovered sessions.",
    )
    parser.add_argument(
        "--recent-window",
        default=None,
        help="Only re-ingest sessions whose source was touched within this window (e.g. 60s, 30m, 1h, 2d). Skips older sessions before derivation.",
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
    parser.add_argument(
        "--trust",
        choices=("append", "verify", "rebuild"),
        default=None,
        help=(
            "Normalization trust tier for delta-capable sessions: append resumes "
            "blindly from the checkpoint, verify re-checks frozen provenance, "
            "rebuild re-derives everything. Default: append for --session-id "
            "refreshes, verify otherwise."
        ),
    )


def _add_chatlas_query_selector_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--uri",
        default=None,
        help="Match the indexed session URI exactly.",
    )
    parser.add_argument(
        "--identity-hash",
        default=None,
        help="Match sessions whose indexed identity hash starts with this value (prefix or full hash).",
    )
    parser.add_argument(
        "--project",
        type=Path,
        default=None,
        help="Match the indexed project_path to this resolved project path exactly.",
    )
    parser.add_argument(
        "--project-base",
        default=None,
        help="Match the basename of the indexed project_path exactly.",
    )
    _add_chatlas_provider_argument(
        parser,
        help_text="Restrict query to a provider family. Repeat to include multiple providers.",
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
        "--active-after",
        default=None,
        help="Keep sessions active at or after this timestamp (naive values are local; use Z or an offset for UTC/explicit timezones).",
    )
    parser.add_argument(
        "--idle-for",
        dest="idle_for",
        default=None,
        help=(
            "Keep only sessions untouched for at least this long (30s, 10m, 4h, 3d, 2w). "
            "Use it to skip sessions still being worked in, whose summaries would go stale immediately."
        ),
    )
    parser.add_argument(
        "--sort",
        choices=("lexical", "newest", "oldest"),
        default="lexical",
        help="Sort order for returned sessions (default: lexical).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of sessions to return.",
    )
    parser.add_argument(
        "--scan-limit",
        type=int,
        default=None,
        help="Maximum number of index candidates to scan before raw and standard-model filters.",
    )
    parser.add_argument(
        "--raw-contains",
        action="append",
        default=None,
        help="Keep only sessions whose backing artifacts contain this literal text. Repeat for AND matching.",
    )
    parser.add_argument(
        "--user-contains",
        action="append",
        default=None,
        help="Keep only sessions whose visible user message text contains this literal text. Repeat for AND matching.",
    )
    parser.add_argument(
        "--assistant-contains",
        action="append",
        default=None,
        help="Keep only sessions whose visible assistant message text contains this literal text. Repeat for AND matching.",
    )
    parser.add_argument(
        "--message-contains",
        action="append",
        default=None,
        help="Keep only sessions whose visible user or assistant message text contains this literal text. Repeat for AND matching.",
    )
    parser.add_argument(
        "--file-read",
        action="append",
        default=None,
        help="Keep only sessions with a reading tool invocation whose path contains this text. Repeat for AND matching.",
    )
    parser.add_argument(
        "--file-write",
        action="append",
        default=None,
        help="Keep only sessions with a mutating tool invocation whose path contains this text. Repeat for AND matching.",
    )
    parser.add_argument(
        "--file-touched",
        action="append",
        default=None,
        help="Keep only sessions with any tool invocation (read or write) whose path contains this text. Repeat for AND matching.",
    )
    parser.add_argument(
        "--tool-contains",
        action="append",
        default=None,
        help="Keep only sessions with a tool invocation whose name/input/output contains this text (recall tier, no verb claim). Repeat for AND matching.",
    )
    parser.add_argument(
        "--tool-name",
        default=None,
        help="Restrict --tool-contains matching to this tool; alone, keep only sessions that used the tool.",
    )
    parser.add_argument(
        "--min-user-turns",
        type=int,
        default=None,
        help="Keep only sessions with at least this many visible user turns.",
    )
    parser.add_argument(
        "--tag",
        action="append",
        default=None,
        dest="tags",
        help="Keep only sessions whose annotations.tags contains this tag. Repeat for AND matching.",
    )
    parser.add_argument(
        "--without-tag",
        action="append",
        default=None,
        dest="without_tags",
        help="Exclude sessions whose annotations.tags contains this tag. Repeat for AND exclusion.",
    )
    parser.add_argument(
        "--field",
        choices=("session_id", "identity_hash"),
        default=None,
        help="Print one field value per matching row.",
    )


def _chatlas_idle_cutoff(idle_for: str | None) -> str | None:
    """Translate an idle duration into the `active_before` timestamp the core filters on."""
    if idle_for is None:
        return None
    seconds = parse_duration_seconds(idle_for, field_name="--idle-for")
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=seconds)
    return cutoff.isoformat().replace("+00:00", "Z")


def _chatlas_query_selector_kwargs(args: argparse.Namespace) -> dict[str, object]:
    return {
        "uri": args.uri,
        "identity_hash": args.identity_hash,
        "project": args.project,
        "project_base": args.project_base,
        "providers": optional_string_tuple(args.providers),
        "session_id": args.session_id,
        "display_name": args.display_name,
        "extractable_only": args.extractable,
        "active_after": normalize_cli_timestamp(
            args.active_after, field="--active-after"
        ),
        "active_before": _chatlas_idle_cutoff(getattr(args, "idle_for", None)),
        "sort": args.sort,
        "limit": args.limit,
        "scan_limit": args.scan_limit,
        "raw_contains": optional_string_tuple(args.raw_contains),
        "user_contains": optional_string_tuple(args.user_contains),
        "assistant_contains": optional_string_tuple(args.assistant_contains),
        "message_contains": optional_string_tuple(args.message_contains),
        "file_read": optional_string_tuple(args.file_read),
        "file_write": optional_string_tuple(args.file_write),
        "file_touched": optional_string_tuple(args.file_touched),
        "tool_contains": optional_string_tuple(args.tool_contains),
        "tool_name": args.tool_name,
        "min_user_turns": args.min_user_turns,
        "tags": optional_string_tuple(args.tags),
        "without_tags": optional_string_tuple(args.without_tags),
    }


def _add_chatlas_view_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--view",
        choices=("full", "transcript", "user", "replay", "events", "zip-transcript"),
        default=None,
        help="Named standard-model view (default: full; events when selection flags are used).",
    )


def _add_chatlas_product_consumer_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--product",
        required=True,
        help="Registered Chatlas product name.",
    )
    _add_chatlas_index_selector_arguments(parser)
    parser.add_argument(
        "--explain",
        action="store_true",
        help="Include product fingerprint diagnostics.",
    )


def _add_chatlas_local_project_argument(
    parser: argparse.ArgumentParser,
    *,
    default: object = argparse.SUPPRESS,
) -> None:
    parser.add_argument(
        "--project",
        nargs="?",
        type=Path,
        const=Path("."),
        default=default,
        help=(
            "Agentos project root to sync or inspect. Bare --project uses the current directory; "
            "omitting --project discovers the project from the current directory."
        ),
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
