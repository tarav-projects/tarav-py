# $kw: ^chatlas2-cli --from Chatlas.Query.Surface --from Usage.Surface --from Raw.Archive --note [CT] Chatlas2 exposes one-session normalization, compact turn lookup and hydration, disposable views, explicit grounding, and hermetic corpus inspection without mutating current Chatlas --supp ^c20260814-13u ^c20260814-15u ^c20260815-16u ^c20260815-31u ^c20260816-23u ^d20260816-1u ^d20260816-28u ^d20260816-31u
from __future__ import annotations

import argparse
import json
from pathlib import Path

from tarav._core.errors import CliError
from tarav.chatlas.index_query import select_one_chatlas_index_row
from tarav.chatlas.providers import supported_chatlas_provider_families
from tarav.chatlas.time_interface import normalize_cli_timestamp

from .cache import (
    materialize_normal_model_cache,
    normal_model_cache_status,
)
from .chat_index import (
    apply_chat_index_capture_plan,
    scaffold_chat_index_capture_plan,
    validate_chat_index_capture_plan,
)
from .corpus import (
    check_corpus,
    load_capture_records,
    load_script_spec,
    prepare_capture,
    register_candidate,
    verify_corpus,
)
from .anchory import (
    CHATLAS2_ANCHOR_BATCH_SCHEMA,
    chatlas2_anchory_batch_preview,
    chatlas2_anchory_batch_register,
    chatlas2_anchory_preview,
    chatlas2_anchory_register,
    chatlas2_anchory_resolve,
    chatlas2_message_support_preview,
    chatlas2_message_support_register,
    format_support_member_ref,
    load_anchor_batch,
)
from .message_ref import chat_message_ref
from .normal_model import (
    compute_normal_model,
    provide_normal_model,
    provide_normal_model_reader,
)
from .query import SUPPORTED_QUERY_PROVIDERS, query_chat_messages, query_sessions
from .views import list_views, project_view, view_names


def _cmd_normalize(args: argparse.Namespace) -> int:
    selector = {
        "session_id": args.session_id,
        "identity_hash": args.identity_hash,
        "chatlas_root": Path(args.chatlas_root) if args.chatlas_root else None,
    }
    model = (
        compute_normal_model(**selector, include_raw=True)
        if args.include_raw
        else provide_normal_model(**selector, refresh=args.refresh)
    )
    if args.json:
        print(json.dumps(model, indent=2, ensure_ascii=False))
        return 0
    annotations = model["annotations"]
    print(f"session: {model['session']['session_id']}")
    print(f"sources: {len(model['sources'])}")
    print(f"events: {len(model['events'])}")
    print(f"chat_messages: {len(annotations['chat_messages'])}")
    print(f"chat_turns: {len(annotations['chat_turns'])}")
    print(f"agent_loaded_contexts: {len(annotations['agent_loaded_contexts'])}")
    return 0


def _print_payload(payload: object, *, pretty: bool) -> None:
    print(json.dumps(payload, indent=2 if pretty else None, ensure_ascii=False))


def _model_reader_for_selector(args: argparse.Namespace):
    return provide_normal_model_reader(
        session_id=args.session_id,
        identity_hash=args.identity_hash,
        chatlas_root=Path(args.chatlas_root) if args.chatlas_root else None,
    )


def _message_payload(session, record):
    message = record["message"]
    at = record["at"]
    ref = chat_message_ref(message)
    member = {
        "session": session["identity_hash"],
        "message_address": ref["message_address"],
        "message_hash": ref["message_hash"],
        "at": at,
    }
    return {
        "member_ref": format_support_member_ref(member),
        "member": member,
        "at": at,
        "message": message,
    }


def _cmd_messages_list(args: argparse.Namespace) -> int:
    reader = _model_reader_for_selector(args)
    session = reader.metadata["model"]["session"]
    records = list(reader.iter_chat_message_records(side=args.side, limit=args.limit))
    _print_payload(
        {
            "session": session,
            "count": len(records),
            "messages": [_message_payload(session, record) for record in records],
        },
        pretty=args.json,
    )
    return 0


