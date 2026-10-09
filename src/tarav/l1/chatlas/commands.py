from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from tarav.l0._core.errors import CliError
from tarav.l1.agent.current_session import (
    CurrentSessionAbsent,
    CurrentSessionAmbiguous,
    CurrentSessionUnsupported,
    current_session,
    session_reporters,
)
from tarav.l1.chatlas.core import chatlas_raw_sources, chatlas_update
from tarav.l1.chatlas.delta_scan import chatlas_index_redo, chatlas_index_reset
from tarav.l1.chatlas.normal_model import (
    compute_normal_model,
    provide_normal_model_reader,
)
from tarav.l1.chatlas.query import ChatlasQuery, ChatlasQueryEngine, ChatlasQueryError
from tarav.l1.chatlas.raw_archive import migrate_raw_partition_manifests
from tarav.l1.chatlas.rendering import (
    DEFAULT_CHATLAS_RENDERER,
    ChatlasRenderError,
    renderer,
)
from tarav.l1.usage import describe_text


def _describe_update(args: argparse.Namespace) -> dict[str, object]:
    """Describe capture selection without retaining session identifiers."""
    return {
        **({"providers": args.providers} if args.providers else {}),
        **({"session_count": len(args.session_ids)} if args.session_ids else {}),
        **({"current_session": True} if args.current_session else {}),
        **({"full_scan": True} if args.full_scan else {}),
        **({"window_seconds": args.window_seconds}
           if args.window_seconds is not None else {}),
    }


def _describe_query(args: argparse.Namespace) -> dict[str, object]:
    reference = (
        "current-session" if args.current_session else
        "identity-hash" if args.identity_hash else "session-id"
    )
    return {
        "session_ref": reference,
        **({"provider": args.provider} if args.provider else {}),
        **({"turn_hash_prefixes": args.turn_hash_prefixes}
           if args.turn_hash_prefixes else {}),
        **({"side": args.side} if args.side else {}),
        **({"text_contains": describe_text(args.text_contains)}
           if args.text_contains else {}),
        "order": args.order,
        "limit": args.limit,
    }


def _describe_render(args: argparse.Namespace) -> dict[str, object]:
    return {
        **_describe_query(args),
        "renderer": args.renderer,
        **({"renderer_options": len(args.renderer_option)}
           if args.renderer_option else {}),
    }


