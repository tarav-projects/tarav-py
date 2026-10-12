"""`tarav context`: ask for the Context of an identifier from the shell."""

from __future__ import annotations

import argparse
import json

from tarav.l0._core.errors import CliError
from tarav.l1.context.query import ContextQueryService, IdentityContextQuery


def _record(value) -> object:
    try:
        return value.records.to_record()
    except Exception:
        return {"object": type(value).__name__, "text": str(value)}


def _listing(target) -> list[dict[str, object]]:
    return [{"name": entry.name, "description": entry.description} for entry in target.ls()]


# tarav.breadcrumb bf3dacc3977903e5c373e142f5942adca5b966ddf5b9611c1024700e3119614b
def _context(args: argparse.Namespace, *, service: ContextQueryService) -> int:
    path = [part for part in (args.path or "").split("/") if part]
    try:
        answer = service.open(IdentityContextQuery(args.id, view=args.view, path=path))
    except (KeyError, TypeError, ValueError) as exc:
        raise CliError(str(exc.args[0]) if exc.args else str(exc)) from exc
    if answer.subject is None:
        if not answer.candidates:
            raise CliError(
                f"Nothing is known by the identifier {args.id!r}. Actions are found by "
                "their id or by the id of the POI they follow (`tarav action list "
                "--project`), and Tarav Types by name or Ship.")
        rows = [{"identifier": candidate.identifier, "resolver": name,
                 "label": candidate.label} for name, candidate in answer.candidates]
        if args.json:
            print(json.dumps({"ambiguous": rows}, indent=2))
        else:
            print(f"{len(rows)} things match {args.id!r}; repeat with a longer --id:")
            for row in rows[:20]:
                print(f"  {row['identifier']}  {row['label']}  ({row['resolver']})")
            if len(rows) > 20:
                print(f"  … {len(rows) - 20} more")
        return 1
    name, candidate = answer.candidates[0]
    location = "/" + "/".join(answer.location)
    listing = _listing(answer.target) if hasattr(answer.target, "ls") else None
    body = None if listing is not None else _record(answer.target)
    if args.json:
        print(json.dumps({
            "identifier": candidate.identifier, "label": candidate.label, "resolver": name,
            "view": args.view, "views": list(answer.views), "location": location,
            "entries": listing, "value": body}, indent=2, default=str))
        return 0
    print(f"{candidate.identifier}  {candidate.label}")
    print(f"view: {args.view or 'general'}   location: {location}")
    others = [view for view in answer.views if view != args.view]
    if others:
        print("other views: " + ", ".join(f"--view {view}" for view in others))
    if listing is not None:
        print("entries (open one with --path <name>):")
        for row in listing:
            print(f"  {row['name']}" + (f"  — {row['description']}" if row["description"] else ""))
        return 0
    text = json.dumps(body.get("value", body) if isinstance(body, dict) else body,
                      indent=2, default=str).splitlines()
    print("\n".join(text[: args.limit]))
    if len(text) > args.limit:
        print(f"… {len(text) - args.limit} more lines; raise --limit or use --json")
    return 0


def _describe(args: argparse.Namespace) -> dict[str, object]:
    return {"id": args.id, "view": args.view, "path": args.path}


def register_context_command(
    subparsers: argparse._SubParsersAction, *, service: ContextQueryService,
) -> None:
    parser = subparsers.add_parser(
        "context",
        help="Open the navigable Context of whatever an identifier identifies.",
        epilog=(
            "examples:\n"
            "  tarav context --id <action-id>\n"
            "  tarav context --id <action-id> --path notes\n"
            "  tarav context --id <poi-id>\n"
            "  tarav context --id Tarav.POI\n\n"
            "Without --view the general Context opens and the other views that\n"
            "support the subject are listed. --path follows entries, separated by\n"
            "'/'. Identifiers resolve today for actions, by their id or by the id\n"
            "of the POI they follow (a unique prefix is enough), and for Tarav\n"
            "Types by name or Ship. Scripts reach the same Context through `.context`."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--id", required=True, help="Identifier, or a unique prefix of it.")
    parser.add_argument("--view", help="Named Context view; default is the general view.")
    parser.add_argument("--path", help="Entries to follow inside the Context, a/b/c.")
    parser.add_argument("--limit", type=int, default=60,
                        help="Maximum lines printed for one opened value.")
    parser.add_argument("--json", action="store_true", help="Print the answer as JSON.")
    parser.set_defaults(handler=lambda args: _context(args, service=service),
                        usage_descriptor=_describe)


__all__ = ["register_context_command"]
