"""CLI adapter for Step actions: start, work, close and list them.

Each command builds one result. It is printed as a short readable text by
default and in full with `--json`; both come from that same result.
"""

from __future__ import annotations

import json
from pathlib import Path

from tarav.l0._core.errors import CliError
from tarav.l0.kernel import entity
from tarav.l1.operator_context import OperatorContextStore
from tarav.l1.records import RecordRegistry

from .tape import ClosingAttempt
from . import (
    CLOSED, RUNNING, ActionError, ActionRun, ActionRunStore, StepAction, StepRunner,
    action_types, axes, resolve_action,
)


def _runner(args) -> StepRunner:
    registry = RecordRegistry(Path(args.registry)) if args.registry else None
    return StepRunner(runs=ActionRunStore(registry), contexts=OperatorContextStore(registry))


# tarav.breadcrumb 1ea07b83144bcb2238da113334351069a288c230af6885369e4962cf32e1d84d
# tarav.breadcrumb a2d9d5a4e505423b4010ff8dff501c7d59a97ab5d3a53f21b6739a860dbf8f37
def _emit(args, value: dict, render, code: int = 0) -> int:
    """Present one result: in full as JSON, or as the command's readable summary."""
    if args.json:
        print(json.dumps(value, indent=2, ensure_ascii=False))
    else:
        print("\n".join(render(value)))
    return code


def _stands(row: dict) -> str:
    axes = row["axes"]
    stands = "open" if axes["action"] == "open" else f"closed ({axes['closing']})"
    return stands + (f", situation {axes['situation']}" if axes["situation"] else "")


def _about(row: dict) -> str:
    poi = row.get("poi")
    return f"{poi['type']}: {poi['message']}" if poi else row["action"]


def _line(row: dict, project: bool = False) -> str:
    """One action in one line: its id, its Project when several are listed, how it stands, what it is about."""
    where = f"{(row.get('project') or {}).get('name') or '-'}  " if project else ""
    return f"  {row['id']}  {where}{_stands(row)}  {_about(row)}"


def _poi_lines(pois: list[dict]) -> list[str]:
    return [f"  {poi['type']}: {poi['message']}" for poi in pois]


def _closing_lines(record: dict | None) -> list[str]:
    if not record:
        return []
    lines = [f"Closing record: {record['type']} {record['id']}, by {record['by']} at {record['at']}"]
    if record.get("reason"):
        lines.append(f"  reason: {record['reason']}")
    if record.get("support"):
        lines.append(f"  support: {len(record['support'])} reference(s)")
    if record.get("project"):
        lines.append(f"  project: {record['project'].get('name')}")
    return lines


def _pois(rows: list[dict]) -> list[dict]:
    return [{"type": poi.get("type"), "id": poi.get("id"), "message": poi.get("message")}
            for row in rows for poi in row["pois"]]


def _row(run: ActionRun) -> dict:
    data = run.data
    row = {"id": str(run.id), "action": data["action"], "state": run.state, "exit": run.exit,
           "started_at": run.started_at, "closed_at": run.closed_at,
           "project": data["project"], "sessions": len(data["sessions"]),
           "axes": axes(run)}
    poi = (data.get("event") or {}).get("poi")
    if poi:
        row["poi"] = {"id": poi.get("id"), "type": poi.get("type"), "message": poi.get("message")}
    return row


def _project_root(start: str) -> str:
    """The nearest folder at or above `start` that holds a Project marker."""
    origin = Path(start).expanduser().resolve()
    for folder in (origin, *origin.parents):
        if (folder / ".tarav" / "project.json").is_file():
            return str(folder)
    raise CliError(f"No Tarav Project at or above {origin}")


def _cmd_types(args) -> int:
    rows = []
    for name, action_type in sorted(action_types().items()):
        row = {"type": name, "summary": (action_type.__doc__ or "").strip().split("\n")[0],
               "skill": action_type.skill.to_json() if action_type.skill else None}
        if issubclass(action_type, StepAction):
            row["input"] = entity(action_type.InputType).name
            row["operations"] = list(action_type.operations)
            row["exits"] = [{"name": item.name, "by": list(item.by),
                             "closing": entity(item.closing).name}
                            for item in action_type.exits]
        rows.append(row)

    def render(value: dict) -> list[str]:
        lines = []
        for row in value["types"]:
            lines.append(f"{row['type']}: {row['summary']}")
            if "input" in row:
                lines.append(f"  input: {row['input']}")
                if row["operations"]:
                    lines.append("  operations: " + ", ".join(row["operations"]))
                lines.extend(f"  exit {item['name']}: by {' or '.join(item['by'])}, "
                             f"leaves {item['closing']}" for item in row["exits"])
        return lines or ["No Action Type is registered."]

    return _emit(args, {"status": "ok", "types": rows}, render)


