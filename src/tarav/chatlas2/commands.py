# $kw: ^chatlas2-cli --from Chatlas.Query.Surface --from Usage.Surface --note [CT] the first public Chatlas2 surface selects one Codex archive row and emits its inspectable model without mutating current Chatlas --supp ^c20260814-13u ^c20260814-15u ^c20260815-16u
from __future__ import annotations

import argparse
import json

from .pipeline import build_normal_model


def _cmd_normalize(args: argparse.Namespace) -> int:
    model = build_normal_model(
        session_id=args.session_id,
        identity_hash=args.identity_hash,
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


def register_chatlas2_commands(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "chatlas2",
        help="Experimental loss-preserving chat normalization.",
    )
    commands = parser.add_subparsers(dest="chatlas2_command", required=True)
    normalize = commands.add_parser(
        "normalize",
        help="Normalize one archived Codex session into the Chatlas2 model.",
    )
    selector = normalize.add_mutually_exclusive_group(required=True)
    selector.add_argument(
        "--session-id",
        help="Exact native Codex session id.",
    )
    selector.add_argument(
        "--identity-hash",
        help="Exact or prefix Chatlas identity hash.",
    )
    normalize.add_argument(
        "--json",
        action="store_true",
        help="Print the complete Chatlas2 Normal Model as JSON.",
    )
    normalize.set_defaults(handler=_cmd_normalize)


__all__ = ["register_chatlas2_commands"]