def _cmd_messages_find(args: argparse.Namespace) -> int:
    reader = _model_reader_for_selector(args)
    session = reader.metadata["model"]["session"]
    records = list(
        reader.iter_chat_message_records(
            side=args.side,
            text=args.text,
            exact=args.exact,
            limit=args.limit,
        )
    )
    _print_payload(
        {
            "session": session,
            "count": len(records),
            "messages": [_message_payload(session, record) for record in records],
        },
        pretty=args.json,
    )
    return 0


def _cmd_turns_list(args: argparse.Namespace) -> int:
    reader = _model_reader_for_selector(args)
    session = reader.metadata["model"]["session"]
    turns = list(reader.iter_chat_turns(side=args.side, limit=args.limit))
    _print_payload(
        {"session": session, "count": len(turns), "turns": turns},
        pretty=args.json,
    )
    return 0


def _cmd_turns_get(args: argparse.Namespace) -> int:
    reader = _model_reader_for_selector(args)
    session = reader.metadata["model"]["session"]
    turn = reader.find_chat_turn(
        turn_address=args.turn_address,
        message_address=args.message_address,
    )
    if turn is None:
        raise CliError("Chatlas2 Chat.Turn not found")
    payload = reader.hydrate_chat_turn(turn) if args.hydrate else {"turn": turn}
    _print_payload({"session": session, **payload}, pretty=args.json)
    return 0


def _cmd_sessions_query(args: argparse.Namespace) -> int:
    payload = query_sessions(
        identity_hash=args.identity_hash,
        project=Path(args.project) if args.project else None,
        project_base=args.project_base,
        providers=tuple(args.providers) if args.providers else None,
        session_id=args.session_id,
        active_after=normalize_cli_timestamp(
            args.active_after, field="--active-after"
        ),
        sort=args.sort,
        limit=args.limit,
        chatlas_root=Path(args.chatlas_root) if args.chatlas_root else None,
    )
    _print_payload(payload, pretty=args.json)
    return 0


def _cmd_chat_query(args: argparse.Namespace) -> int:
    payload = query_chat_messages(
        identity_hash=args.identity_hash,
        project=Path(args.project) if args.project else None,
        project_base=args.project_base,
        providers=tuple(args.providers) if args.providers else None,
        session_id=args.session_id,
        active_after=normalize_cli_timestamp(
            args.active_after, field="--active-after"
        ),
        side=args.side,
        text_exact=args.text_exact,
        text_contains=args.text_contains,
        text_regex=args.text_regex,
        text_verbatim=args.text_verbatim,
        after=normalize_cli_timestamp(args.after, field="--after"),
        before=normalize_cli_timestamp(args.before, field="--before"),
        message_address=args.message_address,
        include_turn_ref=args.include_turn_ref,
        sort=args.sort,
        session_limit=args.session_limit,
        limit=args.limit,
        chatlas_root=Path(args.chatlas_root) if args.chatlas_root else None,
    )
    _print_payload(payload, pretty=args.json)
    return 0


def _cmd_chat_index_scaffold(args: argparse.Namespace) -> int:
    payload = scaffold_chat_index_capture_plan(
        stage=Path(args.stage),
        session_id=args.session_id,
        identity_hash=args.identity_hash,
        chatlas_root=Path(args.chatlas_root) if args.chatlas_root else None,
    )
    _print_payload(payload, pretty=args.json)
    return 0


def _cmd_chat_index_validate(args: argparse.Namespace) -> int:
    payload = validate_chat_index_capture_plan(
        Path(args.plan),
        chatlas_root=Path(args.chatlas_root) if args.chatlas_root else None,
    )
    _print_payload(payload, pretty=args.json)
    return 0


def _cmd_chat_index_apply(args: argparse.Namespace) -> int:
    payload = apply_chat_index_capture_plan(
        Path(args.plan),
        chatlas_root=Path(args.chatlas_root) if args.chatlas_root else None,
    )
    _print_payload(payload, pretty=args.json)
    return 0


def _cmd_views_list(args: argparse.Namespace) -> int:
    _print_payload(list_views(), pretty=args.json)
    return 0


def _cmd_views_get(args: argparse.Namespace) -> int:
    reader = _model_reader_for_selector(args)
    payload = project_view(reader, view=args.view, limit=args.limit)
    _print_payload(payload, pretty=args.json)
    return 0


