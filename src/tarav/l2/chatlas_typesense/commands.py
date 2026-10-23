"""The machine-neutral `tarav chatlas typesense` command family."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from tarav.l0._core.errors import CliError
from tarav.l1.usage import describe_text

from .client import TypesenseConfig, TypesenseError
from .index import TypesenseIndex


def _describe(args):
    return {"operation": args.typesense_command,
            **({"query": describe_text(args.query)} if hasattr(args, "query") else {}),
            **({"limit": args.limit} if hasattr(args, "limit") else {})}


# tarav.breadcrumb d0e00376ee61
def register_typesense_commands(commands: argparse._SubParsersAction):
    parser = commands.add_parser("typesense", help="Search stored Chatlas Normal Models with Typesense.")
    leaves = parser.add_subparsers(dest="typesense_command", required=True)
    status = leaves.add_parser("status", help="Inspect Typesense health and available Normal Model files.")
    sync = leaves.add_parser("sync", help="Index existing Normal Model files; never capture or normalize.")
    sync.add_argument("--limit-sessions", type=int)
    sync.add_argument("--force", action="store_true", help="Resend unchanged sessions too.")
    search = leaves.add_parser("search", help="Hybrid search with exact Chatlas source references.")
    search.add_argument("query")
    search.add_argument("--side", choices=("user", "agent"))
    search.add_argument("--provider", choices=("codex", "claude-code"))
    search.add_argument("--since", help="ISO date or timestamp, inclusive.")
    search.add_argument("--limit", type=int, default=10)
    # tarav.breadcrumb e977b5808fad
    search.add_argument("--order", choices=("relevance", "oldest", "newest"), default="relevance")
    for leaf in (status, sync, search):
        leaf.add_argument("--config", type=Path, help="Global Typesense client configuration file.")
        leaf.add_argument("--normal-model-root", type=Path, help="Root containing stored Model directories.")
        leaf.add_argument("--json", action="store_true")
        leaf.set_defaults(handler=_run, usage_descriptor=_describe)


def _run(args):
    try:
        config = TypesenseConfig.load(args.config, normal_model_root=args.normal_model_root)
        index = TypesenseIndex(config)
        if args.typesense_command == "status":
            result = index.status()
            code = 0 if result["healthy"] else 1
        elif args.typesense_command == "sync":
            def progress(report):
                done = report["indexed_sessions"] + report["unchanged_sessions"] + report["errors"]
                if done == 1 or done % 50 == 0:
                    print(f"Typesense sync: {done} sessions checked, "
                          f"{report['indexed_documents']} documents indexed, "
                          f"{report['errors']} errors", file=sys.stderr, flush=True)

            result = index.sync(limit_sessions=args.limit_sessions, force=args.force, progress=progress)
            code = 1 if result["errors"] else 0
        else:
            result = index.search(args.query, side=args.side, provider=args.provider,
                                  since=args.since, limit=args.limit, order=args.order)
            code = 0
    except TypesenseError as exc:
        raise CliError(str(exc)) from exc
    if args.json or args.typesense_command != "search":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Found {result['found']} matching passages")
        for number, hit in enumerate(result["hits"], start=1):
            print(f"\n{number}. [{hit['side']} · {hit['provider']}] {hit['text']}")
            print(f"   session: {hit['session_id']} ({hit['session_identity']})")
            for ref in hit["source"]["turn_refs"]:
                print(f"   turn: {ref['turn_hash']}")
            print(f"   message: {hit['source']['message_ref']['message_hash']}")
    return code
