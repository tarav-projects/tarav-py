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
from agentos.chatlas.core import (
    chatlas_index_update,
    chatlas_raw_export,
    chatlas_raw_paths,
    chatlas_update,
)
from agentos.chatlas.chat_index_apply import chatlas_chat_index_apply
from agentos.chatlas.chat_index_audit import chatlas_chat_index_audit
from agentos.chatlas.chat_index_plan import chatlas_chat_index_scaffold
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
from agentos.chatlas.delta_scan import chatlas_index_redo, chatlas_index_reset
from agentos.chatlas.gc import chatlas_gc
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
from agentos.chatlas.production_config import load_chatlas_run_produce_config
from agentos.chatlas.output import (
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
    config = load_chatlas_run_produce_config()
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
