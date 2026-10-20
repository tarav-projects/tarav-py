"""Read Notebook Blocks and query their collected Context graph."""

import json
from pathlib import Path

from tarav.l0._core.errors import CliError
from tarav.l0.kernel import TaravEntity, TaravType, entity
from tarav.l1.lines import Block, Line
from tarav.l1.lines.predicates import PREFIX
from tarav.l1.notebook import Notebook
# tarav.breadcrumb 33c95215cd65
from tarav.l2.notebook_context import NotebookContext


def _brief(obj):
    return {"id": str(obj.id), "type": entity(type(obj)).name}


def _read(obj):
    block = obj.scope if isinstance(obj, Line) else obj
    return {
        "record": block.records.to_record(),
        "focus": str(obj.id),
        "contents": [member.records.to_record() for member in block.contents],
        "ancestors": [{"record": parent.records.to_record(),
                       "lines": [member.records.to_record() for member in parent.contents
                                 if isinstance(member, Line)]}
                      for parent in reversed(block.ancestors())],
    }


def _value(value):
    if isinstance(value, TaravEntity):
        return _brief(value)
    if isinstance(value, TaravType):
        return {"type": entity(type(value)).name}
    return value


# tarav.breadcrumb 8200f87b46f9
def report(project, *, operation, branch=None, block=None, root=None,
           identifier=None, sparql=None, json_output=False):
    try:
        context = NotebookContext(project, notebook=Notebook(root),
                                  branch=branch or "model", block=block)
        base = {"project": {**_brief(project), "name": project.name, "root": str(project.root)},
                "notebook": str(context.notebook.root), "scope": _brief(context.root),
                "triplets": len(context.explorer.graph), "prefixes": {"lines": PREFIX}}
        if operation == "ls":
            rows = []
            for obj in context.root.walk():
                if isinstance(obj, Block):
                    direct_lines = [member for member in obj.contents if isinstance(member, Line)]
                    rows.append({**_brief(obj), "parent": str(obj.parent_ship) if obj.parent_ship else None,
                                 "preview": direct_lines[0].text[:200] if direct_lines else "",
                                 "lines": len(direct_lines), "blocks": len(obj.contents) - len(direct_lines)})
            result = {**base, "blocks": rows}
        elif operation == "read":
            result = {**base, **_read(context.get(identifier))}
        else:
            queried = context.explorer.query(sparql)
            result = {**base, **({"answer": queried} if isinstance(queried, bool) else
                                {"rows": [{name: _value(value) for name, value in row.items()}
                                          for row in queried]})}
    except Exception as exc:
        raise CliError(f"Notebook: {type(exc).__name__}: {exc}") from exc
    if json_output:
        print(json.dumps(result, indent=2))
    else:
        print(f"{project.name} · {base['scope']['type']} {base['scope']['id']} · {base['triplets']} triplets")
        if operation == "ls":
            for row in rows:
                print(f"  {row['id']}  {row['type']}  ({row['lines']} Lines, {row['blocks']} Blocks)  {row['preview']}")
        elif operation == "read":
            for parent in result["ancestors"]:
                print(f"context {parent['record']['id']}:")
                for line in parent["lines"]:
                    print(f"  {line['id']}  {line['text']}")
            print(f"block {result['record']['id']}:")
            for member in result["contents"]:
                print(f"  {member['id']}  {member.get('text', member['type'])}")
        else:
            print(json.dumps(result.get("answer", result.get("rows")), indent=2))
    return 0


def _run(args):
    from tarav.l3.project.harness import run

    options = {"operation": args.operation, "branch": args.branch, "block": args.block,
               "root": str(args.root.expanduser().resolve()) if args.root is not None else None,
               "identifier": getattr(args, "id", None), "sparql": getattr(args, "sparql", None),
               "json_output": args.json}
    return run(path=args.project, code=(
        "from tarav.l3.notebook.commands import report\n"
        f"raise SystemExit(report(project, **{options!r}))\n"))


def register_notebook_commands(subparsers):
    parser = subparsers.add_parser("notebook", help="Read Notebook Blocks and query their Context graph.")
    commands = parser.add_subparsers(dest="operation", required=True)
    for name, description in (("ls", "Map the selected subtree's Blocks."),
                              ("read", "Read ordered Block contents and ancestor context."),
                              ("query", "Run SELECT or ASK over the complete collected subtree.")):
        command = commands.add_parser(name, help=description)
        command.add_argument("--project", nargs="?", const=".", default=".",
                             help="Infer the nearest Project from this path (default: cwd).")
        selection = command.add_mutually_exclusive_group()
        selection.add_argument("--branch", choices=("model", "discussion", "archive", "project"),
                               help="Project branch to collect; default: model.")
        selection.add_argument("--block", help="Select a Block Ship or unique prefix under this Project.")
        command.add_argument("--root", type=Path, help="Explicit Notebook storage directory.")
        command.add_argument("--json", action="store_true", help="Print the structured result.")
        if name == "read":
            command.add_argument("--id", help="Read a collected Block/Line Ship; default: selected root.")
        if name == "query":
            command.add_argument("--sparql", required=True, help="A Context SELECT/ASK query.")
        command.set_defaults(handler=_run)
