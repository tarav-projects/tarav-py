"""`tarav context`: open the Context of whatever an identifier identifies."""

from __future__ import annotations

import argparse
import json

from tarav.l0._core.errors import CliError
from tarav.l0.kernel import TaravClass, entity
from tarav.l1.context import LITERALS, ContextExplorer
from tarav.l1.context.query import ContextQueryService, IdentityContextQuery


def _describe_node(explorer: ContextExplorer, value) -> dict[str, object]:
    """A node as the listing shows it: its graph term and what it is."""
    if isinstance(value, LITERALS):
        return {"node": explorer.node(value).n3(), "value": value}
    shown = value.name if isinstance(value, TaravClass) else entity(type(value)).name
    return {"node": explorer.node(value).n3(), "type": shown}


# tarav.breadcrumb bf3dacc3977903e5c373e142f5942adca5b966ddf5b9611c1024700e3119614b
# tarav.breadcrumb af0818fd1d7726e95c9c36296ca3c4a544c4ce42284521178afb61b92436a53f
def _context(args: argparse.Namespace, *, service: ContextQueryService, opener) -> int:
    if args.views:
        raise CliError(
            f"Context view {args.views[0]!r} is not implemented in the graph Context model. "
            "Every object now contributes its triples through `.context.triplets()`; "
            "views are reimplemented as queries when they are needed.")
    try:
        candidates = service.resolve(IdentityContextQuery(args.id))
    except ValueError as exc:
        raise CliError(str(exc)) from exc
    if not candidates:
        raise CliError(
            f"Nothing is known by the identifier {args.id!r}. Actions are found by "
            "their id or by the id of the POI they follow (`tarav action list "
            "--project`), and Tarav Types by name or Ship.")
    if len(candidates) > 1:
        rows = [{"identifier": candidate.identifier, "resolver": name,
                 "label": candidate.label} for name, candidate in candidates]
        if args.json:
            print(json.dumps({"ambiguous": rows}, indent=2))
        else:
            print(f"{len(rows)} things match {args.id!r}; repeat with a longer --id:")
            for row in rows[:20]:
                print(f"  {row['identifier']}  {row['label']}  ({row['resolver']})")
            if len(rows) > 20:
                print(f"  … {len(rows) - 20} more")
        return 1
    name, candidate = candidates[0]
    explorer = opener(candidate.subject)
    focus = _describe_node(explorer, explorer.focus)
    edges = [{"direction": edge.direction, "predicate": edge.predicate,
              **_describe_node(explorer, edge.node)} for edge in explorer.ls()]
    if args.json:
        print(json.dumps({"identifier": candidate.identifier, "label": candidate.label,
                          "resolver": name, "focus": focus, "edges": edges}, indent=2))
        return 0
    print(f"{candidate.identifier}  {candidate.label}")
    print(f"focus: {focus['node']}  {focus['type']}")
    print("edges:")
    for index, edge in enumerate(edges):
        arrow = "→" if edge["direction"] == "out" else "←"
        shown = edge.get("type", edge.get("value"))
        print(f"  {index}  {arrow} <{edge['predicate']}>  {edge['node']}  {shown}")
    return 0


def _describe(args: argparse.Namespace) -> dict[str, object]:
    return {"id": args.id, "views": args.views}


def register_context_command(
    subparsers: argparse._SubParsersAction, *, service: ContextQueryService, opener,
) -> None:
    parser = subparsers.add_parser(
        "context",
        help="Open the Context of whatever an identifier identifies.",
        epilog=(
            "examples:\n"
            "  tarav context --id <action-id>\n"
            "  tarav context --id <poi-id>\n"
            "  tarav context --id Tarav.POI\n\n"
            "Prints the subject and the edges at it in its Context graph, the\n"
            "triples it contributes through `.context.triplets()`. Identifiers\n"
            "resolve today for actions, by their id or by the id of the POI they\n"
            "follow (a unique prefix is enough), and for Tarav Types by name or\n"
            "Ship. Scripts open the same Explorer with `obj.context()`."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--id", required=True, help="Identifier, or a unique prefix of it.")
    parser.add_argument("--view", action="append", dest="views", default=[],
                        help="Not implemented in the graph Context model; fails with an error.")
    parser.add_argument("--json", action="store_true", help="Print the answer as JSON.")
    parser.set_defaults(handler=lambda args: _context(args, service=service, opener=opener),
                        usage_descriptor=_describe)


__all__ = ["register_context_command"]