def _cmd_cache_status(args: argparse.Namespace) -> int:
    payload = normal_model_cache_status(
        session_id=args.session_id,
        identity_hash=args.identity_hash,
        chatlas_root=Path(args.chatlas_root) if args.chatlas_root else None,
    )
    if args.json:
        _print_payload(payload, pretty=True)
    else:
        print(f"{payload['standing']}: {payload['path']}")
    return 0


def _cmd_cache_build(args: argparse.Namespace) -> int:
    reader = materialize_normal_model_cache(
        session_id=args.session_id,
        identity_hash=args.identity_hash,
        chatlas_root=Path(args.chatlas_root) if args.chatlas_root else None,
    )
    payload = {
        "standing": "FRESH",
        "path": str(reader.path),
        "cache_key": reader.metadata["cache_key"],
        "session": reader.metadata["model"]["session"],
        "counts": reader.metadata["counts"],
    }
    if args.json:
        _print_payload(payload, pretty=True)
    else:
        print(f"FRESH: {reader.path}")
    return 0


def _non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be non-negative")
    return parsed


def _json_object(value: str) -> dict[str, object]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError("must be a JSON object") from exc
    if not isinstance(parsed, dict):
        raise argparse.ArgumentTypeError("must be a JSON object")
    return parsed


def _add_cache_selector(parser: argparse.ArgumentParser) -> None:
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--session-id")
    selector.add_argument("--identity-hash")
    parser.add_argument("--chatlas-root")
    parser.add_argument("--json", action="store_true")


def _anchory_root(args: argparse.Namespace) -> Path | None:
    return Path(args.chatlas_root) if args.chatlas_root else None


def _cmd_anchory_preview(args: argparse.Namespace) -> int:
    _print_payload(
        chatlas2_anchory_preview(
            members=tuple(args.members),
            line_content=args.line_content,
            gates=args.gates,
            predecessors=tuple(args.predecessors),
            issue_context=tuple(args.issues),
            radius=args.radius,
            chatlas_root=_anchory_root(args),
        ),
        pretty=True,
    )
    return 0


def _cmd_anchory_register(args: argparse.Namespace) -> int:
    _print_payload(
        chatlas2_anchory_register(
            members=tuple(args.members),
            line_content=args.line_content,
            gates=args.gates,
            predecessors=tuple(args.predecessors),
            issue_context=tuple(args.issues),
            radius=args.radius,
            chatlas_root=_anchory_root(args),
        ),
        pretty=True,
    )
    return 0


def _cmd_message_support_preview(args: argparse.Namespace) -> int:
    _print_payload(
        chatlas2_message_support_preview(
            members=tuple(args.members),
            radius=args.radius,
            chatlas_root=_anchory_root(args),
        ),
        pretty=True,
    )
    return 0


def _cmd_message_support_register(args: argparse.Namespace) -> int:
    _print_payload(
        chatlas2_message_support_register(
            members=tuple(args.members),
            radius=args.radius,
            chatlas_root=_anchory_root(args),
        ),
        pretty=True,
    )
    return 0


def _cmd_anchory_resolve(args: argparse.Namespace) -> int:
    _print_payload(
        chatlas2_anchory_resolve(
            args.anchor,
            radius=args.radius,
            chatlas_root=_anchory_root(args),
        ),
        pretty=True,
    )
    return 0


def _cmd_anchory_batch_preview(args: argparse.Namespace) -> int:
    _print_payload(
        chatlas2_anchory_batch_preview(
            items=load_anchor_batch(Path(args.input)),
            chatlas_root=_anchory_root(args),
        ),
        pretty=True,
    )
    return 0


def _cmd_anchory_batch_register(args: argparse.Namespace) -> int:
    _print_payload(
        chatlas2_anchory_batch_register(
            items=load_anchor_batch(Path(args.input)),
            chatlas_root=_anchory_root(args),
        ),
        pretty=True,
    )
    return 0


