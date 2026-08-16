# $kw: ^chatlas2-cli --from Chatlas.Query.Surface --from Usage.Surface --from Raw.Archive --note [CT] Chatlas2 exposes one-session normalization plus explicit prepare/register and hermetic corpus inspection surfaces without mutating current Chatlas --supp ^c20260814-13u ^c20260814-15u ^c20260815-16u ^c20260815-31u ^d20260816-1u
from __future__ import annotations

import argparse
import json
from pathlib import Path

from tarav.chatlas.index_query import select_one_chatlas_index_row
from tarav.chatlas.providers import supported_chatlas_provider_families

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
    format_support_member_ref,
    load_anchor_batch,
)
from .messages import (
    chat_message_at,
    chat_message_support_member,
    find_chat_messages,
    list_chat_messages,
)
from .pipeline import build_normal_model


def _cmd_normalize(args: argparse.Namespace) -> int:
    model = build_normal_model(
        session_id=args.session_id,
        identity_hash=args.identity_hash,
        include_raw=args.include_raw,
    )
    if args.json:
        print(json.dumps(model, indent=2, ensure_ascii=False))
        return 0
    annotations = model["annotations"]
    print(f"session: {model['session']['session_id']}")
    print(f"sources: {len(model['sources'])}")
    print(f"events: {len(model['events'])}")
    print(f"chat_messages: {len(annotations['chat_messages'])}")
    print(f"agent_loaded_contexts: {len(annotations['agent_loaded_contexts'])}")
    return 0


def _print_payload(payload: object, *, pretty: bool) -> None:
    print(json.dumps(payload, indent=2 if pretty else None, ensure_ascii=False))


def _model_for_selector(args: argparse.Namespace):
    return build_normal_model(
        session_id=args.session_id,
        identity_hash=args.identity_hash,
        chatlas_root=Path(args.chatlas_root) if args.chatlas_root else None,
    )


def _message_payload(model, message):
    member = chat_message_support_member(model, message)
    return {
        "member_ref": format_support_member_ref(member),
        "member": member,
        "at": chat_message_at(model, message),
        "message": message,
    }


def _cmd_messages_list(args: argparse.Namespace) -> int:
    model = _model_for_selector(args)
    messages = list_chat_messages(model, side=args.side)
    _print_payload(
        {
            "session": model["session"],
            "count": len(messages),
            "messages": [_message_payload(model, message) for message in messages],
        },
        pretty=args.json,
    )
    return 0


def _cmd_messages_find(args: argparse.Namespace) -> int:
    model = _model_for_selector(args)
    messages = find_chat_messages(
        model,
        text=args.text,
        side=args.side,
        exact=args.exact,
    )
    _print_payload(
        {
            "session": model["session"],
            "count": len(messages),
            "messages": [_message_payload(model, message) for message in messages],
        },
        pretty=args.json,
    )
    return 0


def _anchory_root(args: argparse.Namespace) -> Path | None:
    return Path(args.chatlas_root) if args.chatlas_root else None


def _cmd_anchory_preview(args: argparse.Namespace) -> int:
    _print_payload(
        chatlas2_anchory_preview(
            members=tuple(args.members),
            line_content=args.line_content,
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
    normalize.add_argument(
        "--include-raw",
        action="store_true",
        help="Attach optional normalizer-owned raw evidence.",
    )
    normalize.add_argument(
        "--json",
        action="store_true",
        help="Print the complete Chatlas2 Normal Model as JSON.",
    )
    normalize.set_defaults(handler=_cmd_normalize)

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

    anchory = commands.add_parser(
        "anchory",
        help="Ground Index lines in Chatlas2 user messages.",
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
            help=(
                "Support as <session>:<message-address>:<message-hash>; repeatable."
            ),
        )
        command.add_argument("--line-content", required=True)
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
    parser.add_argument("--json", action="store_true")


__all__ = ["register_chatlas2_commands"]