# tarav.breadcrumb 250f9a54c802d27f7c66d23affbb1120a16fa5c1c22e97034c20edd4b54af5d7
def _cmd_start(args) -> int:
    """Start an action and tell the operator where its instructions are."""
    action_type = resolve_action(args.type)
    if not issubclass(action_type, StepAction):
        raise CliError(f"{args.type} is not a Step action")
    run = _runner(args).start(action_type, args.context)
    result = {**_row(run), "opening": {"passed": run.data["opening"]["passed"],
                                       "pois": _pois(run.data["opening"]["results"])}}
    if run.state != RUNNING:
        return _emit(args, {"status": "not-started", **result, "reason": run.data["reason"]},
                     lambda value: [f"Action {value['id']} did not start: {value['reason']}",
                                    *_poi_lines(value["opening"]["pois"])], 1)
    skill = run.data["skill"]
    welcome = [f"Action {run.id} of {args.type} is running."]
    if skill:
        welcome.append(f"Load the skill {skill['skill']!r}"
                       + (f", module {skill['path']!r}" if skill["path"] else "")
                       + " for what this step asks of you.")
    if action_type.operations:
        welcome.append("Operations: " + ", ".join(
            f"tarav action do --id {run.id} --operation {name}"
            for name in action_type.operations))
    welcome.append("Exits: " + ", ".join(
        f"{item.name} (by {' or '.join(item.by)})" for item in action_type.exits))
    welcome.append(f"Close it with: tarav action close --id {run.id}")
    return _emit(args, {"status": "ok", **result, "skill": skill, "welcome": welcome},
                 lambda value: value["welcome"])


def _cmd_do(args) -> int:
    run, result = _runner(args).operate(args.id, args.operation, args.context)
    return _emit(args, {"status": "ok", **_row(run), "operation": args.operation,
                        "result": result},
                 lambda value: [f"Operation {value['operation']} done in action {value['id']}.",
                                "  " + json.dumps(value["result"], ensure_ascii=False)])


def _cmd_close(args) -> int:
    run = _runner(args).close(args.id, args.context, exit=args.exit)
    attempt = next(item for item in reversed(run.data["tape"])
                   if item["type"] == entity(ClosingAttempt).name)
    result = {**_row(run), "closing": {"exit": attempt["exit"], "passed": attempt["passed"],
                                       "pois": _pois(attempt["results"])}}
    if run.state != CLOSED:
        return _emit(args, {"status": "still-running", **result},
                     lambda value: [f"Action {value['id']} is still running: the exit "
                                    f"{value['closing']['exit']} was refused.",
                                    *_poi_lines(value["closing"]["pois"])], 1)
    return _emit(args, {"status": "ok", **result, "output": run.data["output"],
                        "record": run.closing_record()},
                 lambda value: [f"Action {value['id']} closed by the exit {value['exit']}.",
                                *_closing_lines(value["record"])])


def _cmd_sweep(args) -> int:
    closed = _runner(args).sweep()
    return _emit(args, {"status": "ok", "closed": [_row(run) for run in closed]},
                 lambda value: [f"The sweep closed {len(value['closed'])} action(s).",
                                *map(_line, value["closed"])])


def _cmd_abort(args) -> int:
    run = _runner(args).abort(args.id, args.reason)
    return _emit(args, {"status": "ok", **_row(run), "reason": run.data["reason"]},
                 lambda value: [f"Action {value['id']} aborted: {value['reason']}"])


def _cmd_show(args) -> int:
    run = _runner(args).runs.load(args.id)

    def render(value: dict) -> list[str]:
        record, row = value["record"], value["summary"]
        lines = [f"Action {row['id']} of {row['action']}", f"{_stands(row)}: {_about(row)}"]
        if record["project"]:
            lines.append(f"Project: {record['project'].get('name') or ''} "
                         f"{record['project'].get('root')}".replace("  ", " "))
        lines.append(f"First opened {row['started_at']}; opened {value['opened_at']}"
                     + (f"; closed {row['closed_at']}" if row["closed_at"] else ""))
        if record["reason"]:
            lines.append(f"Reason: {record['reason']}")
        lines.extend(_closing_lines(value["closing"]))
        lines.append(f"{len(record['intakes'])} input(s) taken, {len(record['sessions'])} "
                     f"session(s), {len(record['operations'])} operation(s), "
                     f"{len(record['tape'])} event(s) on its tape.")
        lines.append(f"The full record: tarav action show --id {row['id']} --json")
        return lines

    return _emit(args, {"status": "ok", "summary": _row(run), "opened_at": run.opened_at,
                        "closing": run.closing_record(),
                        "record": run.records.to_record()}, render)