def _cmd_corpus_prepare(args: argparse.Namespace) -> int:
    row = select_one_chatlas_index_row(
        command="tarav chatlas2 corpus ingest prepare",
        providers=(args.provider,),
        session_id=args.session_id,
    )
    script = load_script_spec(Path(args.script))
    candidate = prepare_capture(
        row=row,
        script=script,
        captured_at=args.captured_at,
        features=args.features or script.features,
        stage_dir=Path(args.stage),
    )
    payload = {"candidate": str(candidate), "status": "prepared"}
    if args.json:
        _print_payload(payload, pretty=False)
    else:
        print(f"prepared: {candidate}")
    return 0


def _cmd_corpus_register(args: argparse.Namespace) -> int:
    registered = register_candidate(
        Path(args.candidate),
        corpus_root=Path(args.corpus),
    )
    payload = {"registered": registered}
    if args.json:
        _print_payload(payload, pretty=False)
    else:
        print("registered" if registered else "already registered")
    return 0


def _cmd_corpus_list(args: argparse.Namespace) -> int:
    records = load_capture_records(Path(args.corpus) / "captures.jsonl")
    payload = {"capture_count": len(records), "captures": records}
    if args.json:
        _print_payload(payload, pretty=False)
    else:
        for record in records:
            print(
                f"{record['capture_id']}  {record['provider']}  "
                f"{record['script_id']}@{record['script_revision']}"
            )
    return 0


def _cmd_corpus_verify(args: argparse.Namespace) -> int:
    payload = verify_corpus(Path(args.corpus))
    if args.json:
        _print_payload(payload, pretty=False)
    else:
        print(
            f"{payload['status']}: {payload['capture_count']} captures, "
            f"{payload['artifact_count']} artifacts"
        )
    return 0


def _cmd_corpus_check(args: argparse.Namespace) -> int:
    payload = check_corpus(Path(args.corpus))
    if args.json:
        _print_payload(payload, pretty=False)
    else:
        print(
            f"{payload['status']}: {payload['passed_count']} passed, "
            f"{payload['unsupported_count']} unsupported, "
            f"{payload['failed_count']} failed"
        )
    return 0 if payload["status"] == "ok" else 1