def register_chatlas_commands(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "chatlas",
        help="Capture and normalize provider-native chat artifacts.",
    )
    commands = parser.add_subparsers(dest="chatlas_command", required=True)

    update = commands.add_parser(
        "update", help="Capture chat deltas and update the session index."
    )
    _add_capture_options(update)
    update.set_defaults(handler=_cmd_update, usage_descriptor=_describe_update)

    current_session = commands.add_parser(
        "current-session",
        help="Resolve the running harness's verified provider-native session.",
    )
    current_session.add_argument(
        "--provider",
        choices=tuple(session_reporters()),
        help="Harness provider; recommended when more than one may be active.",
    )
    current_session.add_argument("--json", action="store_true")
    current_session.set_defaults(handler=_cmd_current_session)

    index = commands.add_parser(
        "index", help="Rebuild or reset the derived session index."
    )
    index_commands = index.add_subparsers(dest="chatlas_index_command", required=True)
    redo = index_commands.add_parser(
        "redo", help="Rebuild the session index from captured raw artifacts."
    )
    redo.add_argument("--provider", action="append", dest="providers")
    _add_root_option(redo)
    redo.set_defaults(handler=_cmd_index_redo)
    reset = index_commands.add_parser(
        "reset", help="Delete the derived session index and scan cache."
    )
    _add_root_option(reset)
    reset.set_defaults(handler=_cmd_index_reset)
    migrate = index_commands.add_parser(
        "migrate", help="Migrate retained Chatlas records to current schemas."
    )
    _add_root_option(migrate)
    migrate.set_defaults(handler=_cmd_index_migrate)

    raw = commands.add_parser(
        "raw", help="Resolve retained raw artifacts for one exact session."
    )
    raw_commands = raw.add_subparsers(dest="chatlas_raw_command", required=True)
    sources = raw_commands.add_parser(
        "sources", help="Print raw artifact locations for one exact session."
    )
    _add_session_reference_options(sources)
    sources.set_defaults(handler=_cmd_raw_sources)

    normal_model = commands.add_parser(
        "normal-model", help="Materialize one provider-neutral Normal Model."
    )
    _add_session_reference_options(normal_model)
    normal_model.add_argument(
        "--refresh", action="store_true", help="Rebuild the derived model cache."
    )
    normal_model.add_argument(
        "--include-raw",
        action="store_true",
        help="Attach raw normalized fragments without caching.",
    )
    normal_model.add_argument(
        "--messages",
        action="store_true",
        help="Add projected Messages to the default Event output.",
    )
    normal_model.add_argument(
        "--turns",
        action="store_true",
        help="Add projected Turns to the default Event output.",
    )
    normal_model.add_argument(
        "--loaded-contexts",
        action="store_true",
        help="Add Agent Loaded Contexts to the default Event output.",
    )
    normal_model.add_argument(
        "--all",
        action="store_true",
        dest="all_collections",
        help="Add Messages, Turns, and Loaded Contexts.",
    )
    normal_model.set_defaults(handler=_cmd_normal_model)

    query = commands.add_parser("query", help="Query one exact Chatlas Normal Model.")
    _add_query_options(query)
    query.set_defaults(handler=_cmd_query, usage_descriptor=_describe_query)

    render = commands.add_parser(
        "render", help="Render Chatlas Query matches through a named Renderer."
    )
    _add_query_options(render)
    render.add_argument(
        "--renderer",
        default=DEFAULT_CHATLAS_RENDERER,
        help="Fully qualified registered Renderer name.",
    )
    render.add_argument(
        "--renderer-option",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="Renderer-owned option; may be repeated.",
    )
    render.set_defaults(handler=_cmd_render, usage_descriptor=_describe_render)


def _add_capture_options(parser: argparse.ArgumentParser) -> None:
    _add_provider_options(parser)
    parser.add_argument("--session-id", action="append", dest="session_ids")
    parser.add_argument(
        "--current-session",
        action="store_true",
        help="Capture the running harness session; supplying --provider is recommended.",
    )
    parser.add_argument("--start-path", default=".")
    parser.add_argument("--full-scan", action="store_true")
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--window-seconds", type=int)
    _add_root_option(parser)


def _add_provider_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--provider", action="append", dest="providers")
    parser.add_argument("--instance", action="append", dest="instances")


