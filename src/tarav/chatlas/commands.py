from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from tarav.chatlas.core import chatlas_raw_sources, chatlas_update
from tarav.chatlas.delta_scan import chatlas_index_redo, chatlas_index_reset
from tarav.chatlas.normal_model import (
    compute_normal_model,
    provide_normal_model_reader,
)


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
    update.set_defaults(handler=_cmd_update)

    index = commands.add_parser(
        "index", help="Rebuild or reset the derived session index."
    )
    index_commands = index.add_subparsers(
        dest="chatlas_index_command", required=True
    )
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


def _add_capture_options(parser: argparse.ArgumentParser) -> None:
    _add_provider_options(parser)
    parser.add_argument("--session-id", action="append", dest="session_ids")
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
    parser.add_argument("--provider")
    parser.add_argument("--instance")
    _add_root_option(parser)


def _add_root_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--chatlas-root")


def _root(args: argparse.Namespace) -> Path | None:
    return Path(args.chatlas_root) if args.chatlas_root else None


def _print(payload: object) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _progress(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def _cmd_update(args: argparse.Namespace) -> int:
    return _print(
        chatlas_update(
            providers=tuple(args.providers) if args.providers else None,
            instances=tuple(args.instances) if args.instances else None,
            session_ids=tuple(args.session_ids or ()),
            chatlas_root=_root(args),
            start_path=args.start_path,
            cache_enabled=not args.no_cache,
            full_scan=args.full_scan,
            window_seconds=args.window_seconds,
            progress=_progress,
        )
    )


def _cmd_index_redo(args: argparse.Namespace) -> int:
    return _print(
        chatlas_index_redo(
            providers=tuple(args.providers) if args.providers else None,
            chatlas_root=_root(args),
            progress=_progress,
        )
    )


def _cmd_index_reset(args: argparse.Namespace) -> int:
    return _print(chatlas_index_reset(chatlas_root=_root(args), progress=_progress))


def _reference(args: argparse.Namespace) -> dict[str, object]:
    return {
        "identity_hash": args.identity_hash,
        "session_id": args.session_id,
        "provider": args.provider,
        "instance": args.instance,
        "chatlas_root": _root(args),
    }


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


def _project_computed_model(
    model: dict[str, object],
    *,
    include_messages: bool,
    include_turns: bool,
    include_loaded_contexts: bool,
) -> dict[str, object]:
    projected = {
        key: model[key]
        for key in ("class", "schema_version", "metadata", "session", "sources", "events")
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