def register_chatlas2_commands(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "chatlas2",
        help="Experimental loss-preserving chat normalization.",
    )
    commands = parser.add_subparsers(dest="chatlas2_command", required=True)
    normalize = commands.add_parser(
        "normalize",
        help="Normalize one archived supported session into the Chatlas2 model.",
    )
    selector = normalize.add_mutually_exclusive_group(required=True)
    selector.add_argument(
        "--session-id",
        help="Exact native provider session id.",
    )
    selector.add_argument(
        "--identity-hash",
        help="Exact or prefix Chatlas identity hash.",
    )
    normalize_mode = normalize.add_mutually_exclusive_group()
    normalize_mode.add_argument(
        "--include-raw",
        action="store_true",
        help="Compute directly and attach optional normalizer-owned raw evidence.",
    )
    normalize_mode.add_argument(
        "--refresh",
        action="store_true",
        help="Force normalization and replace the compact cache.",
    )
    normalize.add_argument("--chatlas-root")
    normalize.add_argument(
        "--json",
        action="store_true",
        help="Print the complete Chatlas2 Normal Model as JSON.",
    )
    normalize.set_defaults(handler=_cmd_normalize)

    sessions = commands.add_parser(
        "sessions",
        help="Select Chatlas2-capable sessions through the existing Session.Index.",
    )
    session_commands = sessions.add_subparsers(
        dest="chatlas2_sessions_command", required=True
    )
    session_query = session_commands.add_parser(
        "query", help="Find chats by provider-neutral session metadata."
    )
    session_query.add_argument("--session-id")
    session_query.add_argument("--identity-hash")
    session_query.add_argument(
        "--provider",
        dest="providers",
        action="append",
        choices=SUPPORTED_QUERY_PROVIDERS,
    )
    session_query.add_argument("--project")
    session_query.add_argument("--project-base")
    session_query.add_argument("--active-after")
    session_query.add_argument(
        "--sort", choices=("lexical", "newest", "oldest"), default="newest"
    )
    session_query.add_argument("--limit", type=_non_negative_int, default=50)
    session_query.add_argument("--chatlas-root")
    session_query.add_argument("--json", action="store_true")
    session_query.set_defaults(handler=_cmd_sessions_query)

    chat = commands.add_parser(
        "chat",
        help="Query provider-neutral content inside a Session.Query result set.",
    )
    chat_commands = chat.add_subparsers(dest="chatlas2_chat_command", required=True)
    chat_query = chat_commands.add_parser(
        "query", help="Find authoritative Chat.Message records."
    )
    chat_query.add_argument("--session-id")
    chat_query.add_argument("--identity-hash")
    chat_query.add_argument(
        "--provider",
        dest="providers",
        action="append",
        choices=SUPPORTED_QUERY_PROVIDERS,
    )
    chat_query.add_argument("--project")
    chat_query.add_argument("--project-base")
    chat_query.add_argument("--active-after")
    chat_query.add_argument("--side", choices=("user", "agent"))
    text_query = chat_query.add_mutually_exclusive_group()
    text_query.add_argument("--exact", dest="text_exact")
    text_query.add_argument("--contains", dest="text_contains")
    text_query.add_argument("--regex", dest="text_regex")
    text_query.add_argument("--verbatim", dest="text_verbatim")
    chat_query.add_argument("--after")
    chat_query.add_argument("--before")
    chat_query.add_argument("--message-address")
    chat_query.add_argument("--include-turn-ref", action="store_true")
    chat_query.add_argument(
        "--sort", choices=("oldest", "newest"), default="oldest"
    )
    chat_query.add_argument("--session-limit", type=_non_negative_int, default=50)
    chat_query.add_argument("--limit", type=_non_negative_int, default=50)
    chat_query.add_argument("--chatlas-root")
    chat_query.add_argument("--json", action="store_true")
    chat_query.set_defaults(handler=_cmd_chat_query)

    cache = commands.add_parser(
        "cache",
        help="Build or inspect disposable compact Normal Model caches.",
    )
    cache_commands = cache.add_subparsers(dest="chatlas2_cache_command", required=True)
    cache_status = cache_commands.add_parser(
        "status", help="Inspect cache freshness without normalizing."
    )
    _add_cache_selector(cache_status)
    cache_status.set_defaults(handler=_cmd_cache_status)
    cache_build = cache_commands.add_parser(
        "build", help="Explicitly normalize and replace one session cache."
    )
    _add_cache_selector(cache_build)
    cache_build.set_defaults(handler=_cmd_cache_build)

    messages = commands.add_parser(
        "messages",
        help="Inspect provider-neutral Chat.Message projections.",
    )
    message_commands = messages.add_subparsers(
        dest="chatlas2_messages_command", required=True
    )
    message_list = message_commands.add_parser(
        "list", help="List projected messages in chronological order."
    )
    _add_message_selector(message_list)
    message_list.set_defaults(handler=_cmd_messages_list)
    message_find = message_commands.add_parser(
        "find", help="Find projected messages by provider-neutral primary text."
    )
    _add_message_selector(message_find)
    message_find.add_argument("--text", required=True, help="Text to locate.")
    message_find.add_argument(
        "--exact", action="store_true", help="Require complete text equality."
    )
    message_find.set_defaults(handler=_cmd_messages_find)

    turns = commands.add_parser(
        "turns",
        help="Inspect compact Chat.Turn groupings and hydrate them on demand.",
    )
    turn_commands = turns.add_subparsers(dest="chatlas2_turns_command", required=True)
    turn_list = turn_commands.add_parser(
        "list", help="List compact turns in chronological order."
    )
    _add_message_selector(turn_list)
    turn_list.set_defaults(handler=_cmd_turns_list)
    turn_get = turn_commands.add_parser(
        "get", help="Get one turn by turn address or containing message address."
    )
    turn_session_selector = turn_get.add_mutually_exclusive_group(required=True)
    turn_session_selector.add_argument("--session-id")
    turn_session_selector.add_argument("--identity-hash")
    turn_target_selector = turn_get.add_mutually_exclusive_group(required=True)
    turn_target_selector.add_argument("--turn-address")
    turn_target_selector.add_argument("--message-address")
    turn_get.add_argument("--hydrate", action="store_true")
    turn_get.add_argument("--chatlas-root")
    turn_get.add_argument("--json", action="store_true")
    turn_get.set_defaults(handler=_cmd_turns_get)

    chat_index = commands.add_parser(
        "chat-index",
        help="Backpropagate landed Hugentic lines into Chat.Index HEAD and tape.",
    )
    chat_index_commands = chat_index.add_subparsers(
        dest="chatlas2_chat_index_command", required=True
    )
    chat_index_scaffold = chat_index_commands.add_parser(
        "scaffold", help="Create one real-time Capture.Plan envelope."
    )
    chat_index_selector = chat_index_scaffold.add_mutually_exclusive_group(
        required=True
    )
    chat_index_selector.add_argument("--session-id")
    chat_index_selector.add_argument("--identity-hash")
    chat_index_scaffold.add_argument("--stage", required=True)
    chat_index_scaffold.add_argument("--chatlas-root")
    chat_index_scaffold.add_argument("--json", action="store_true")
    chat_index_scaffold.set_defaults(handler=_cmd_chat_index_scaffold)
    for name, handler, help_text in (
        (
            "validate",
            _cmd_chat_index_validate,
            "Resolve one ready Capture.Plan without writing Chat.Index.",
        ),
        (
            "apply",
            _cmd_chat_index_apply,
            "Apply one ready Capture.Plan through recoverable replacement.",
        ),
    ):
        command = chat_index_commands.add_parser(name, help=help_text)
        command.add_argument("--plan", required=True)
        command.add_argument("--chatlas-root")
        command.add_argument("--json", action="store_true")
        command.set_defaults(handler=handler)

    views = commands.add_parser(
        "views",
        help="Read disposable projections of canonical Normal Model content.",
    )
    view_commands = views.add_subparsers(dest="chatlas2_views_command", required=True)
    view_list = view_commands.add_parser(
        "list", help="List the implemented Chatlas2 views."
    )
    view_list.add_argument("--json", action="store_true")
    view_list.set_defaults(handler=_cmd_views_list)
    view_get = view_commands.add_parser(
        "get", help="Read one view for one exact session."
    )
    view_selector = view_get.add_mutually_exclusive_group(required=True)
    view_selector.add_argument("--session-id")
    view_selector.add_argument("--identity-hash")
    view_get.add_argument("--view", choices=view_names(), default="full")
    view_get.add_argument("--limit", type=_non_negative_int)
    view_get.add_argument("--chatlas-root")
    view_get.add_argument("--json", action="store_true")
    view_get.set_defaults(handler=_cmd_views_get)

    anchory = commands.add_parser(
        "anchory",
        help="Ground Hugentic records in Chatlas2 messages.",
    )
    anchory_commands = anchory.add_subparsers(
        dest="chatlas2_anchory_command", required=True
    )
    for name, handler, help_text in (
        ("preview", _cmd_anchory_preview, "Preview a line support dossier."),
        ("register", _cmd_anchory_register, "Idempotently register a line dossier."),
    ):
        command = anchory_commands.add_parser(name, help=help_text)
        command.add_argument(
            "--member",
            dest="members",
            action="append",
            required=True,
            help=("Support as <session>:<message-address>:<message-hash>; repeatable."),
        )
        command.add_argument("--line-content", required=True)
        command.add_argument(
            "--gates",
            type=_json_object,
            help="Independent semantic or tokenized approval message refs as JSON.",
        )
        command.add_argument(
            "--predecessor", dest="predecessors", action="append", default=[]
        )
        command.add_argument("--issue", dest="issues", action="append", default=[])
        command.add_argument("--radius", type=int, default=4)
        command.add_argument("--chatlas-root")
        command.set_defaults(handler=handler)
    message_support = anchory_commands.add_parser(
        "support", help="Mint a generic user-message support anchor."
    )
    message_support_commands = message_support.add_subparsers(
        dest="chatlas2_message_support_command", required=True
    )
    for name, handler in (
        ("preview", _cmd_message_support_preview),
        ("register", _cmd_message_support_register),
    ):
        command = message_support_commands.add_parser(name)
        command.add_argument("--member", dest="members", action="append", required=True)
        command.add_argument("--radius", type=int, default=4)
        command.add_argument("--chatlas-root")
        command.set_defaults(handler=handler)
    anchory_resolve = anchory_commands.add_parser(
        "resolve", help="Resolve a Chatlas2 line dossier."
    )
    anchory_resolve.add_argument("anchor")
    anchory_resolve.add_argument("--radius", type=int, default=4)
    anchory_resolve.add_argument("--chatlas-root")
    anchory_resolve.set_defaults(handler=_cmd_anchory_resolve)
    anchory_batch = anchory_commands.add_parser(
        "batch", help="Preview or register a Chatlas2 line-dossier batch."
    )
    anchory_batch_commands = anchory_batch.add_subparsers(
        dest="chatlas2_anchory_batch_command", required=True
    )
    for name, handler in (
        ("preview", _cmd_anchory_batch_preview),
        ("register", _cmd_anchory_batch_register),
    ):
        command = anchory_batch_commands.add_parser(name)
        command.add_argument(
            "--input",
            required=True,
            help=f"Path to a {CHATLAS2_ANCHOR_BATCH_SCHEMA} JSON document.",
        )
        command.add_argument("--chatlas-root")
        command.set_defaults(handler=handler)

    corpus = commands.add_parser(
        "corpus",
        help="Manage the hermetic Chatlas2 conformance corpus.",
    )
    corpus_commands = corpus.add_subparsers(dest="corpus_command", required=True)

    ingest = corpus_commands.add_parser(
        "ingest",
        help="Prepare or explicitly register one archived capture.",
    )
    ingest_commands = ingest.add_subparsers(dest="ingest_command", required=True)
    prepare = ingest_commands.add_parser(
        "prepare",
        help="Anonymize and validate one capture without registering it.",
    )
    prepare.add_argument("--corpus", required=True, help="Target corpus directory.")
    prepare.add_argument(
        "--stage", required=True, help="Private preparation directory."
    )
    prepare.add_argument("--script", required=True, help="Script specification JSON.")
    prepare.add_argument(
        "--provider",
        required=True,
        choices=tuple(
            family.family for family in supported_chatlas_provider_families()
        ),
        help="Archived provider family.",
    )
    prepare.add_argument("--session-id", required=True, help="Exact native session id.")
    prepare.add_argument(
        "--captured-at", required=True, help="Capture date (YYYY-MM-DD)."
    )
    prepare.add_argument(
        "--feature",
        dest="features",
        action="append",
        help="Observed feature; repeat for multiple features.",
    )
    prepare.add_argument("--json", action="store_true", help="Print JSON output.")
    prepare.set_defaults(handler=_cmd_corpus_prepare)

    register = ingest_commands.add_parser(
        "register",
        help="Register one inspected preparation candidate.",
    )
    register.add_argument("--corpus", required=True, help="Target corpus directory.")
    register.add_argument("--candidate", required=True, help="Prepared candidate JSON.")
    register.add_argument("--json", action="store_true", help="Print JSON output.")
    register.set_defaults(handler=_cmd_corpus_register)

    list_command = corpus_commands.add_parser("list", help="List registered captures.")
    list_command.add_argument("--corpus", required=True, help="Corpus directory.")
    list_command.add_argument("--json", action="store_true", help="Print JSON output.")
    list_command.set_defaults(handler=_cmd_corpus_list)

    verify = corpus_commands.add_parser(
        "verify",
        help="Verify registry and artifact integrity.",
    )
    verify.add_argument("--corpus", required=True, help="Corpus directory.")
    verify.add_argument("--json", action="store_true", help="Print JSON output.")
    verify.set_defaults(handler=_cmd_corpus_verify)

    check = corpus_commands.add_parser(
        "check",
        help="Normalize every supported capture and check its script contract.",
    )
    check.add_argument("--corpus", required=True, help="Corpus directory.")
    check.add_argument("--json", action="store_true", help="Print JSON output.")
    check.set_defaults(handler=_cmd_corpus_check)


def _add_message_selector(parser: argparse.ArgumentParser) -> None:
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument("--session-id")
    selector.add_argument("--identity-hash")
    parser.add_argument("--side", choices=("user", "agent"))
    parser.add_argument("--chatlas-root")
    parser.add_argument("--limit", type=_non_negative_int)
    parser.add_argument("--json", action="store_true")


__all__ = ["register_chatlas2_commands"]