def _cmd_list(args) -> int:
    from tarav.l1.project.scope import project_scope

    # a Project sees the actions of the Projects it lists as children; --own leaves them out
    project = _project_root(args.project) if args.project else None
    roots = None if project is None else (
        (project,) if args.own else project_scope(project))
    runner = _runner(args)
    runs = runner.runs.list(state=args.state, exit=args.exit, project_root=roots)

    def render(value: dict) -> list[str]:
        rows = value["actions"]
        stands: dict[str, int] = {}
        for row in rows:
            key = "open" if row["axes"]["action"] == "open" else row["axes"]["closing"]
            stands[key] = stands.get(key, 0) + 1
        lines = [f"{len(rows)} action(s) in {value['store']}"
                 + (": " + ", ".join(f"{count} {name}" for name, count in stands.items())
                    if rows else "")]
        several = len(value["projects"] or ()) > 1
        if several:
            per = {}
            for row in rows:
                name = (row.get("project") or {}).get("name") or "-"
                per[name] = per.get(name, 0) + 1
            lines.append("Projects: " + ", ".join(
                f"{Path(root).name} {per.get(Path(root).name, 0)}"
                for root in value["projects"]) + ". --own lists only the first.")
        lines.extend(_line(row, several) for row in rows[:args.limit])
        if len(rows) > args.limit:
            lines.append(f"  … {len(rows) - args.limit} more; raise --limit, or use --json "
                         "for all of them in full.")
        return lines

    return _emit(args, {"status": "ok", "store": str(runner.runs.map.root),
                        "projects": list(roots) if roots is not None else None,
                        "actions": [_row(run) for run in runs]}, render)


def _cli(handler):
    def run(args):
        try:
            return handler(args)
        except (ActionError, OSError, ValueError, TypeError) as error:
            raise CliError(str(error)) from error
    return run


def register_action_commands(subparsers) -> None:
    parser = subparsers.add_parser(
        "action", help="Start, work and close typed Actions; list them.")
    commands = parser.add_subparsers(dest="action_command", required=True)

    types = commands.add_parser("types", help="List the Action Types that can be started.")
    types.set_defaults(handler=_cli(_cmd_types))

    start = commands.add_parser(
        "start", help="Take the input from the Operator Context and run the opening test.")
    start.add_argument("--type", required=True, help="Action Type name.")
    start.add_argument("--context", required=True, help="Id of the Operator Context input.")
    start.set_defaults(handler=_cli(_cmd_start))

    do = commands.add_parser("do", help="Do one operation of a running Step action.")
    do.add_argument("--id", required=True, help="The action's id.")
    do.add_argument("--operation", required=True)
    do.add_argument("--context", help="Operator Context input; defaults to the action's last one.")
    do.set_defaults(handler=_cli(_cmd_do))

    close = commands.add_parser(
        "close", help="Take one exit; the action closes only when that exit's tests pass.")
    close.add_argument("--id", required=True, help="The action's id.")
    close.add_argument("--exit", help="Which exit; needed when the action offers several.")
    close.add_argument("--context", help="Operator Context input; defaults to the action's last one.")
    close.set_defaults(handler=_cli(_cmd_close))

    sweep = commands.add_parser(
        "sweep", help="Close the running actions whose loop-taken exit is met.")
    sweep.set_defaults(handler=_cli(_cmd_sweep))

    abort = commands.add_parser("abort", help="Close a running action with an error.")
    abort.add_argument("--id", required=True, help="The action's id.")
    abort.add_argument("--reason", required=True)
    abort.set_defaults(handler=_cli(_cmd_abort))

    show = commands.add_parser("show", help="Show one action's full record.")
    show.add_argument("--id", required=True, help="The action's id.")
    show.set_defaults(handler=_cli(_cmd_show))

    listing = commands.add_parser("list", help="List actions, newest first.")
    listing.add_argument("--state", choices=("running", "closed"))
    listing.add_argument("--exit", help="Only actions closed by this exit, or 'error'.")
    listing.add_argument("--project", nargs="?", const=".",
                         help="Only actions of the Project at or above this folder and of the "
                              "Projects it lists as children.")
    listing.add_argument("--own", action="store_true",
                         help="With --project: leave the children's actions out.")
    listing.add_argument("--limit", type=int, default=20,
                         help="How many actions the readable listing shows (default 20).")
    listing.set_defaults(handler=_cli(_cmd_list))

    for command in (types, start, do, close, sweep, abort, show, listing):
        command.add_argument("--registry", help="Record Registry root; defaults to the standard one.")
        command.add_argument("--json", action="store_true",
                             help="Print the full result as JSON instead of the summary.")
