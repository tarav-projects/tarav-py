"""`tarav context`: ask for the Context of an identifier from the shell."""

from __future__ import annotations

import argparse
import json

from tarav.l0._core.errors import CliError
from tarav.l1.context.query import ContextQueryService, IdentityContextQuery
from tarav.l0.kernel import entity


def _record(value) -> object:
    try:
        return value.records.to_record()
    except Exception:
        return {"object": type(value).__name__, "text": str(value)}


def _listing(target) -> list[dict[str, object]]:
    return [{"name": entry.name, "type": entity(type(entry)).name,
             "description": entry.description} for entry in target.ls()]


# tarav.breadcrumb bf3dacc3977903e5c373e142f5942adca5b966ddf5b9611c1024700e3119614b
def _context(args: argparse.Namespace, *, service: ContextQueryService) -> int:
    path = [part for part in (args.path or "").split("/") if part]
    try:
        answer = service.open(IdentityContextQuery(args.id, views=args.views, path=path))
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
    scope = getattr(answer.target, "context_scope", None)
    qualifications = [
        {"type": entity(view).name, "ship": str(entity(view).id)}
        if isinstance(view, type) else view.records.to_record()
        for view in scope.views
    ] if scope is not None else []
    if args.json:
        print(json.dumps({
            "identifier": candidate.identifier, "label": candidate.label, "resolver": name,
            "selected_views": args.views, "views": list(answer.views), "location": location,
            "qualifications": qualifications,
            "entries": listing, "value": body}, indent=2, default=str))
        return 0
    print(f"{candidate.identifier}  {candidate.label}")
    view_label = " → ".join(args.views) or " → ".join(view["type"] for view in qualifications) or "general"
    print(f"view: {view_label}   location: {location}")
    others = list(answer.views)
    if others:
        print("other views: " + ", ".join(f"--view {view}" for view in others))
    if listing is not None:
        print("entries (open one with --path <name>):")
        for row in listing:
            print(f"  {row['name']} [{row['type']}]" + (f"  — {row['description']}" if row["description"] else ""))
        return 0
    text = json.dumps(body.get("value", body) if isinstance(body, dict) else body,
                      indent=2, default=str).splitlines()
    print("\n".join(text[: args.limit]))
    if len(text) > args.limit:
        print(f"… {len(text) - args.limit} more lines; raise --limit or use --json")
    return 0


def _describe(args: argparse.Namespace) -> dict[str, object]:
    return {"id": args.id, "views": args.views, "path": args.path}


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
    # tarav.context 473c89a0:4c4bb8bf8f117d07
    parser.add_argument("--view", action="append", dest="views", default=[],
                        help="Named Context view; repeat to qualify left to right.")
    parser.add_argument("--path", help="Entries to follow inside the Context, a/b/c.")
    parser.add_argument("--limit", type=int, default=60,
                        help="Maximum lines printed for one opened value.")
    parser.add_argument("--json", action="store_true", help="Print the answer as JSON.")
    parser.set_defaults(handler=lambda args: _context(args, service=service),
                        usage_descriptor=_describe)


__all__ = ["register_context_command"]
