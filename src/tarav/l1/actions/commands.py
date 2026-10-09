"""CLI adapter for Step actions and their runs."""

from __future__ import annotations

import json
from pathlib import Path

from tarav.l0._core.errors import CliError
from tarav.l0.kernel import entity
from tarav.l1.operator_context import OperatorContextStore
from tarav.l1.records import RecordRegistry

from . import (
    CLOSED, RUNNING, ActionError, ActionRun, ActionRunStore, StepAction, StepRunner,
    action_types, resolve_action,
)


def _runner(args) -> StepRunner:
    registry = RecordRegistry(Path(args.registry)) if args.registry else None
    return StepRunner(runs=ActionRunStore(registry), contexts=OperatorContextStore(registry))


def _output(value, code: int = 0) -> int:
    print(json.dumps(value, indent=2, ensure_ascii=False))
    return code


def _pois(rows: list[dict]) -> list[dict]:
    return [{"type": poi.get("type"), "id": poi.get("id"), "message": poi.get("message")}
            for row in rows for poi in row["pois"]]


def _row(run: ActionRun) -> dict:
    data = run.data
    return {"run": str(run.id), "action": data["action"], "state": run.state, "exit": run.exit,
            "started_at": data["started_at"], "closed_at": data["closed_at"],
            "project": data["project"], "sessions": len(data["sessions"])}


def _cmd_types(args) -> int:
    rows = []
    for name, action_type in sorted(action_types().items()):
        row = {"type": name, "summary": (action_type.__doc__ or "").strip().split("\n")[0],
               "skill": action_type.skill.to_json() if action_type.skill else None}
        if issubclass(action_type, StepAction):
            row["input"] = entity(action_type.InputType).name
            row["operations"] = list(action_type.operations)
            row["exits"] = [{"name": item.name, "by": list(item.by)}
                            for item in action_type.exits]
        rows.append(row)
    return _output({"status": "ok", "types": rows})


# tarav.breadcrumb 250f9a54c802d27f7c66d23affbb1120a16fa5c1c22e97034c20edd4b54af5d7
def _cmd_start(args) -> int:
    """Start a run and tell the operator where its instructions are."""
    action_type = resolve_action(args.type)
    if not issubclass(action_type, StepAction):
        raise CliError(f"{args.type} is not a Step action")
    run = _runner(args).start(action_type, args.context)
    result = {**_row(run), "opening": {"passed": run.data["opening"]["passed"],
                                       "pois": _pois(run.data["opening"]["results"])}}
    if run.state != RUNNING:
        return _output({"status": "not-started", **result, "reason": run.data["reason"]}, 1)
    skill = run.data["skill"]
    welcome = [f"Run {run.id} of {args.type} is running."]
    if skill:
        welcome.append(f"Load the skill {skill['skill']!r}"
                       + (f", module {skill['path']!r}" if skill["path"] else "")
                       + " for what this step asks of you.")
    if action_type.operations:
        welcome.append("Operations: " + ", ".join(
            f"tarav action do --run {run.id} --operation {name}"
            for name in action_type.operations))
    welcome.append("Exits: " + ", ".join(
        f"{item.name} (by {' or '.join(item.by)})" for item in action_type.exits))
    welcome.append(f"Close it with: tarav action close --run {run.id}")
    return _output({"status": "ok", **result, "skill": skill, "welcome": welcome})


def _cmd_do(args) -> int:
    run, result = _runner(args).operate(args.run, args.operation, args.context)
    return _output({"status": "ok", **_row(run), "operation": args.operation, "result": result})


def _cmd_close(args) -> int:
    run = _runner(args).close(args.run, args.context, exit=args.exit)
    attempt = run.data["closings"][-1]
    result = {**_row(run), "closing": {"exit": attempt["exit"], "passed": attempt["passed"],
                                       "pois": _pois(attempt["results"])}}
    if run.state != CLOSED:
        return _output({"status": "still-running", **result}, 1)
    return _output({"status": "ok", **result, "output": run.data["output"]})


def _cmd_sweep(args) -> int:
    closed = _runner(args).sweep()
    return _output({"status": "ok", "closed": [_row(run) for run in closed]})


def _cmd_abort(args) -> int:
    run = _runner(args).abort(args.run, args.reason)
    return _output({"status": "ok", **_row(run), "reason": run.data["reason"]})


def _cmd_show(args) -> int:
    run = _runner(args).runs.load(args.run)
    return _output({"status": "ok", "record": run.records.to_record()})


def _cmd_list(args) -> int:
    project = str(Path(args.project).resolve()) if args.project else None
    runner = _runner(args)
    runs = runner.runs.list(state=args.state, exit=args.exit, project_root=project)
    return _output({"status": "ok", "store": str(runner.runs.map.root),
                    "runs": [_row(run) for run in runs]})


def _cli(handler):
    def run(args):
        try:
            return handler(args)
        except (ActionError, OSError, ValueError, TypeError) as error:
            raise CliError(str(error)) from error
    return run


def register_action_commands(subparsers) -> None:
    parser = subparsers.add_parser(
        "action", help="Start, work and close typed Actions; list their runs.")
    commands = parser.add_subparsers(dest="action_command", required=True)

    types = commands.add_parser("types", help="List the Action Types that can be started.")
    types.set_defaults(handler=_cli(_cmd_types))

    start = commands.add_parser(
        "start", help="Take the input from the Operator Context and run the opening test.")
    start.add_argument("--type", required=True, help="Action Type name.")
    start.add_argument("--context", required=True, help="Id of the Operator Context input.")
    start.set_defaults(handler=_cli(_cmd_start))

    do = commands.add_parser("do", help="Do one operation of a running Step action.")
    do.add_argument("--run", required=True)
    do.add_argument("--operation", required=True)
    do.add_argument("--context", help="Operator Context input; defaults to the run's last one.")
    do.set_defaults(handler=_cli(_cmd_do))

    close = commands.add_parser(
        "close", help="Take one exit; the run closes only when that exit's tests pass.")
    close.add_argument("--run", required=True)
    close.add_argument("--exit", help="Which exit; needed when the action offers several.")
    close.add_argument("--context", help="Operator Context input; defaults to the run's last one.")
    close.set_defaults(handler=_cli(_cmd_close))

    sweep = commands.add_parser(
        "sweep", help="Close the running runs whose loop-taken exit is met.")
    sweep.set_defaults(handler=_cli(_cmd_sweep))

    abort = commands.add_parser("abort", help="Close a running run with an error.")
    abort.add_argument("--run", required=True)
    abort.add_argument("--reason", required=True)
    abort.set_defaults(handler=_cli(_cmd_abort))

    show = commands.add_parser("show", help="Show one run's full record.")
    show.add_argument("--run", required=True)
    show.set_defaults(handler=_cli(_cmd_show))

    listing = commands.add_parser("list", help="List runs, newest first.")
    listing.add_argument("--state", choices=("running", "closed"))
    listing.add_argument("--exit", help="Only runs closed by this exit, or 'error'.")
    listing.add_argument("--project", help="Only runs whose input names this Project root.")
    listing.set_defaults(handler=_cli(_cmd_list))

    for command in (types, start, do, close, sweep, abort, show, listing):
        command.add_argument("--registry", help="Record Registry root; defaults to the standard one.")