def _add_session_reference_options(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--identity-hash")
    group.add_argument("--session-id")
    group.add_argument(
        "--current-session",
        action="store_true",
        help="Use the running harness session; supplying --provider is recommended.",
    )
    parser.add_argument("--provider")
    parser.add_argument("--instance")
    _add_root_option(parser)


def _add_root_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--chatlas-root")


def _add_query_options(parser: argparse.ArgumentParser) -> None:
    _add_session_reference_options(parser)
    parser.add_argument(
        "--turn-hash-prefix",
        action="append",
        dest="turn_hash_prefixes",
        help="Lowercase Chat.Turn hash prefix; may be repeated.",
    )
    parser.add_argument(
        "--side",
        choices=("user", "agent"),
        help="Discovery filter; cannot be combined with Turn-hash prefixes.",
    )
    parser.add_argument(
        "--text-contains",
        help="Case-insensitive literal discovery filter over Turn message text.",
    )
    parser.add_argument(
        "--order",
        choices=("oldest", "newest"),
        default="oldest",
        help="Discovery order (default: oldest).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum discovery matches (default: 50).",
    )
    parser.add_argument(
        "--refresh", action="store_true", help="Rebuild the Normal Model cache."
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Capture the exact provider session before querying; this writes.",
    )
    parser.add_argument("--json", action="store_true")


def _root(args: argparse.Namespace) -> Path | None:
    return Path(args.chatlas_root) if args.chatlas_root else None


def _print(payload: object) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _progress(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _cmd_update(args: argparse.Namespace) -> int:
    providers = tuple(args.providers) if args.providers else None
    session_ids = tuple(args.session_ids or ())
    if args.current_session:
        if session_ids:
            raise CliError("--current-session cannot be combined with --session-id")
        if providers is not None and len(providers) != 1:
            raise CliError("--current-session accepts exactly one --provider")
        provider, session_id = _resolve_current_session(
            providers[0] if providers is not None else None
        )
        providers = (provider,)
        session_ids = (session_id,)
    return _print(
        chatlas_update(
            providers=providers,
            instances=tuple(args.instances) if args.instances else None,
            session_ids=session_ids,
            chatlas_root=_root(args),
            start_path=args.start_path,
            cache_enabled=not args.no_cache,
            full_scan=args.full_scan,
            window_seconds=args.window_seconds,
            progress=_progress,
        )
    )


def _cmd_current_session(args: argparse.Namespace) -> int:
    provider, session_id = _resolve_current_session(args.provider)
    payload = {
        "provider": provider,
        "session_id": session_id,
    }
    if args.json:
        return _print(payload)
    print(f"provider:   {provider}")
    print(f"session_id: {session_id}")
    return 0


def _cmd_index_redo(args: argparse.Namespace) -> int:
    return _print(
        chatlas_index_redo(
            providers=tuple(args.providers) if args.providers else None,
            chatlas_root=_root(args),
            progress=_progress,
        )
    )


def _cmd_index_migrate(args: argparse.Namespace) -> int:
    root = _root(args)
    from tarav.l1.chatlas.paths import default_chatlas_root

    chatlas_root = (root or default_chatlas_root()).expanduser().resolve()
    return _print(migrate_raw_partition_manifests(chatlas_root / "raw"))


def _cmd_index_reset(args: argparse.Namespace) -> int:
    return _print(chatlas_index_reset(chatlas_root=_root(args), progress=_progress))


def _reference(args: argparse.Namespace) -> dict[str, object]:
    provider = args.provider
    session_id = args.session_id
    if args.current_session:
        provider, session_id = _resolve_current_session(provider)
    return {
        "identity_hash": args.identity_hash,
        "session_id": session_id,
        "provider": provider,
        "instance": args.instance,
        "chatlas_root": _root(args),
    }


# tarav.breadcrumb 77e8947e08844ffbf0be40cd72d8dd24aaecba5382e7450c26624fbae15ca08a
def _resolve_current_session(provider: str | None) -> tuple[str, str]:
    """Ask the Agents workflow; keep this command's own error wording."""
    try:
        session = current_session(provider)
    except CurrentSessionUnsupported as exc:
        raise CliError(
            f"--current-session is not supported for provider: {exc.provider}"
        ) from exc
    except CurrentSessionAbsent as exc:
        if exc.provider is None:
            raise CliError(
                "--current-session found no verified harness context; supply --provider"
            ) from exc
        raise CliError(
            f"--current-session found no {exc.variable} for provider {exc.provider}"
        ) from exc
    except CurrentSessionAmbiguous as exc:
        raise CliError(
            "--current-session is ambiguous; supply --provider explicitly"
        ) from exc
    return session.provider, session.session_id


def _cmd_raw_sources(args: argparse.Namespace) -> int:
    return _print(chatlas_raw_sources(**_reference(args)))


def _cmd_normal_model(args: argparse.Namespace) -> int:
    reference = _reference(args)
    include_messages = args.messages or args.all_collections
    include_turns = args.turns or args.all_collections
    include_loaded_contexts = args.loaded_contexts or args.all_collections
    if args.include_raw:
        model = compute_normal_model(**reference, include_raw=True)
        model = _project_computed_model(
            model,
            include_messages=include_messages,
            include_turns=include_turns,
            include_loaded_contexts=include_loaded_contexts,
        )
    else:
        reader = provide_normal_model_reader(**reference, refresh=args.refresh)
        model = reader.project(
            include_messages=include_messages,
            include_turns=include_turns,
            include_loaded_contexts=include_loaded_contexts,
        )
    return _print(model)


def _cmd_query(args: argparse.Namespace) -> int:
    return _run_query_renderer(
        args,
        renderer_name=DEFAULT_CHATLAS_RENDERER,
        renderer_options={},
    )


# tarav.breadcrumb 2a02bd8be13fa9ec70c84f2d7435ba6d016d952a6070c9b0d9606c18d2a73910
def _cmd_render(args: argparse.Namespace) -> int:
    return _run_query_renderer(
        args,
        renderer_name=args.renderer,
        renderer_options=_renderer_options(args.renderer_option),
    )


def _run_query_renderer(
    args: argparse.Namespace,
    *,
    renderer_name: str,
    renderer_options: dict[str, str],
) -> int:
    try:
        selected_renderer = renderer(renderer_name)
        query = ChatlasQuery(
            turn_hash_prefixes=tuple(args.turn_hash_prefixes or ()),
            side=args.side,
            text_contains=args.text_contains,
            order=args.order,
            limit=args.limit,
        )
        reference = _query_reference(args)
        if args.update:
            _update_query_session(reference)
        reader = provide_normal_model_reader(
            **reference,
            refresh=args.refresh or args.update,
        )
        result = ChatlasQueryEngine(reader).run(query)
        rendered = selected_renderer.render(result, options=renderer_options)
    except (ChatlasQueryError, ChatlasRenderError) as exc:
        raise CliError(str(exc)) from exc
    if args.json:
        return _print(rendered.to_dict())
    print(rendered.content)
    return 0


def _query_reference(args: argparse.Namespace) -> dict[str, object]:
    if args.update:
        if args.provider is None:
            raise CliError("--update requires --provider")
        if args.identity_hash is not None:
            raise CliError(
                "--update requires --current-session or --session-id, not --identity-hash"
            )
    return _reference(args)


def _update_query_session(reference: dict[str, object]) -> None:
    provider = reference.get("provider")
    session_id = reference.get("session_id")
    instance = reference.get("instance")
    if not isinstance(provider, str) or not isinstance(session_id, str):
        raise CliError("--update requires an exact provider session")
    chatlas_update(
        providers=(provider,),
        instances=(instance,) if isinstance(instance, str) else None,
        session_ids=(session_id,),
        chatlas_root=reference.get("chatlas_root"),
        start_path=".",
        cache_enabled=True,
        full_scan=False,
        window_seconds=None,
        progress=_progress,
    )


def _renderer_options(values: list[str]) -> dict[str, str]:
    options: dict[str, str] = {}
    for value in values:
        name, separator, option = value.partition("=")
        if not separator or not name:
            raise CliError("--renderer-option must use NAME=VALUE")
        if name in options:
            raise CliError(f"duplicate Renderer option: {name}")
        options[name] = option
    return options


def _project_computed_model(
    model: dict[str, object],
    *,
    include_messages: bool,
    include_turns: bool,
    include_loaded_contexts: bool,
) -> dict[str, object]:
    projected = {
        key: model[key]
        for key in (
            "type",
            "schema_version",
            "metadata",
            "session",
            "sources",
            "counts",
            "events",
        )
    }
    if include_messages:
        projected["messages"] = model["messages"]
    if include_turns:
        projected["turns"] = model["turns"]
    if include_loaded_contexts:
        projected["loaded_contexts"] = model["loaded_contexts"]
    if "raw" in model:
        projected["raw"] = model["raw"]
    return projected


__all__ = ["register_chatlas_commands"]
